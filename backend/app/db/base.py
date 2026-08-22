"""Declarative base for ORM models.

Models are added in Stage 2. Alembic imports this module's ``Base.metadata``
for autogeneration, so it must import every model package once they exist.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
