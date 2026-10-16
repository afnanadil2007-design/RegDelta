import type {
  AnalystDecision,
  AssessmentStatus,
  ImpactType,
  ProviderInfo,
  QuoteStatus,
  RetrievalMode,
  ScoreKind,
} from "@/types/api";

export const IMPACT_ORDER: ImpactType[] = [
  "CONFLICT",
  "MODIFIED",
  "NEW_REQUIREMENT",
  "ALREADY_COVERED",
  "NO_MATCH",
];

export const IMPACT: Record<ImpactType, { label: string; short: string; meaning: string; tone: string }> = {
  CONFLICT: {
    label: "Conflict",
    short: "Conflict",
    meaning: "Following the clause would breach the obligation.",
    tone: "conflict",
  },
  MODIFIED: {
    label: "Modified",
    short: "Modified",
    meaning: "The clause covers this but its specifics differ.",
    tone: "modified",
  },
  NEW_REQUIREMENT: {
    label: "New requirement",
    short: "New",
    meaning: "The clause does not address this requirement.",
    tone: "new",
  },
  ALREADY_COVERED: {
    label: "Already covered",
    short: "Covered",
    meaning: "The clause already satisfies the obligation.",
    tone: "covered",
  },
  NO_MATCH: {
    label: "No match",
    short: "No match",
    meaning: "The clause, or every clause, is not relevant to this obligation.",
    tone: "none",
  },
};

export const QUOTE_STATUS: Record<QuoteStatus, { label: string; detail: string }> = {
  VERIFIED: {
    label: "Quotes located",
    detail:
      "Each quote was found verbatim in its source. This checks the text exists, not that the interpretation is right.",
  },
  FAILED: {
    label: "Quote not located",
    detail: "A quote could not be found in its source, so the evidence this interpretation cites is missing.",
  },
  NOT_APPLICABLE: {
    label: "No quote to check",
    detail: "No policy clause cleared the relevance threshold, so no judgement was made.",
  },
};

export const DECISION: Record<AnalystDecision, string> = {
  PENDING: "Not yet decided",
  ACCEPTED: "Accepted",
  REJECTED: "Rejected",
};

export const RUN_STATUS: Record<AssessmentStatus, { label: string; meaning: string }> = {
  PENDING: { label: "Queued", meaning: "Waiting to start." },
  RUNNING: { label: "Running", meaning: "The agent is working through the obligations." },
  COMPLETED: { label: "Completed", meaning: "Every obligation was processed." },
  CAPPED: {
    label: "Stopped at a limit",
    meaning: "A call, token, or time limit stopped the run; findings so far are kept.",
  },
  FAILED: { label: "Failed", meaning: "The run stopped on an error." },
};

export const MODE: Record<RetrievalMode, { label: string; note: string }> = {
  hybrid: {
    label: "Hybrid",
    note: "Dense and lexical rankings fused by rank. Fast; never refuses.",
  },
  hybrid_rerank: {
    label: "Hybrid + rerank",
    note: "Re-scores up to 50 passages with a cross-encoder on the CPU. Slow on modest hardware; the only mode that refuses weak results.",
  },
  lexical: { label: "Lexical", note: "Postgres full-text ranking. Best for reference numbers." },
  dense: { label: "Dense", note: "Embedding similarity only." },
};

export const SCORE: Record<ScoreKind, string> = {
  cosine_similarity: "Cosine similarity",
  ts_rank_cd: "Full-text rank (unbounded)",
  rrf: "Reciprocal-rank fusion score",
  cross_encoder_sigmoid: "Cross-encoder score (0 to 1, uncalibrated)",
};

/** "Rule-based judge (deterministic demo)" or "groq · openai/gpt-oss-20b". */
export function providerLabel(provider: ProviderInfo | null): string {
  if (!provider) return "Provider not recorded";
  if (provider.deterministic) return "Rule-based judge (deterministic demo)";
  return provider.model ? `${provider.name} · ${provider.model}` : provider.name;
}

/** Model-stated scores are shown as such, never as calibrated confidence. */
export function modelScoreLabel(score: number | null, deterministic: boolean): string | null {
  if (score === null) return null;
  return deterministic
    ? `Term overlap ${score.toFixed(2)} (rule score)`
    : `Model-stated ${score.toFixed(2)}, uncalibrated`;
}
