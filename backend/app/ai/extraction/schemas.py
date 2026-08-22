"""Pydantic schemas for structured model output.

These are the contract between the model and the database. Every model call
that produces structure validates against one of these; a violation triggers a
single repair attempt with the validation error fed back, and then an
extraction failure is recorded rather than bad data being stored.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.db.models.enums import ImpactType


class ExtractedObligation(BaseModel):
    """One obligation as the model reports it, before span resolution."""

    text: str = Field(min_length=8, description="verbatim substring of the paragraph")
    actor: str | None = None
    action: str | None = None
    modality: Literal["shall", "must", "may", "should"] | None = None
    deadline: str | None = None
    condition: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("text")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class ObligationExtraction(BaseModel):
    obligations: list[ExtractedObligation] = Field(default_factory=list)


class JudgedImpact(BaseModel):
    """The judge_impact node's required output shape.

    Spans are quoted text, not offsets: the model cannot count characters
    reliably, but it can quote. Offsets are resolved from these quotes by
    code that can be verified.
    """

    impact_type: ImpactType
    rationale: str = Field(min_length=20)
    confidence: float = Field(ge=0.0, le=1.0)
    circular_span: str = Field(
        default="", description="verbatim quote from the circular supporting the verdict"
    )
    clause_span: str = Field(
        default="", description="verbatim quote from the policy clause, empty for NO_MATCH"
    )


def json_schema_for(model: type[BaseModel]) -> dict:
    """A JSON Schema the gateway can pass as an output constraint.

    Structured outputs reject unsupported keywords, so the schema is emitted
    with ``additionalProperties: false`` and without the ``$defs`` indirection
    that Pydantic produces for nested enums.
    """
    schema = model.model_json_schema()
    return _inline_defs(schema)


def _inline_defs(schema: dict) -> dict:
    """Resolve local ``$ref``s so the schema is self-contained."""
    defs = schema.pop("$defs", {})

    def walk(node: object) -> object:
        if isinstance(node, dict):
            if "$ref" in node:
                ref = node["$ref"].rsplit("/", 1)[-1]
                target = defs.get(ref, {})
                merged = {k: v for k, v in node.items() if k != "$ref"}
                return walk({**target, **merged})
            resolved = {k: walk(v) for k, v in node.items()}
            if resolved.get("type") == "object" and "additionalProperties" not in resolved:
                resolved["additionalProperties"] = False
            return resolved
        if isinstance(node, list):
            return [walk(item) for item in node]
        return node

    return walk(schema)  # type: ignore[return-value]
