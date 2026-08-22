import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/api/client";
import type { HealthResponse } from "@/types/api";

/** Polls the API health endpoint; drives the connection indicator in the shell. */
export function useHealth() {
  return useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: () => apiFetch<HealthResponse>("/health"),
    staleTime: 10_000,
    refetchInterval: 30_000,
  });
}
