"""Consistent error envelope.

Every error response the API emits has the shape::

    {"error": {"code": "...", "message": "...", "detail": ...}}

Routers raise ``ApiError``; request-validation failures and unexpected
exceptions are rendered into the same envelope by the handlers below.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.logging import get_logger

log = get_logger("app.core.errors")


class ErrorBody(BaseModel):
    code: str
    message: str
    detail: Any | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class ApiError(Exception):
    """Domain error carrying an HTTP status and a stable machine code."""

    def __init__(self, status_code: int, code: str, message: str, detail: Any | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail


def _envelope(code: str, message: str, detail: Any | None = None) -> dict[str, Any]:
    return ErrorEnvelope(error=ErrorBody(code=code, message=message, detail=detail)).model_dump()


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(exc.code, exc.message, exc.detail),
    )


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """422s in the envelope, with one entry per invalid field."""
    fields = [
        {
            "field": ".".join(str(part) for part in error.get("loc", ()) if part != "body"),
            "message": error.get("msg", "invalid value"),
        }
        for error in exc.errors()
    ]
    first = fields[0] if fields else {"field": "", "message": "invalid request"}
    message = f"{first['field']}: {first['message']}" if first["field"] else first["message"]
    return JSONResponse(status_code=422, content=_envelope("invalid_request", message, fields))


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Never leak internals to the client; the full traceback goes to the log.
    log.error(
        "api.unhandled_error",
        exc_info=exc,
        extra={"path": request.url.path, "error_type": type(exc).__name__},
    )
    return JSONResponse(
        status_code=500,
        content=_envelope("internal_error", "An unexpected error occurred."),
    )
