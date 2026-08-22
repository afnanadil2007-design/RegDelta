// TypeScript mirrors of the backend Pydantic models in app/routers/schemas.py.
// Kept in sync by hand; a change there is a change to this contract.
// No `any` in this file, ever.

export interface HealthResponse {
  status: string;
  env: string;
  database: "up" | "down";
}

export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    detail?: unknown;
  };
}

// --- circulars ---------------------------------------------------------

export interface CircularSummary {
  id: number;
  circular_number: string;
  title: string;
  issue_date: string | null;
  department: string | null;
  doc_type: string;
  page_count: number;
  vision_page_count: number;
}

export type ExtractionMethod = "text" | "vision";

export interface Paragraph {
  id: number;
  order_index: number;
  para_number: string | null;
  heading_path: string | null;
  text: string;
  char_start: number;
  char_end: number;
  page_number: number | null;
  extraction_method: ExtractionMethod;
}

export interface Obligation {
  id: number;
  text: string;
  actor: string | null;
  action: string | null;
  deadline: string | null;
  modality: string | null;
  char_start: number;
  char_end: number;
  confidence: number | null;
}

export interface Citation {
  id: number;
  raw_reference: string;
  cited_circular_id: number | null;
  cited_circular_number: string | null;
  resolved: boolean;
  resolution_method: string;
}

export interface Supersession {
  id: number;
  superseding_circular_id: number;
  superseding_number: string | null;
  superseded_circular_id: number | null;
  superseded_number: string | null;
  supersession_type: string;
  effective_date: string | null;
  evidence_paragraph_id: number | null;
}

export interface CircularDetail {
  circular: CircularSummary;
  full_text: string;
  paragraphs: Paragraph[];
  obligations: Obligation[];
  citations: Citation[];
  supersessions: Supersession[];
}

// --- search ------------------------------------------------------------

export type RetrievalMode = "dense" | "lexical" | "hybrid" | "hybrid_rerank";

export interface SearchRequest {
  query: string;
  as_of?: string | null;
  mode?: RetrievalMode;
  department?: string | null;
  date_from?: string | null;
  date_to?: string | null;
  doc_type?: string | null;
  top_k?: number | null;
}

export interface SearchHit {
  chunk_id: number;
  circular_id: number;
  circular_number: string;
  circular_title: string;
  issue_date: string | null;
  text: string;
  char_start: number;
  char_end: number;
  heading_path: string | null;
  score: number;
  dense_rank: number | null;
  lexical_rank: number | null;
  rrf_score: number | null;
  rerank_score: number | null;
}

export interface SearchResponse {
  mode: RetrievalMode;
  hits: SearchHit[];
  below_threshold: boolean;
  top_score: number | null;
  excluded_by_temporal_filter: number[];
}

// --- assessments -------------------------------------------------------

export type ImpactType =
  | "NEW_REQUIREMENT"
  | "MODIFIED"
  | "CONFLICT"
  | "ALREADY_COVERED"
  | "NO_MATCH";

export type AnalystDecision = "PENDING" | "ACCEPTED" | "REJECTED";

export type AssessmentStatus =
  | "PENDING"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "CAPPED";

export interface Finding {
  id: number;
  obligation_id: number;
  obligation_text: string | null;
  policy_clause_id: number | null;
  clause_number: string | null;
  clause_text: string | null;
  impact_type: ImpactType;
  rationale: string;
  confidence: number;
  circular_span_start: number | null;
  circular_span_end: number | null;
  clause_span_start: number | null;
  clause_span_end: number | null;
  verified: boolean;
  verification_attempts: number;
  analyst_decision: AnalystDecision;
}

export interface Assessment {
  id: number;
  run_id: string;
  circular_id: number;
  circular_number: string | null;
  policy_pack_id: number;
  status: AssessmentStatus;
  error_reason: string | null;
  memo: string | null;
  total_tokens: number;
  total_cost_usd: number;
  created_at: string;
  completed_at: string | null;
  findings: Finding[];
}

export interface AgentStep {
  seq: number;
  node: string;
  status: "RUNNING" | "OK" | "ERROR";
  summary: string | null;
  tokens: number;
  latency_ms: number | null;
}

// --- policy ------------------------------------------------------------

export interface PolicyPack {
  id: number;
  name: string;
  version: string;
  description: string | null;
  is_synthetic: boolean;
  clause_count: number;
}

export interface PolicyClause {
  id: number;
  clause_number: string;
  heading: string | null;
  heading_path: string | null;
  text: string;
  char_start: number;
  char_end: number;
}

// --- evaluation --------------------------------------------------------

export interface EvalMetric {
  metric_name: string;
  metric_value: number;
  subset: string | null;
  k: number | null;
}

export interface EvalRun {
  id: number;
  suite: string;
  mode: string | null;
  git_sha: string;
  dataset: string | null;
  started_at: string;
  finished_at: string | null;
  results: EvalMetric[];
}
