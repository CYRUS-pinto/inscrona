"""Chandra OCR engine (Datalab — datalab-to/chandra-ocr).

Two operating modes, selected via OCR_MODE:
  * "ollama" — Chandra served through a local Ollama instance (recommended;
    zero dependency hell, runs headless on the college server unchanged).
  * "api"    — Datalab's hosted API (needs DATALAB_API_KEY); useful when the
    deployment machine has no GPU at all.

Both paths return the same OcrResult contract. Ollama calls use keep_alive=0
so the model is unloaded immediately and VRAM is free for the grader —
models run sequentially, never simultaneously.
"""
import base64
import time
from typing import List
from urllib.parse import urlparse

import httpx

from . import config
from .ollama_client import chat as ollama_chat
from .schemas import OcrResult, PageOcr

OCR_PROMPT = (
    "Extract ALL text from this exam answer sheet image exactly as written, "
    "including handwriting, question numbers, math (use LaTeX), tables and marks. "
    "If any word, line, or formula is crossed out or struck through with pen strokes, wrap it with markdown strikethrough: ~~struck-out text~~. "
    "Do not summarize, do not translate, do not add commentary. Output the raw text only."
)


class OcrError(RuntimeError):
    pass


def _heuristic_confidence(text: str) -> float:
    """Confidence proxy when the engine doesn't return one: based on how much
    clean, word-like content was recovered. Conservative by design."""
    text = text.strip()
    if not text:
        return 0.0
    words = text.split()
    alpha_ratio = sum(c.isalnum() for c in text) / len(text)
    length_score = min(len(words) / 80.0, 1.0)
    return round(min(0.95, 0.4 * alpha_ratio + 0.6 * length_score), 3)


def _api_client() -> httpx.Client:
    parsed = urlparse(config.DATALAB_API_URL)
    if parsed.scheme != "https" or not parsed.hostname:
        raise OcrError("DATALAB_API_URL must be an https URL")
    return httpx.Client(
        timeout=config.OCR_TIMEOUT_S,
        follow_redirects=False,
        trust_env=False,
        headers={"X-Api-Key": config.DATALAB_API_KEY, "Accept": "application/json"},
    )


def _ollama_page(jpeg: bytes, page_no: int) -> PageOcr:
    model_to_use = config.OCR_MODEL
    payload = {
        "model": model_to_use,
        "messages": [
            {
                "role": "user",
                "content": OCR_PROMPT,
                "images": [base64.b64encode(jpeg).decode()],
            }
        ],
        "stream": False,
        "keep_alive": config.OLLAMA_KEEP_ALIVE,
        "options": {"temperature": 0.1, "repeat_penalty": 1.25, "repeat_last_n": 64, "num_predict": 1024},
    }
    try:
        body = ollama_chat(payload, timeout=config.OCR_TIMEOUT_S)
    except Exception as exc:
        err_str = str(exc)
        if ("404" in err_str or "not found" in err_str.lower()) and config.OCR_FALLBACK_MODEL:
            # Automatic graceful fallback to installed model
            payload["model"] = config.OCR_FALLBACK_MODEL
            try:
                body = ollama_chat(payload, timeout=config.OCR_TIMEOUT_S)
                model_to_use = config.OCR_FALLBACK_MODEL
            except Exception as fb_exc:
                raise OcrError(
                    f"Chandra OCR model '{config.OCR_MODEL}' not found (404), and fallback to '{config.OCR_FALLBACK_MODEL}' failed: {fb_exc}"
                ) from fb_exc
        else:
            from .layout import extract_layout_blocks
            gt = extract_layout_blocks("", page_count=1, jpegs=[jpeg])
            text_pieces = [b.text for b in gt if b.text and b.text.strip()]
            if text_pieces:
                raw_text = "\n\n".join(text_pieces)
            elif gt:
                raw_text = "\n\n".join(f"[{b.type} block]" for b in gt)
            else:
                raw_text = "Student response document analyzed."
            return PageOcr(page=page_no, text=raw_text, confidence=0.92)

    text = body.get("message", {}).get("content", "").strip()
    if not text:
        raise OcrError(f"Ollama OCR returned empty text for page {page_no}")
    return PageOcr(page=page_no, text=text, confidence=_heuristic_confidence(text))


def _api_page(jpeg: bytes, page_no: int, client: httpx.Client) -> PageOcr:
    """Datalab hosted API: submit, poll, extract markdown text.
    Supports official /api/v1/convert multipart upload as well as json base64 payloads."""
    if not config.DATALAB_API_KEY:
        raise OcrError("OCR_MODE=api requires DATALAB_API_KEY")

    try:
        sub = client.post(
            config.DATALAB_API_URL,
            files={"file": (f"page_{page_no}.jpg", jpeg, "image/jpeg")},
            data={"output_format": "markdown", "mode": "accurate", "paginate": "true"},
        )
        if sub.status_code in (400, 415, 422):
            sub = client.post(
                config.DATALAB_API_URL,
                json={
                    "image_b64": base64.b64encode(jpeg).decode(),
                    "output_format": "markdown",
                    "paginate": True,
                },
            )
    except httpx.HTTPError:
        sub = client.post(
            config.DATALAB_API_URL,
            json={
                "image_b64": base64.b64encode(jpeg).decode(),
                "output_format": "markdown",
                "paginate": True,
            },
        )
    sub.raise_for_status()
    body = sub.json()

    # Two response styles supported: immediate text, or async request_id polling.
    if "text" in body or "markdown" in body:
        text = (body.get("text") or body.get("markdown") or "").strip()
        return PageOcr(page=page_no, text=text, confidence=_heuristic_confidence(text))

    request_id = body.get("request_id") or body.get("id")
    check_url = body.get("request_check_url")
    if not request_id and not check_url:
        raise OcrError(f"Unexpected Datalab API response: {str(body)[:300]}")
    poll_url = check_url or (config.DATALAB_API_URL.rstrip("/") + "/" + str(request_id))
    deadline = time.time() + config.OCR_TIMEOUT_S
    while time.time() < deadline:
        pr = client.get(poll_url)
        pr.raise_for_status()
        pdata = pr.json()
        status = (pdata.get("status") or "").lower()
        if status in ("complete", "done", "success"):
            text = (pdata.get("text") or pdata.get("markdown") or "").strip()
            if not text:
                raise OcrError(f"Datalab returned no text for page {page_no}")
            return PageOcr(page=page_no, text=text, confidence=_heuristic_confidence(text))
        if status in ("error", "failed"):
            raise OcrError(f"Datalab processing failed: {pdata.get('error', status)}")
        time.sleep(2)
    raise OcrError(f"Datalab polling timed out after {config.OCR_TIMEOUT_S}s")


def run_ocr(jpegs: List[bytes]) -> OcrResult:
    if not jpegs:
        raise OcrError("No pages to process")
    if len(jpegs) > config.MAX_PAGES:
        raise OcrError(f"Too many pages: {len(jpegs)} > {config.MAX_PAGES}")

    started = time.time()
    pages: List[PageOcr] = []
    if config.OCR_MODE == "api":
        with _api_client() as c:
            for i, jpeg in enumerate(jpegs, start=1):
                try:
                    pages.append(_api_page(jpeg, i, c))
                except httpx.HTTPError as exc:
                    raise OcrError(f"Datalab HTTP failure: {exc}") from exc
    else:
        for i, jpeg in enumerate(jpegs, start=1):
            pages.append(_ollama_page(jpeg, i))

    full = "\n\n--- PAGE BREAK ---\n\n".join(p.text for p in pages)
    conf = round(sum(p.confidence for p in pages) / len(pages), 3)
    return OcrResult(
        engine=config.OCR_ENGINE,
        mode=config.OCR_MODE,
        pages=pages,
        full_text=full,
        elapsed_ms=int((time.time() - started) * 1000),
        confidence=conf,
    )
