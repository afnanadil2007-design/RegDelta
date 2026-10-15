/**
 * Mirrors backend/app/routers/schemas.py (API v2). A change there is a change
 * here. Offsets are Unicode code-point offsets into the source text; use
 * lib/text.ts to slice them, never String.prototype.slice directly.
 */

export type ImpactType = "NEW_REQUIREMENT" | "MODIFIED" | "CONFLICT" | "ALREADY_COVERED" | "NO_MATCH";

export type QuoteStatus = "VERIFIED" | "FAILED" | "NOT_APPLICABLE";
export type AnalystDecision = "PENDING" | "ACCEPTED" | "REJECTED";
export type AssessmentStatus = "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "CAPPED";
export type StepStatus = "RUNNING" | "OK" | "ERROR";
export type RetrievalMode = "dense" | "lexical" | "hybrid" | "hybrid_rerank";
export type ScoreKind = "cosine_similarity" | "ts_rank_cd" | "rrf" | "cross_encoder_sigmoid";

export interface ErrorEnvelope {
  error: { code: string; message: string; detail?: unknown };
}

// --- circulars -------------------------------------------------------------

export interface CircularSummary {
  id: number;
  circular_number: string;
  title: string;
  issue_date: string | null;
  department: string | null;
  doc_type: string;
  page_count: number;
  vision_page_count: number;
  source_url: string | null;
  is_synthetic: boolean;
  obligation_count: number;
  ingested_at: string;
}

export interface CircularPage {
  items: CircularSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface Paragraph {
  id: number;
  order_index: number;
  para_number: string | null;
  heading_path: string | null;
  text: string;
  char_start: number;
  char_end: number;
  page_number: number | null;
  extraction_method: string;
  text_quality_score: number | null;
}

export interface Obligation {
  id: number;
  paragraph_id: number;
  text: string;
  actor: string | null;
  action: string | null;
  deadline: string | null;
  condition: string | null;
  modality: string | null;
  char_start: number;
  char_end: number;
  model_confidence: number | null;
  extractor: string | null;
}

export interface Citation {
  id: number;
  citing_circular_id: number;
  citing_circular_number: string | null;
  citing_paragraph_id: number;
  raw_reference: string;
  cited_circular_id: number | null;
  cited_circular_number: string | null;
  cited_circular_title: string | null;
  resolved: boolean;
  resolution_method: string;
  char_start: number | null;
  char_end: number | null;
}

export interface Supersession {
  id: number;
  direction: "outgoing" | "incoming";
  superseding_circular_id: number;
  superseding_number: string | null;
  superseding_title: string | null;
  superseded_circular_id: number | null;
  superseded_number: string | null;
  superseded_title: string | null;
  supersession_type: "supersedes" | "rescinds" | "amends" | "partial";
  removes_from_force: boolean;
  effective_date: string | null;
  resolved: boolean;
  raw_reference: string;
  evidence_paragraph_id: number | null;
}

export interface CircularDetail {
  circular: CircularSummary;
  provenance: { checksum: string | null; pdf_filename: string | null; ingested_at: string };
  full_text: string;
  paragraphs: Paragraph[];
  obligations: Obligation[];
  citations: Citation[];
  cited_by: Citation[];
  supersessions: Supersession[];
}

// --- search ------------------------------------------------------------------

export interface SearchRequest {
  query: string;
  mode?: RetrievalMode;
  as_of?: string | null;
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
  refused: boolean;
  top_score: number | null;
  threshold: number | null;
  score_kind: ScoreKind;
  excluded_by_temporal_filter: { circular_id: number; circular_number: string; title: string }[];
  elapsed_ms: number;
}

// --- assessments -------------------------------------------------------------

export interface ProviderInfo {
  name: string;
  model: string | null;
  deterministic: boolean;
}

export interface Usage {
  total_tokens: number;
  estimated_cost_usd: number | null;
  cost_complete: boolean;
  unpriced_calls: number;
}

export interface FindingCounts {
  total: number;
  assessed_obligations: number;
  quote_verified: number;
  quote_failed: number;
  quote_not_applicable: number;
  by_impact: Record<ImpactType, number>;
  decision_pending: number;
  decision_accepted: number;
  decision_rejected: number;
}

export interface AssessmentSummary {
  id: number;
  run_id: string;
  circular_id: number;
  circular_number: string | null;
  circular_title: string | null;
  policy_pack_id: number;
  policy_pack_name: string | null;
  policy_pack_version: string | null;
  as_of: string | null;
  status: AssessmentStatus;
  status_detail: string | null;
  provider: ProviderInfo | null;
  graph_version: string | null;
  usage: Usage;
  failed_tasks: number;
  obligation_count: number;
  counts: FindingCounts;
  created_at: string;
  completed_at: string | null;
}

export interface Finding {
  id: number;
  circular_id: number;
  obligation_id: number;
  obligation_text: string;
  obligation_char_start: number;
  obligation_char_end: number;
  policy_clause_id: number | null;
  clause_number: string | null;
  clause_heading: string | null;
  clause_text: string | null;
  clause_char_start: number | null;
  impact_type: ImpactType;
  rationale: string;
  model_confidence: number | null;
  circular_span_start: number | null;
  circular_span_end: number | null;
  clause_span_start: number | null;
  clause_span_end: number | null;
  quote_status: QuoteStatus;
  verification_note: string | null;
  /** For a FAILED finding: the quote that could not be found in its source. */
  unlocated_quote: string | null;
  verification_attempts: number;
  analyst_decision: AnalystDecision;
  decided_at: string | null;
}

export interface AssessmentDetail extends AssessmentSummary {
  memo: string | null;
  findings: Finding[];
}

export interface AssessmentPage {
  items: AssessmentSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface AgentStep {
  seq: number;
  node: string;
  status: StepStatus;
  summary: string | null;
  tokens: number;
  cost_usd: number | null;
  latency_ms: number | null;
  error: string | null;
  obligation_id: number | null;
  clause_number: string | null;
  attempt: number | null;
  started_at: string;
  finished_at: string | null;
}

// --- policy ------------------------------------------------------------------

export interface PolicyPack {
  id: number;
  name: string;
  version: string;
  description: string | null;
  is_synthetic: boolean;
  clause_count: number;
  created_at: string;
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

// --- evaluation and health ---------------------------------------------------

export interface EvalMetric {
  metric_name: string;
  metric_value: number;
  subset: string | null;
  k: number | null;
  detail: Record<string, unknown> | null;
}

export interface EvalRun {
  id: number;
  suite: string;
  mode: string | null;
  git_sha: string;
  dataset: string | null;
  config: Record<string, unknown> | null;
  notes: string | null;
  started_at: string;
  finished_at: string | null;
  results: EvalMetric[];
}

export interface Health {
  status: "ok";
  env: string;
  database: "up" | "down";
  schema_revision: string | null;
  provider: {
    name: string;
    model: string;
    deterministic: boolean;
    ready: boolean;
    reason: string | null;
  };
}
