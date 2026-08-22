import { apiFetch } from "@/api/client";
import type {
  AgentStep,
  Assessment,
  CircularDetail,
  CircularSummary,
  EvalRun,
  Finding,
  PolicyClause,
  PolicyPack,
  SearchRequest,
  SearchResponse,
} from "@/types/api";

export const endpoints = {
  circulars: (params: { limit?: number; department?: string | null } = {}) => {
    const search = new URLSearchParams();
    if (params.limit) search.set("limit", String(params.limit));
    if (params.department) search.set("department", params.department);
    const qs = search.toString();
    return apiFetch<CircularSummary[]>(`/circulars${qs ? `?${qs}` : ""}`);
  },

  departments: () => apiFetch<string[]>("/circulars/departments"),

  circular: (id: number) => apiFetch<CircularDetail>(`/circulars/${id}`),

  search: (body: SearchRequest) =>
    apiFetch<SearchResponse>("/search", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  policyPacks: () => apiFetch<PolicyPack[]>("/policy-packs"),

  policyClauses: (packId: number) =>
    apiFetch<PolicyClause[]>(`/policy-packs/${packId}/clauses`),

  assessments: () => apiFetch<Assessment[]>("/assessments"),

  assessment: (runId: string) => apiFetch<Assessment>(`/assessments/${runId}`),

  assessmentSteps: (runId: string) =>
    apiFetch<AgentStep[]>(`/assessments/${runId}/steps`),

  startAssessment: (body: {
    circular_id: number;
    policy_pack_id: number;
    as_of?: string | null;
  }) =>
    apiFetch<{ run_id: string }>("/assessments", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  setDecision: (findingId: number, decision: string) =>
    apiFetch<Finding>(`/assessments/findings/${findingId}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    }),

  evalRuns: () => apiFetch<EvalRun[]>("/eval/runs"),
};
