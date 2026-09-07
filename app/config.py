"""Centralised configuration — every tuneable knob in one place."""

from __future__ import annotations

import os
from pathlib import Path

# ── CORS ───────────────────────────────────────────────────────────
CORS_ORIGINS: list[str] = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")]

# ── OCR engine ───────────────────────────────────────────────────────────
OCR_ENGINE: str = os.getenv("OCR_ENGINE", "glm-ocr")   # "glm-ocr" | "chandra"
OCR_MODEL: str = os.getenv("OCR_MODEL", "glm-ocr")     # model name sent to the engine
OCR_TIMEOUT_S: int = int(os.getenv("OCR_TIMEOUT_S", "300"))

# ── Two-pass OCR (GLM quality gating) ───────────────────────────────────
GLM_TWO_PASS: bool = os.getenv("GLM_TWO_PASS", "true").lower() in ("1", "true", "yes")
PASS2_THRESHOLD: float = float(os.getenv("PASS2_THRESHOLD", "0.55"))

# ── Ollama / LLM grading ────────────────────────────────────────────────
OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
GRADE_MODEL: str = os.getenv("GRADE_MODEL", "qwen2.5:7b")
FEEDBACK_MODEL: str = os.getenv("FEEDBACK_MODEL", "qwen2.5:7b")
GRADE_TIMEOUT_S: int = int(os.getenv("GRADE_TIMEOUT_S", "300"))
OLLAMA_KEEP_ALIVE: str = os.getenv("OLLAMA_KEEP_ALIVE", "30m")

# ── Image processing ─────────────────────────────────────────────────────
MAX_IMAGE_EDGE: int = int(os.getenv("MAX_IMAGE_EDGE", "1400"))
MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "20"))
MAX_PAGES: int = int(os.getenv("MAX_PAGES", "20"))

# ── Layout detection (IBM Docling ONNX) ──────────────────────────────────
LAYOUT_MODEL_PATH: str = os.getenv(
    "LAYOUT_MODEL_PATH",
    str(Path(__file__).resolve().parent.parent / "models" / "layout" / "model.onnx"),
)

# ── Ensemble weights ─────────────────────────────────────────────────────
ENSEMBLE_W_KEYWORD: float = float(os.getenv("ENSEMBLE_W_KEYWORD", "0.25"))
ENSEMBLE_W_SEMANTIC: float = float(os.getenv("ENSEMBLE_W_SEMANTIC", "0.35"))
ENSEMBLE_W_COT: float = float(os.getenv("ENSEMBLE_W_COT", "0.40"))

# ── Audit trail ──────────────────────────────────────────────────────────
AUDIT_DIR: Path = Path(os.getenv("AUDIT_DIR", str(Path(__file__).resolve().parent.parent / "results")))
AUDIT_FILE: str = "audit_chain.jsonl"

# ── File-system limits ───────────────────────────────────────────────────
UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", str(Path(__file__).resolve().parent.parent / "uploads")))
RESULTS_DIR: Path = Path(os.getenv("RESULTS_DIR", str(Path(__file__).resolve().parent.parent / "results")))
ANSWER_KEY_PATH: Path = Path(os.getenv("ANSWER_KEY_PATH", str(Path(__file__).resolve().parent.parent / "qp" / "answer_key.json")))

# ── Service & Datalab API fallbacks ───────────────────────────────────────
OCR_MODE: str = os.getenv("OCR_MODE", "ollama")
DATALAB_API_URL: str = os.getenv("DATALAB_API_URL", "https://api.datalab.to/v1")
DATALAB_API_KEY: str = os.getenv("DATALAB_API_KEY", "")
KEEP_ALIVE: str = os.getenv("KEEP_ALIVE", "0")

PASS1_PROMPT: str = (
    "Transcribe all handwritten text from this exam answer sheet image verbatim. "
    "Preserve question numbers, equations, and tables. Wrap equations in $ or $$ "
    "(as LaTeX). If any text, line, or equation is crossed out or struck through with a pen line, wrap it with markdown strikethrough: ~~crossed-out text~~. "
    "Do not summarize or add commentary. Output the raw text only."
)

PASS2_PROMPT: str = (
    "You are performing high-accuracy OCR on a scanned handwritten exam answer "
    "sheet. Transcribe every visible character exactly, preserving layout: "
    "question numbers on their own lines, tables as markdown, formulas as LaTeX. "
    "If any word, line, or equation is crossed out or struck through with a pen stroke, transcribe it using ~~struck-out text~~. "
    "If a word is ambiguous, choose the reading most consistent with sentence "
    "context. Output transcription only."
)

import sys
settings = sys.modules[__name__]


