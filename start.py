"""Inscrona launcher — pre-flight checks + uvicorn startup."""
import argparse
import os
import sys
from pathlib import Path

import requests
from loguru import logger

OLLAMA_URL = "http://127.0.0.1:11434"
REQUIRED_MODELS = ["glm-ocr", "llama3.2:3b"]
REQUIRED_DIRS = ["./uploads", "./results"]


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (stdlib only). Never overrides real env vars."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not key or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ[key] = value


_load_dotenv()

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

def check_ollama_reachable() -> bool:
    """Ping Ollama's /api/tags endpoint."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        logger.success("Ollama reachable at {}", OLLAMA_URL)
        return True
    except Exception as exc:
        logger.error("Cannot reach Ollama at {} — {}", OLLAMA_URL, exc)
        return False


def check_models_installed() -> bool:
    """Verify all required models are pulled locally."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
    except Exception as exc:
        logger.error("Failed to query Ollama models — {}", exc)
        return False

    ok = True
    for model in REQUIRED_MODELS:
        # Ollama may store names as "model:latest" — match prefix
        found = any(m == model or m.startswith(model + ":") for m in models)
        if found:
            logger.success("Model '{}' found", model)
        else:
            logger.error("Model '{}' not found — pull it with: ollama pull {}", model, model)
            ok = False
    return ok


def ensure_directories() -> bool:
    """Create upload and result directories if they don't exist."""
    for d in REQUIRED_DIRS:
        path = Path(d)
        path.mkdir(parents=True, exist_ok=True)
        logger.success("Directory ready: {}", path.resolve())
    return True


def check_colab() -> bool:
    """Non-fatal probe of the optional Colab burst backend.

    Prints MODE: local-only vs hybrid. Never fails startup — a dead
    tunnel must not block the teacher.
    """
    url = os.getenv("COLAB_INFERENCE_URL", "").rstrip("/")
    if not url:
        logger.info("MODE: local-only (COLAB_INFERENCE_URL not set)")
        return True
    try:
        resp = requests.get(f"{url}/health", timeout=8)
        resp.raise_for_status()
        logger.success("MODE: hybrid (local + Colab burst reachable)")
        return True
    except Exception:
        # Fixed string on purpose: the tunnel URL is a bearer secret and
        # must never land in logs (exceptions may echo it).
        logger.warning("MODE: local-only (Colab burst unreachable)")
        return True


def run_checks() -> bool:
    """Run all pre-flight checks. Returns True if all pass."""
    logger.info("Running pre-flight checks...")
    results = [
        check_ollama_reachable(),
        check_models_installed(),
        ensure_directories(),
    ]
    check_colab()  # advisory only — never gates startup
    if all(results):
        logger.success("All pre-flight checks passed")
        return True
    else:
        logger.error("One or more pre-flight checks failed")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Inscrona launcher — pre-flight checks + uvicorn startup"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Run pre-flight checks only, then exit (don't start the server)",
    )
    args = parser.parse_args()

    # Run checks
    ok = run_checks()

    if args.check_only:
        sys.exit(0 if ok else 1)

    if not ok:
        logger.error("Aborting startup due to failed checks")
        sys.exit(1)

    # Start uvicorn
    logger.info("Starting Inscrona on http://localhost:8000/")
    logger.info("Network access: http://0.0.0.0:8000/")
    logger.info("Press Ctrl+C to stop")

    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    main()
