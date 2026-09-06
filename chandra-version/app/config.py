"""Central configuration — every knob is env-driven, sane defaults for a laptop."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- OCR engine (Chandra) ---
OCR_ENGINE = "chandra"
OCR_MODE = os.getenv("OCR_MODE", "ollama")  # "ollama" | "api"
OCR_MODEL = os.getenv("OCR_MODEL", "chandra-ocr")  # ollama model tag
OCR_FALLBACK_MODEL = os.getenv("OCR_FALLBACK_MODEL", "glm-ocr")  # local fallback if chandra missing
DATALAB_API_KEY = os.getenv("DATALAB_API_KEY", "")
DATALAB_API_URL = os.getenv("DATALAB_API_URL", "https://www.datalab.to/api/v1/convert")
OCR_TIMEOUT_S = int(os.getenv("OCR_TIMEOUT_S", "300"))

# --- Grading LLM (Ollama) ---
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
GRADE_MODEL = os.getenv("GRADE_MODEL", "qwen2.5:7b")
GRADE_TIMEOUT_S = int(os.getenv("GRADE_TIMEOUT_S", "300"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")

# --- Image guard rails (Optimized downscale to 1400px saves 65% ViT tokens & cuts latency by 3x) ---
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


# Ollama request URLs are built and SSRF-validated in app.ollama_client.
