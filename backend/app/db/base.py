"""Declarative base for the ORM models in ``app.db.models``."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
