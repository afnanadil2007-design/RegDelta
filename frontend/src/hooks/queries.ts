import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { endpoints } from "@/api/endpoints";
import type { SearchRequest } from "@/types/api";

// Corpus data changes only on re-ingest, so it can be cached generously.
const CORPUS_STALE = 5 * 60_000;
// Assessment data changes while a run is in flight.
const RUN_STALE = 5_000;

export function useCirculars(department?: string | null) {
  return useQuery({
    queryKey: ["circulars", department ?? null],
    queryFn: () => endpoints.circulars({ limit: 200, department }),
    staleTime: CORPUS_STALE,
  });
}

export function useDepartments() {
  return useQuery({
    queryKey: ["departments"],
    queryFn: endpoints.departments,
    staleTime: CORPUS_STALE,
  });
}

export function useCircular(id: number | null) {
  return useQuery({
    queryKey: ["circular", id],
    queryFn: () => endpoints.circular(id as number),
    enabled: id !== null,
    staleTime: CORPUS_STALE,
  });
}

export function usePolicyPacks() {
  return useQuery({
    queryKey: ["policy-packs"],
    queryFn: endpoints.policyPacks,
    staleTime: CORPUS_STALE,
  });
}

export function usePolicyClauses(packId: number | null) {
  return useQuery({
    queryKey: ["policy-clauses", packId],
    queryFn: () => endpoints.policyClauses(packId as number),
    enabled: packId !== null,
    staleTime: CORPUS_STALE,
  });
}

export function useAssessments() {
  return useQuery({
    queryKey: ["assessments"],
    queryFn: endpoints.assessments,
    staleTime: RUN_STALE,
  });
}

export function useAssessment(runId: string | null, poll = false) {
  return useQuery({
    queryKey: ["assessment", runId],
    queryFn: () => endpoints.assessment(runId as string),
    enabled: runId !== null,
    staleTime: RUN_STALE,
    refetchInterval: poll ? 2000 : false,
  });
}

export function useEvalRuns() {
  return useQuery({
    queryKey: ["eval-runs"],
    queryFn: endpoints.evalRuns,
    staleTime: CORPUS_STALE,
  });
}

export function useSearch() {
  return useMutation({
    mutationFn: (body: SearchRequest) => endpoints.search(body),
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

export function useSetDecision(runId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ findingId, decision }: { findingId: number; decision: string }) =>
      endpoints.setDecision(findingId, decision),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["assessment", runId] });
    },
  });
}
