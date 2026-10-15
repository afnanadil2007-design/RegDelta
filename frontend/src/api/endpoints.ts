import { apiFetch } from "@/api/client";
import type {
  AgentStep,
  AnalystDecision,
  AssessmentDetail,
  AssessmentPage,
  CircularDetail,
  CircularPage,
  EvalRun,
  Finding,
  Health,
  PolicyClause,
  PolicyPack,
  SearchRequest,
  SearchResponse,
} from "@/types/api";

export interface CircularQuery {
  q?: string;
  department?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

function query(params: object): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export const endpoints = {
  health: () => apiFetch<Health>("/health"),

  circulars: (params: CircularQuery) => apiFetch<CircularPage>(`/circulars${query(params)}`),
  departments: () => apiFetch<string[]>("/circulars/departments"),
  circular: (id: number) => apiFetch<CircularDetail>(`/circulars/${id}`),

  search: (body: SearchRequest, signal?: AbortSignal) =>
    apiFetch<SearchResponse>("/search", { method: "POST", body: JSON.stringify(body), signal }),

  policyPacks: () => apiFetch<PolicyPack[]>("/policy-packs"),
  policyClauses: (packId: number) => apiFetch<PolicyClause[]>(`/policy-packs/${packId}/clauses`),

  assessments: (params: { limit?: number; offset?: number } = {}) =>
    apiFetch<AssessmentPage>(`/assessments${query(params)}`),
  assessment: (runId: string) => apiFetch<AssessmentDetail>(`/assessments/${runId}`),
  assessmentSteps: (runId: string) => apiFetch<AgentStep[]>(`/assessments/${runId}/steps`),
  startAssessment: (body: { circular_id: number; policy_pack_id: number; as_of?: string | null }) =>
    apiFetch<{ run_id: string }>("/assessments", { method: "POST", body: JSON.stringify(body) }),
  setDecision: (findingId: number, decision: AnalystDecision) =>
    apiFetch<Finding>(`/assessments/findings/${findingId}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    }),

  evalRuns: () => apiFetch<EvalRun[]>("/eval/runs"),
};

export function streamUrl(runId: string): string {
  return `${import.meta.env.VITE_API_BASE ?? "/api"}/assessments/${runId}/stream`;
}
