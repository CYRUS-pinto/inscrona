"""
Unified OCR module for Inscrona.

Combines:
- Chandra edition: dual-mode backend (Ollama local / Datalab API fallback)
- GLM edition: two-pass quality check (PASS1 → PASS2 for weak pages)

Golden Rule: Models run sequentially, never simultaneously.
"""

from __future__ import annotations

import base64
import logging
import os
import re
import time
from pathlib import Path
from typing import Literal

import httpx
from pydantic import HttpUrl

from .config import (
    GLM_TWO_PASS,
    OCR_ENGINE,
    OCR_MODE,
    OCR_MODEL,
    OLLAMA_HOST,
    OLLAMA_KEEP_ALIVE,
    PASS2_THRESHOLD,
    PASS2_PROMPT,
    PASS1_PROMPT,
    DATALAB_API_KEY,
    DATALAB_API_URL,
    OCR_TIMEOUT_S,
)
from .schemas import OcrResult, PageOcr
from .ollama_client import chat, _validate_url

logger = logging.getLogger(__name__)


class OcrError(RuntimeError):
    """Raised when OCR processing fails."""
    pass

# Heuristic confidence estimator
# ---------------------------------------------------------------------------

_HEURISTIC_NOISE_THRESHOLD = 120
_HEURISTIC_MIN_TEXT_LEN = 5


def _heuristic_confidence(text: str) -> float:
    """
    Quick rule-based confidence score for OCR output.

    Returns float in [0.0, 1.0]. Higher is better.
    Penalises very short text, excessive special chars, and garbled patterns.
    """
    if not text or not text.strip():
        return 0.0

    stripped = text.strip()
    score = 1.0

    # Penalise very short outputs
    if len(stripped) < _HEURISTIC_MIN_TEXT_LEN:
        score *= 0.3

    # Ratio of alphanumeric to total — garbage OCR is mostly noise
    alnum = sum(c.isalnum() for c in stripped)
    total = max(len(stripped), 1)
    alpha_ratio = alnum / total
    if alpha_ratio < 0.3:
        score *= 0.2
    elif alpha_ratio < 0.5:
        score *= 0.6

    # Excessive repetition (e.g. "aaaaa" or "???") signals hallucination
    _rep = re.compile(r"(.)\1{5,}")
    reps = _rep.findall(stripped)
    if reps:
        score *= 0.4

    # Question marks / underscores dominating
    special_ratio = sum(c in "?_" for c in stripped) / total
    if special_ratio > 0.3:
        score *= 0.3

    return max(0.0, min(score, 1.0))


# ---------------------------------------------------------------------------
# Model lifecycle helpers
# ---------------------------------------------------------------------------


def _unload_model() -> None:
    """
    Explicitly unload the current Ollama model to free VRAM.

    Uses keep_alive=0 to tell Ollama to unload immediately after the
    next request completes — critical for consumer GPUs (8-12 GB VRAM).
    """
    try:
        chat(
            model=OCR_MODEL,
            messages=[{"role": "user", "content": "ping"}],
            keep_alive=0,
        )
        logger.debug("Model %s unloaded via keep_alive=0", OCR_MODEL)
    except Exception as exc:
        logger.warning("Failed to unload model %s: %s", OCR_MODEL, exc)


# ---------------------------------------------------------------------------
# Ollama backend (Chandra dual-mode)
# ---------------------------------------------------------------------------


def _ocr_ollama(
    page_img_b64: str,
    *,
    prompt: str = PASS1_PROMPT,
    model: str | None = None,
) -> tuple[str, float]:
    """
    Send a single page image to Ollama for OCR.

    Returns (extracted_text, confidence).
    """
    model = model or OCR_MODEL
    response = chat(
        model=model,
        messages=[
            {
                "role": "user",
                "content": prompt,
                "images": [page_img_b64],
            }
        ],
        options={"temperature": 0.0},
        keep_alive=OCR_TIMEOUT_S,
    )
    text = response.get("message", {}).get("content", "")
    conf = _heuristic_confidence(text)
    return text, conf


# ---------------------------------------------------------------------------
# Datalab API backend (Chandra fallback)
# ---------------------------------------------------------------------------


def _validate_datalab_url(url: str) -> str:
    """SSRF-safe validation for the Datalab API endpoint."""
    return _validate_url(url)


def _ocr_datalab_api(
    page_img_b64: str,
    *,
    prompt: str = PASS1_PROMPT,
) -> tuple[str, float]:
    """
    Send a single page image to Datalab API for OCR.

    Uses httpx synchronous client. Validates URL for SSRF safety.
    Returns (extracted_text, confidence).
    """
    api_url = _validate_datalab_url(DATALAB_API_URL)
    api_key = DATALAB_API_KEY

    if not api_key:
        raise RuntimeError("DATALAB_API_KEY is not set; cannot use API mode")

    payload = {
        "model": OCR_MODEL,
        "prompt": prompt,
        "image": page_img_b64,
    }

    with httpx.Client(timeout=OCR_TIMEOUT_S) as client:
        resp = client.post(
            api_url,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    text = data.get("text", "") or data.get("content", "") or ""
    conf = _heuristic_confidence(text)
    return text, conf


# ---------------------------------------------------------------------------
# Dispatch helper
# ---------------------------------------------------------------------------


def _ocr_page(
    page_img_b64: str,
    *,
    prompt: str = PASS1_PROMPT,
) -> tuple[str, float]:
    """
    Dispatch a single page to the configured OCR backend.

    Respects OCR_MODE: "ollama" (default, local) or "api" (Datalab).
    """
    if OCR_MODE == "api":
        return _ocr_datalab_api(page_img_b64, prompt=prompt)
    return _ocr_ollama(page_img_b64, prompt=prompt)


ocr_page = _ocr_page


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_ocr(image_paths: list[str | Path]) -> OcrResult:
    """
    Run OCR on a list of page images.

    Pipeline (per page):
      1. Read + base64 encode image
      2. PASS1 prompt → extract text
      3. Heuristic confidence score
      4. If GLM_TWO_PASS enabled and confidence < PASS2_THRESHOLD:
         re-process with PASS2 prompt (high-accuracy mode)
      5. Collect all PageOcr results

    After all pages processed, explicitly unload the model (keep_alive=0)
    to free VRAM for the next pipeline stage.

    Returns OcrResult with per-page text + confidence + aggregated stats.
    """
    start = time.time()
    pages: list[PageOcr] = []

    logger.info("OCR started: %d pages, engine=%s, mode=%s", len(image_paths), OCR_ENGINE, OCR_MODE)

    for idx, path in enumerate(image_paths, start=1):
        path = Path(path)
        if not path.exists():
            logger.warning("Page %d: file not found — %s", idx, path)
            pages.append(PageOcr(page=idx, text="", confidence=0.0))
            continue

        img_bytes = path.read_bytes()
        img_b64 = base64.b64encode(img_bytes).decode("ascii")

        # --- PASS 1 ---
        try:
            text, conf = _ocr_page(img_b64, prompt=PASS1_PROMPT)
        except Exception as exc:
            logger.error("Page %d PASS1 failed: %s", idx, exc)
            pages.append(PageOcr(page=idx, text="", confidence=0.0))
            continue

        # --- PASS 2 (optional, GLM two-pass quality gate) ---
        if GLM_TWO_PASS and conf < PASS2_THRESHOLD:
            logger.info(
                "Page %d: confidence %.2f < threshold %.2f — running PASS2",
                idx, conf, PASS2_THRESHOLD,
            )
            try:
                text2, conf2 = _ocr_page(img_b64, prompt=PASS2_PROMPT)
                # Keep PASS2 result only if it improved confidence
                if conf2 > conf:
                    text, conf = text2, conf2
                    logger.info("Page %d: PASS2 improved confidence to %.2f", idx, conf)
            except Exception as exc:
                logger.warning("Page %d PASS2 failed, keeping PASS1: %s", idx, exc)

        pages.append(PageOcr(page=idx, text=text, confidence=conf))
        logger.debug("Page %d: %d chars, confidence=%.2f", idx, len(text), conf)

    # --- Unload model to free VRAM (Golden Rule) ---
    _unload_model()

    elapsed_ms = int((time.time() - start) * 1000)
    confidences = [p.confidence for p in pages if p.confidence > 0]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    full_text = "\n\n---PAGE BREAK---\n\n".join(p.text for p in pages)

    logger.info(
        "OCR complete: %d pages, avg_conf=%.2f, elapsed=%dms",
        len(pages), avg_conf, elapsed_ms,
    )

    return OcrResult(
        engine=OCR_ENGINE,
        mode=OCR_MODE,
        pages=pages,
        full_text=full_text,
        elapsed_ms=elapsed_ms,
        confidence=avg_conf,
    )
