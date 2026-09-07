"""
Inscora — FastAPI Application
OCR → Structural Analysis → Grading → Score + Feedback
"""
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import OLLAMA_HOST, OCR_MODEL, GRADE_MODEL, FEEDBACK_MODEL
from app.middleware import (
    setup_cors,
    logging_middleware,
    inscora_exception_handler,
    unhandled_exception_handler,
    InscronaException,
)
from app.routes import router
from app.jobs import JobManager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle."""
    # ── Startup ──────────────────────────────────────────────────────
    # Initialise the in-memory job manager (singleton per process).
    app.state.job_manager = JobManager()

    # Pre-warm models so the first real request isn't cold.
    # We ping Ollama to confirm the server is reachable; the actual
    # model loading happens lazily inside ollama_client per-request.
    try:
        import httpx

        async with httpx.AsyncClient(    base_url=OLLAMA_HOST, timeout=5) as c:
            resp = await c.get("/api/tags")
            resp.raise_for_status()
    except Exception as exc:
        # Non-fatal: Ollama might start later; we log and continue.
        print(f"[startup] Warning: Ollama ping failed ({exc}); will retry on first request.")

    print(
        f"[startup] Inscora ready — "
        f"ocr={OCR_MODEL}  grading={GRADE_MODEL}  feedback={FEEDBACK_MODEL}"
    )

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    print("[shutdown] Inscora stopping.")


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI(
        title="Inscora",
        version="0.1.0",
        description="AI-powered exam correction engine",
        lifespan=lifespan,
    )

    # Middleware (order matters: last added = first executed)
    setup_cors(app)
    app.middleware("http")(logging_middleware)

    # Exception handlers
    app.add_exception_handler(InscronaException, inscora_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)  # type: ignore[arg-type]

    # Routes
    app.include_router(router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
