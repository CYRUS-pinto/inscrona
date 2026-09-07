"""FastAPI middleware for Inscrona."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config

logger = logging.getLogger("inscora")


def setup_cors(app) -> None:
    """Add CORS middleware."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


async def logging_middleware(request: Request, call_next) -> Response:
    """Log every request with timing."""
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s -> %s (%.0fms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


class InscronaException(Exception):
    """Base application exception."""

    def __init__(self, message: str, status_code: int = 500, detail: Any = None):
        self.message = message
        self.status_code = status_code
        self.detail = detail


class OcrError(InscronaException):
    def __init__(self, message: str, detail: Any = None):
        super().__init__(message, status_code=422, detail=detail)


class GradingError(InscronaException):
    def __init__(self, message: str, detail: Any = None):
        super().__init__(message, status_code=500, detail=detail)


class JobError(InscronaException):
    def __init__(self, message: str, status_code: int = 404, detail: Any = None):
        super().__init__(message, status_code=status_code, detail=detail)


class AnswerKeyError(InscronaException):
    def __init__(self, message: str, status_code: int = 400, detail: Any = None):
        super().__init__(message, status_code=status_code, detail=detail)


async def inscora_exception_handler(request: Request, exc: InscronaException) -> JSONResponse:
    """Handle known application errors."""
    logger.warning("AppError [%s]: %s", exc.status_code, exc.message)
    body: dict[str, Any] = {"error": exc.message}
    if exc.detail is not None:
        body["detail"] = exc.detail
    return JSONResponse(status_code=exc.status_code, content=body)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unexpected errors."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )
