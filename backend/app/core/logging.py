"""Structured JSON logging.

Every log line is a single JSON object. A ``run_id`` field is always present so
ingestion, retrieval, and agent runs can be traced end-to-end; when no run is
active it is the literal ``"-"``. Set the current run id via ``bind_run_id``.
"""

from __future__ import annotations

import contextvars
import logging

from pythonjsonlogger import jsonlogger

# Propagated through async tasks; each graph/ingestion run binds its own id.
_run_id: contextvars.ContextVar[str] = contextvars.ContextVar("run_id", default="-")


def bind_run_id(run_id: str) -> None:
    _run_id.set(run_id)


class _RunIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = _run_id.get()
        return True


def configure_logging(level: str = "INFO") -> None:
    """Install a single JSON handler on the root logger (idempotent)."""
    root = logging.getLogger()
    root.setLevel(level)
    # Avoid duplicate handlers under uvicorn reload.
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler()
    handler.addFilter(_RunIdFilter())
    handler.setFormatter(
        jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(run_id)s %(message)s",
            rename_fields={"asctime": "ts", "levelname": "level", "name": "logger"},
        )
    )
    root.addHandler(handler)

    # Tame noisy libraries; their records still flow through the JSON handler.
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
