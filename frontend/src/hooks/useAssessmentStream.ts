import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useReducer } from "react";

import { streamUrl } from "@/api/endpoints";
import { initialTrace, traceReducer, type TraceState } from "@/hooks/traceReducer";

const EVENTS = ["snapshot", "step", "done", "timeout", "error"] as const;

/**
 * Subscribe to a run's live trace while it is in progress.
 *
 * EventSource reconnects on its own after a dropped connection; the server
 * answers every connection with a full snapshot, so nothing is lost or
 * doubled. When the run ends, the assessment queries are refreshed so the
 * findings, memo, and usage come from the stored record. Bumping
 * ``generation`` opens a fresh connection after the server ended the stream.
 */
export function useAssessmentStream(runId: string | null, enabled: boolean, generation = 0): TraceState {
  const [state, dispatch] = useReducer(traceReducer, initialTrace);
  const client = useQueryClient();

  useEffect(() => {
    if (!runId || !enabled) return;
    const source = new EventSource(streamUrl(runId));
    let finished = false;
    dispatch({ type: "reset" });

    source.onopen = () => dispatch({ type: "open" });
    source.onerror = () => {
      if (!finished) dispatch({ type: "connection-lost" });
    };
    for (const name of EVENTS) {
      source.addEventListener(name, (event) => {
        const data = (event as MessageEvent<string>).data;
        // The browser fires a data-less "error" event on connection loss; only
        // server-sent errors carry data.
        if (name === "error" && typeof data !== "string") return;
        dispatch({ type: "message", event: name, data });
        if (name === "done" || name === "timeout" || name === "error") {
          finished = true;
          source.close();
          void client.invalidateQueries({ queryKey: ["assessment", runId] });
          void client.invalidateQueries({ queryKey: ["assessment-steps", runId] });
          void client.invalidateQueries({ queryKey: ["assessments"] });
        }
      });
    }
    return () => {
      finished = true;
      source.close();
    };
  }, [runId, enabled, client, generation]);

  return state;
}
