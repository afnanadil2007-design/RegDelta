import { keepPreviousData, useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";

import { endpoints, type CircularQuery } from "@/api/endpoints";
import type { AnalystDecision, AssessmentDetail, Finding, SearchRequest } from "@/types/api";

// Corpus data changes only on re-ingest, so it can be cached generously.
const CORPUS_STALE = 5 * 60_000;

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: endpoints.health,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

export function useCirculars(params: CircularQuery) {
  return useQuery({
    queryKey: ["circulars", params],
    queryFn: () => endpoints.circulars(params),
    staleTime: CORPUS_STALE,
    placeholderData: keepPreviousData,
  });
}

export function useDepartments() {
  return useQuery({ queryKey: ["departments"], queryFn: endpoints.departments, staleTime: CORPUS_STALE });
}

export function useCircular(id: number | null) {
  return useQuery({
    queryKey: ["circular", id],
    queryFn: () => endpoints.circular(id as number),
    enabled: id !== null,
    staleTime: CORPUS_STALE,
  });
}

/** Several circulars at once (the neighbours on a timeline); shares the detail cache. */
export function useCircularsById(ids: number[]) {
  return useQueries({
    queries: ids.map((id) => ({
      queryKey: ["circular", id],
      queryFn: () => endpoints.circular(id),
      staleTime: CORPUS_STALE,
    })),
  });
}

export function usePolicyPacks() {
  return useQuery({ queryKey: ["policy-packs"], queryFn: endpoints.policyPacks, staleTime: CORPUS_STALE });
}

export function usePolicyClauses(packId: number | null) {
  return useQuery({
    queryKey: ["policy-clauses", packId],
    queryFn: () => endpoints.policyClauses(packId as number),
    enabled: packId !== null,
    staleTime: CORPUS_STALE,
  });
}

export function useAssessments(params: { limit?: number; offset?: number } = {}) {
  return useQuery({
    queryKey: ["assessments", params],
    queryFn: () => endpoints.assessments(params),
    staleTime: 5_000,
    placeholderData: keepPreviousData,
  });
}

export function useAssessment(runId: string | null) {
  return useQuery({
    queryKey: ["assessment", runId],
    queryFn: () => endpoints.assessment(runId as string),
    enabled: runId !== null,
    staleTime: 5_000,
    // While a run is in flight, findings arrive as workers persist them.
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "RUNNING" || status === "PENDING" ? 4_000 : false;
    },
  });
}

export function useAssessmentSteps(runId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ["assessment-steps", runId],
    queryFn: () => endpoints.assessmentSteps(runId as string),
    enabled: runId !== null && enabled,
  });
}

export function useEvalRuns() {
  return useQuery({ queryKey: ["eval-runs"], queryFn: endpoints.evalRuns, staleTime: CORPUS_STALE });
}

export function useSearch() {
  return useMutation({
    mutationFn: ({ body, signal }: { body: SearchRequest; signal?: AbortSignal }) =>
      endpoints.search(body, signal),
  });
}

export function useStartAssessment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: endpoints.startAssessment,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["assessments"] });
    },
  });
}

/**
 * Record an analyst decision. Pessimistic on purpose: the UI shows the new
 * decision only once the server has stored it, so a failed request can never
 * look like a saved one.
 */
export function useSetDecision(runId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ findingId, decision }: { findingId: number; decision: AnalystDecision }) =>
      endpoints.setDecision(findingId, decision),
    onSuccess: (saved: Finding) => {
      client.setQueryData<AssessmentDetail>(["assessment", runId], (current) =>
        current
          ? { ...current, findings: current.findings.map((f) => (f.id === saved.id ? saved : f)) }
          : current,
      );
      void client.invalidateQueries({ queryKey: ["assessment", runId] });
      void client.invalidateQueries({ queryKey: ["assessments"] });
    },
  });
}
