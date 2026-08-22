"""Pydantic request/response models for the HTTP layer.

Routers speak only these types. The frontend's TypeScript mirrors them, so a
change here is a change to the API contract.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.db.models.enums import AnalystDecision, ImpactType, RetrievalMode

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


class ObligationOut(BaseModel):
    id: int
    text: str
    actor: str | None
    action: str | None
    deadline: str | None
    modality: str | None
    char_start: int
    char_end: int
    confidence: float | None


class CitationOut(BaseModel):
    id: int
    raw_reference: str
    cited_circular_id: int | None
    cited_circular_number: str | None
    resolved: bool
    resolution_method: str


class SupersessionOut(BaseModel):
    id: int
    superseding_circular_id: int
    superseding_number: str | None
    superseded_circular_id: int | None
    superseded_number: str | None
    supersession_type: str
    effective_date: date | None
    evidence_paragraph_id: int | None


class CircularDetail(BaseModel):
    circular: CircularSummary
    full_text: str
    paragraphs: list[ParagraphOut]
    obligations: list[ObligationOut]
    citations: list[CitationOut]
    supersessions: list[SupersessionOut]


# --- search -------------------------------------------------------------


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    as_of: date | None = None
    mode: RetrievalMode = RetrievalMode.HYBRID_RERANK
    department: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    doc_type: str | None = None
    top_k: int | None = None


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


class SearchResponse(BaseModel):
    mode: RetrievalMode
    hits: list[SearchHit]
    below_threshold: bool
    top_score: float | None
    excluded_by_temporal_filter: list[int]


# --- assessments --------------------------------------------------------


class CreateAssessmentRequest(BaseModel):
    circular_id: int
    policy_pack_id: int
    as_of: date | None = None


class CreateAssessmentResponse(BaseModel):
    run_id: uuid.UUID


class FindingOut(BaseModel):
    id: int
    obligation_id: int
    obligation_text: str | None
    policy_clause_id: int | None
    clause_number: str | None
    clause_text: str | None
    impact_type: ImpactType
    rationale: str
    confidence: float
    circular_span_start: int | None
    circular_span_end: int | None
    clause_span_start: int | None
    clause_span_end: int | None
    verified: bool
    verification_attempts: int
    analyst_decision: AnalystDecision


class AssessmentOut(BaseModel):
    id: int
    run_id: uuid.UUID
    circular_id: int
    circular_number: str | None
    policy_pack_id: int
    status: str
    error_reason: str | None
    memo: str | None
    total_tokens: int
    total_cost_usd: float
    created_at: datetime
    completed_at: datetime | None
    findings: list[FindingOut]


class DecisionRequest(BaseModel):
    decision: Literal["ACCEPTED", "REJECTED", "PENDING"]


class AgentStepOut(BaseModel):
    """One SSE event / timeline row."""

    seq: int
    node: str
    status: str
    summary: str | None
    tokens: int
    latency_ms: int | None


# --- policy packs -------------------------------------------------------


class PolicyPackOut(BaseModel):
    id: int
    name: str
    version: str
    description: str | None
    is_synthetic: bool
    clause_count: int


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


class EvalRunOut(BaseModel):
    id: int
    suite: str
    mode: str | None
    git_sha: str
    dataset: str | None
    started_at: datetime
    finished_at: datetime | None
    results: list[EvalMetricOut]
