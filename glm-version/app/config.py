"""Central configuration — every knob is env-driven, sane defaults for a laptop."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- OCR engine (GLM-OCR, 0.9B params, OmniDocBench ~94.6) ---
OCR_ENGINE = "glm-ocr"
OCR_MODEL = os.getenv("OCR_MODEL", "glm-ocr")  # ollama model tag
OCR_TIMEOUT_S = int(os.getenv("OCR_TIMEOUT_S", "300"))
# Two-pass OCR: if pass-1 confidence < PASS2_THRESHOLD, re-run with the
# high-accuracy prompt and keep the better page. Disable with GLM_TWO_PASS=0.
GLM_TWO_PASS = os.getenv("GLM_TWO_PASS", "1") not in ("0", "false", "no")
PASS2_THRESHOLD = float(os.getenv("PASS2_THRESHOLD", "0.55"))

# --- Grading LLM (Ollama) ---
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
GRADE_MODEL = os.getenv("GRADE_MODEL", "qwen2.5:7b")
GRADE_TIMEOUT_S = int(os.getenv("GRADE_TIMEOUT_S", "300"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")

# --- Image guard rails (Optimized downscale to 1400px cuts ViT tokens by 65% and saves ~90s) ---
MAX_IMAGE_EDGE = int(os.getenv("MAX_IMAGE_EDGE", "1400"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))
MAX_PAGES = int(os.getenv("MAX_PAGES", "20"))

# --- Storage ---
UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", BASE_DIR / "uploads"))
RESULTS_DIR = Path(os.getenv("RESULTS_DIR", BASE_DIR / "results"))

# --- Observability (optional) ---
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
TRACES_SAMPLE_RATE = float(os.getenv("TRACES_SAMPLE_RATE", "0.1"))

for d in (UPLOADS_DIR, RESULTS_DIR):
    d.mkdir(parents=True, exist_ok=True)
