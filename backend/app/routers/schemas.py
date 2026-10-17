"""Pydantic request/response models for the HTTP layer.

Routers speak only these types, and ``frontend/src/types/api.ts`` mirrors
them, so a change here is a change to the API contract.

Naming carries meaning the UI must preserve: ``quote_status`` says whether a
finding's quotes were found verbatim in the source (not whether the judgement
is right), ``model_confidence`` is the judge's own uncalibrated score, and an
estimated cost is ``None`` — unknown — when a model had no list price.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.ai.retrieval.pipeline import ScoreKind
from app.db.models.enums import (
    AnalystDecision,
    AssessmentStatus,
    ImpactType,
    QuoteStatus,
    RetrievalMode,
    StepStatus,
)

# --- circulars ----------------------------------------------------------


class CircularSummary(BaseModel):
    id: int
    circular_number: str
    title: str
    issue_date: date | None
    department: str | None
    doc_type: str
    page_count: int
    vision_page_count: int
    source_url: str | None
    # True for documents produced by ingestion/generate_corpus.py.
    is_synthetic: bool
    obligation_count: int
    ingested_at: datetime


class CircularPage(BaseModel):
    items: list[CircularSummary]
    total: int
    limit: int
    offset: int


class CircularProvenance(BaseModel):
    checksum: str | None
    pdf_filename: str | None
    ingested_at: datetime


class ParagraphOut(BaseModel):
    id: int
    order_index: int
    para_number: str | None
    heading_path: str | None
    text: str
    char_start: int
    char_end: int
    page_number: int | None
    extraction_method: str
    text_quality_score: float | None


class ObligationOut(BaseModel):
    id: int
    paragraph_id: int
    text: str
    actor: str | None
    action: str | None
    deadline: str | None
    condition: str | None
    modality: str | None
    char_start: int
    char_end: int
    model_confidence: float | None
    extractor: str | None


class CitationOut(BaseModel):
    id: int
    citing_circular_id: int
    citing_circular_number: str | None
    citing_paragraph_id: int
    raw_reference: str
    cited_circular_id: int | None
    cited_circular_number: str | None
    cited_circular_title: str | None
    resolved: bool
    resolution_method: str
    char_start: int | None
    char_end: int | None


class SupersessionOut(BaseModel):
    id: int
    # Relative to the circular being viewed.
    direction: Literal["outgoing", "incoming"]
    superseding_circular_id: int
    superseding_number: str | None
    superseding_title: str | None
    superseded_circular_id: int | None
    superseded_number: str | None
    superseded_title: str | None
    supersession_type: str
    # Only supersedes/rescinds edges take the earlier circular out of force.
    removes_from_force: bool
    effective_date: date | None
    resolved: bool
    raw_reference: str
    evidence_paragraph_id: int | None


class CircularDetail(BaseModel):
    circular: CircularSummary
    provenance: CircularProvenance
    full_text: str
    paragraphs: list[ParagraphOut]
    obligations: list[ObligationOut]
    citations: list[CitationOut]
    cited_by: list[CitationOut]
    supersessions: list[SupersessionOut]


# --- search -------------------------------------------------------------


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    as_of: date | None = None
    mode: RetrievalMode = RetrievalMode.HYBRID_RERANK
    department: str | None = Field(default=None, max_length=64)
    date_from: date | None = None
    date_to: date | None = None
    doc_type: str | None = Field(default=None, max_length=32)
    top_k: int | None = Field(default=None, ge=1, le=50)

    @model_validator(mode="after")
    def _ordered_dates(self) -> SearchRequest:
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        if not self.query.strip():
            raise ValueError("query must contain non-whitespace characters")
        return self


class SearchHit(BaseModel):
    chunk_id: int
    circular_id: int
    circular_number: str
    circular_title: str
    issue_date: date | None
    text: str
    char_start: int
    char_end: int
    heading_path: str | None
    score: float
    # Per-retriever ranks, so the UI can show fusion contributions.
    dense_rank: int | None
    lexical_rank: int | None
    rrf_score: float | None
    rerank_score: float | None


class ExcludedCircular(BaseModel):
    circular_id: int
    circular_number: str
    title: str


class SearchResponse(BaseModel):
    mode: RetrievalMode
    hits: list[SearchHit]
    # True when the reranked mode's best score was below the threshold: the
    # pipeline declined to answer rather than return weak passages.
    refused: bool
    top_score: float | None
    # The threshold that applies to this mode; None for modes without one.
    threshold: float | None
    score_kind: ScoreKind
    excluded_by_temporal_filter: list[ExcludedCircular]
    elapsed_ms: int


# --- assessments --------------------------------------------------------


class CreateAssessmentRequest(BaseModel):
    circular_id: int = Field(ge=1)
    policy_pack_id: int = Field(ge=1)
    as_of: date | None = None


class CreateAssessmentResponse(BaseModel):
    run_id: uuid.UUID


class ProviderOut(BaseModel):
    name: str
    model: str | None
    deterministic: bool


class UsageOut(BaseModel):
    total_tokens: int
    # List-price estimate for priced calls; None when no call was priced.
    estimated_cost_usd: float | None
    # False when some calls used a model with no list price.
    cost_complete: bool
    unpriced_calls: int


class FindingCountsOut(BaseModel):
    total: int
    assessed_obligations: int
    quote_verified: int
    quote_failed: int
    quote_not_applicable: int
    by_impact: dict[ImpactType, int]
    decision_pending: int
    decision_accepted: int
    decision_rejected: int


class AssessmentSummary(BaseModel):
    id: int
    run_id: uuid.UUID
    circular_id: int
    circular_number: str | None
    circular_title: str | None
    policy_pack_id: int
    policy_pack_name: str | None
    policy_pack_version: str | None
    as_of: date | None
    status: AssessmentStatus
    # Why a run failed or was capped, or a note on a completed run.
    status_detail: str | None
    provider: ProviderOut | None
    graph_version: str | None
    usage: UsageOut
    failed_tasks: int
    obligation_count: int
    counts: FindingCountsOut
    created_at: datetime
    completed_at: datetime | None


class FindingOut(BaseModel):
    id: int
    circular_id: int
    obligation_id: int
    obligation_text: str
    obligation_char_start: int
    obligation_char_end: int
    policy_clause_id: int | None
    clause_number: str | None
    clause_heading: str | None
    clause_text: str | None
    clause_char_start: int | None
    impact_type: ImpactType
    rationale: str
    model_confidence: float | None
    circular_span_start: int | None
    circular_span_end: int | None
    clause_span_start: int | None
    clause_span_end: int | None
    quote_status: QuoteStatus
    verification_note: str | None
    # FAILED only: the quote the judge claimed that is not in its source.
    unlocated_quote: str | None
    verification_attempts: int
    analyst_decision: AnalystDecision
    decided_at: datetime | None


class AssessmentDetail(AssessmentSummary):
    memo: str | None
    findings: list[FindingOut]


class AssessmentPage(BaseModel):
    items: list[AssessmentSummary]
    total: int
    limit: int
    offset: int


class DecisionRequest(BaseModel):
    decision: AnalystDecision


class AgentStepOut(BaseModel):
    """One SSE ``step`` event / timeline row."""

    seq: int
    node: str
    status: StepStatus
    summary: str | None
    tokens: int
    # None when a call in the step had no list price.
    cost_usd: float | None
    latency_ms: int | None
    error: str | None
    obligation_id: int | None
    clause_number: str | None
    attempt: int | None
    started_at: datetime
    finished_at: datetime | None


# --- policy packs -------------------------------------------------------


class PolicyPackOut(BaseModel):
    id: int
    name: str
    version: str
    description: str | None
    is_synthetic: bool
    clause_count: int
    created_at: datetime


class PolicyClauseOut(BaseModel):
    id: int
    clause_number: str
    heading: str | None
    heading_path: str | None
    text: str
    char_start: int
    char_end: int


# --- evaluation ---------------------------------------------------------


class EvalMetricOut(BaseModel):
    metric_name: str
    metric_value: float
    subset: str | None
    k: int | None
    detail: dict | None


class EvalRunOut(BaseModel):
    id: int
    suite: str
    mode: str | None
    git_sha: str
    dataset: str | None
    config: dict | None
    notes: str | None
    started_at: datetime
    finished_at: datetime | None
    results: list[EvalMetricOut]


# --- health -------------------------------------------------------------


class ProviderStatus(BaseModel):
    name: str
    model: str
    deterministic: bool
    ready: bool
    reason: str | None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    env: str
    database: Literal["up", "down"]
    schema_revision: str | None
    provider: ProviderStatus
