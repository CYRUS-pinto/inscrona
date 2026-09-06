"""GLM-OCR engine (0.9B params — SOTA small document OCR, strong tables/LaTeX).

Served through local Ollama (native GLM-OCR support, no vLLM dependency hell).
Runs at full capacity: two-pass mode re-processes weak pages with a
high-accuracy prompt and keeps the better reading. keep_alive=0 after every
call so VRAM is free for the grading LLM — models run sequentially, never
simultaneously.
"""
import base64
import time
from typing import List

from . import config
from .ollama_client import chat as ollama_chat
from .schemas import OcrResult, PageOcr

PASS1_PROMPT = (
    "Extract ALL text from this exam answer sheet image exactly as written, "
    "including handwriting, question numbers, tables (as markdown), and math "
    "(as LaTeX). Do not summarize or add commentary. Output the raw text only."
)

# Pass 2 trades some speed for accuracy on weak pages.
PASS2_PROMPT = (
    "You are performing high-accuracy OCR on a scanned handwritten exam answer "
    "sheet. Transcribe every visible character exactly, preserving layout: "
    "question numbers on their own lines, tables as markdown, formulas as LaTeX. "
    "If a word is ambiguous, choose the reading most consistent with sentence "
    "context. Output transcription only."
)


class OcrError(RuntimeError):
    pass


def _heuristic_confidence(text: str) -> float:
    """Confidence proxy when the engine doesn't return one. Penalizes both
    thin content and duplicated blocks (a known vision-OCR failure mode where
    the page transcription is emitted twice)."""
    text = text.strip()
    if not text:
        return 0.0
    words = text.split()
    alpha_ratio = sum(c.isalnum() for c in text) / len(text)
    length_score = min(len(words) / 80.0, 1.0)
    unique_ratio = len(set(words)) / len(words)
    base = min(0.95, 0.4 * alpha_ratio + 0.6 * length_score)
    return round(base * (0.5 + 0.5 * unique_ratio), 3)


def _call_ocr(jpeg: bytes, prompt: str) -> str:
    payload = {
        "model": config.OCR_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [base64.b64encode(jpeg).decode()],
            }
        ],
        "stream": False,
        "keep_alive": config.OLLAMA_KEEP_ALIVE,
        "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 1024},
    }
    try:
        body = ollama_chat(payload, timeout=config.OCR_TIMEOUT_S)
    except Exception as exc:
        raise OcrError(f"Ollama OCR call failed: {exc}") from exc
    return body.get("message", {}).get("content", "").strip()


def _ocr_page(jpeg: bytes, page_no: int) -> PageOcr:
    text = _call_ocr(jpeg, PASS1_PROMPT)
    if not text or not text.strip():
        return PageOcr(page=page_no, text="[BLANK PAGE / UNATTEMPTED]", confidence=0.0)
    best = PageOcr(page=page_no, text=text, confidence=_heuristic_confidence(text))

    # Pass 2: high-accuracy retry on weak pages, keep the better reading.
    if config.GLM_TWO_PASS and best.confidence < config.PASS2_THRESHOLD:
        alt = _call_ocr(jpeg, PASS2_PROMPT)
        alt_conf = _heuristic_confidence(alt)
        if alt and alt_conf > best.confidence:
            best = PageOcr(page=page_no, text=alt, confidence=alt_conf)
    return best


def run_ocr(jpegs: List[bytes]) -> OcrResult:
    if not jpegs:
        raise OcrError("No pages to process")
    if len(jpegs) > config.MAX_PAGES:
        raise OcrError(f"Too many pages: {len(jpegs)} > {config.MAX_PAGES}")

    started = time.time()
    pages = [_ocr_page(jpeg, i) for i, jpeg in enumerate(jpegs, start=1)]
    full = "\n\n--- PAGE BREAK ---\n\n".join(p.text for p in pages)
    conf = round(sum(p.confidence for p in pages) / len(pages), 3)
    return OcrResult(
        engine=config.OCR_ENGINE,
        mode="ollama",
        pages=pages,
        full_text=full,
        elapsed_ms=int((time.time() - started) * 1000),
        confidence=conf,
    )
