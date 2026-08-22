"""Consistent error envelope.

Every error response the API emits has the shape::

    {"error": {"code": "...", "message": "...", "detail": ...}}

Routers raise ``ApiError``; a single exception handler renders the envelope.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


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


async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    # Never leak internals; the message is generic, the code is stable.
    return JSONResponse(
        status_code=500,
        content=_envelope("internal_error", "An unexpected error occurred."),
    )
