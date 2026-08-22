import { useEffect, useRef, useState } from "react";

import type { AgentStep, AssessmentStatus } from "@/types/api";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

interface StreamState {
  steps: AgentStep[];
  status: AssessmentStatus | null;
  connected: boolean;
  error: string | null;
}

/**
 * Subscribe to an assessment's SSE trace.
 *
 * Steps are appended as each graph node completes, so the timeline renders
 * progressively. Duplicate sequence numbers are ignored, which makes a
 * reconnect safe.
 */
export function useAssessmentStream(runId: string | null): StreamState {
  const [state, setState] = useState<StreamState>({
    steps: [],
    status: null,
    connected: false,
    error: null,
  });
  const seen = useRef<Set<number>>(new Set());

  useEffect(() => {
    if (!runId) return;

    seen.current = new Set();
    setState({ steps: [], status: null, connected: true, error: null });

    const source = new EventSource(`${API_BASE}/assessments/${runId}/stream`);

    source.addEventListener("step", (event) => {
      const step = JSON.parse((event as MessageEvent<string>).data) as AgentStep;
      if (seen.current.has(step.seq)) return;
      seen.current.add(step.seq);
      setState((prev) => ({ ...prev, steps: [...prev.steps, step] }));
    });

    source.addEventListener("done", (event) => {
      const payload = JSON.parse((event as MessageEvent<string>).data) as {
        status: AssessmentStatus;
        error_reason: string | null;
      };
      setState((prev) => ({
        ...prev,
        status: payload.status,
        connected: false,
        error: payload.error_reason,
      }));
      source.close();
    });

    source.addEventListener("error", () => {
      // EventSource retries on its own; surface the state without tearing down
      // the accumulated steps.
      setState((prev) => ({ ...prev, connected: false }));
    });

    return () => source.close();
  }, [runId]);

  return state;
}
