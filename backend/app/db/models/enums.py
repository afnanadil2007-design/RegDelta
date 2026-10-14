"""Domain vocabularies shared by the ORM, the API, and the pipeline.

Postgres stores each enum's *values* (see ``db_enum``), so the labels in the
database, the JSON the API emits, and the strings the ingestion pipeline writes
are the same strings. Member order is the label order of the native enum types
created in migration ``0002_core_schema``; append new members, never reorder.
"""

from __future__ import annotations

from enum import Enum, StrEnum

from sqlalchemy import Enum as SAEnum


class ExtractionMethod(StrEnum):
    """How a paragraph's text was obtained from its PDF page."""

    TEXT = "text"
    VISION = "vision"


class ResolutionMethod(StrEnum):
    """How a citation's reference string was bound to a circular, if at all."""

    REGEX = "regex"
    DATE = "date"
    LLM = "llm"
    UNRESOLVED = "unresolved"


class SupersessionType(StrEnum):
    """What a later circular asserts about an earlier one.

    Only ``SUPERSEDES`` and ``RESCINDS`` take the earlier circular out of
    force; ``AMENDS`` and ``PARTIAL`` leave it in force as modified.
    """

    SUPERSEDES = "supersedes"
    RESCINDS = "rescinds"
    AMENDS = "amends"
    PARTIAL = "partial"


class ImpactType(StrEnum):
    """The judged effect of one obligation on one policy clause."""

    NEW_REQUIREMENT = "NEW_REQUIREMENT"
    MODIFIED = "MODIFIED"
    CONFLICT = "CONFLICT"
    ALREADY_COVERED = "ALREADY_COVERED"
    NO_MATCH = "NO_MATCH"


class AssessmentStatus(StrEnum):
    """Lifecycle of an assessment and of its agent run.

    ``COMPLETED``, ``FAILED`` and ``CAPPED`` are terminal. ``CAPPED`` means a
    hard limit stopped the run; whatever it produced before then is kept.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CAPPED = "CAPPED"


TERMINAL_STATUSES = frozenset(
    {AssessmentStatus.COMPLETED, AssessmentStatus.FAILED, AssessmentStatus.CAPPED}
)


class StepStatus(StrEnum):
    """State of one traced graph-node execution."""

    RUNNING = "RUNNING"
    OK = "OK"
    ERROR = "ERROR"


class AnalystDecision(StrEnum):
    """A reviewer's call on a finding. Not an independent research label."""

    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class EvalSuite(StrEnum):
    RETRIEVAL = "retrieval"
    EXTRACTION = "extraction"
    GROUNDEDNESS = "groundedness"
    REFUSAL = "refusal"
    PERFORMANCE = "performance"


class RetrievalMode(StrEnum):
    """The four retrieval configurations the ablation compares."""

    DENSE = "dense"
    LEXICAL = "lexical"
    HYBRID = "hybrid"
    HYBRID_RERANK = "hybrid_rerank"


def db_enum(enum_cls: type[Enum], name: str) -> SAEnum:
    """A native Postgres enum that persists member values, not member names.

    SQLAlchemy defaults to names; for ``ExtractionMethod.VISION`` that would
    store ``'VISION'`` while the pipeline and API speak ``'vision'``.
    """
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=lambda members: [member.value for member in members],
    )
