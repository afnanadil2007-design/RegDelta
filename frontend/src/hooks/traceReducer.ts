import type { AgentStep, AssessmentStatus } from "@/types/api";

/**
 * State of the live trace for one run, driven by the SSE protocol in
 * backend/app/services/assessment_stream.py:
 *
 * - ``snapshot`` replaces everything (sent on every connect and reconnect),
 * - ``step`` upserts one step by ``seq`` (a step is re-sent when it changes),
 * - ``done`` / ``timeout`` / ``error`` end the stream.
 *
 * Duplicate or replayed events are harmless because steps are keyed by seq.
 * A payload that does not match the protocol is counted and ignored.
 */
export type Connection = "connecting" | "live" | "reconnecting" | "closed";

export interface TraceState {
  steps: AgentStep[];
  status: AssessmentStatus | null;
  statusDetail: string | null;
  connection: Connection;
  /** Why the stream ended without a terminal status, if it did. */
  ended: "timeout" | "error" | null;
  endMessage: string | null;
  malformed: number;
}

export type TraceEvent =
  | { type: "reset" }
  | { type: "open" }
  | { type: "connection-lost" }
  | { type: "message"; event: string; data: string };

export const initialTrace: TraceState = {
  steps: [],
  status: null,
  statusDetail: null,
  connection: "connecting",
  ended: null,
  endMessage: null,
  malformed: 0,
};

const STATUSES = new Set(["PENDING", "RUNNING", "COMPLETED", "FAILED", "CAPPED"]);
const STEP_STATUSES = new Set(["RUNNING", "OK", "ERROR"]);

function isStep(value: unknown): value is AgentStep {
  if (typeof value !== "object" || value === null) return false;
  const step = value as Record<string, unknown>;
  return (
    Number.isInteger(step.seq) &&
    typeof step.node === "string" &&
    typeof step.status === "string" &&
    STEP_STATUSES.has(step.status)
  );
}

function upsert(steps: AgentStep[], step: AgentStep): AgentStep[] {
  const index = steps.findIndex((existing) => existing.seq === step.seq);
  if (index === -1) return [...steps, step].sort((a, b) => a.seq - b.seq);
  const next = steps.slice();
  next[index] = step;
  return next;
}

function parse(data: string): unknown {
  try {
    return JSON.parse(data);
  } catch {
    return undefined;
  }
}

export function traceReducer(state: TraceState, action: TraceEvent): TraceState {
  if (action.type === "reset") return { ...initialTrace, steps: state.steps };
  if (action.type === "open") return { ...state, connection: "live" };
  if (action.type === "connection-lost") {
    return state.connection === "closed" ? state : { ...state, connection: "reconnecting" };
  }

  const payload = parse(action.data);
  const bad = { ...state, malformed: state.malformed + 1 };
  switch (action.event) {
    case "snapshot": {
      const snapshot = payload as { status?: unknown; steps?: unknown } | undefined;
      if (!snapshot || !Array.isArray(snapshot.steps) || !STATUSES.has(String(snapshot.status))) {
        return bad;
      }
      const steps = snapshot.steps.filter(isStep).sort((a, b) => a.seq - b.seq);
      return {
        ...state,
        steps,
        status: snapshot.status as AssessmentStatus,
        connection: "live",
        malformed: state.malformed + (snapshot.steps.length - steps.length),
      };
    }
    case "step":
      return isStep(payload) ? { ...state, steps: upsert(state.steps, payload) } : bad;
    case "done": {
      const done = payload as { status?: unknown; status_detail?: unknown } | undefined;
      if (!done || !STATUSES.has(String(done.status))) return bad;
      return {
        ...state,
        status: done.status as AssessmentStatus,
        statusDetail: typeof done.status_detail === "string" ? done.status_detail : null,
        connection: "closed",
      };
    }
    case "timeout":
    case "error": {
      const message = (payload as { message?: unknown } | undefined)?.message;
      return {
        ...state,
        connection: "closed",
        ended: action.event,
        endMessage: typeof message === "string" ? message : null,
      };
    }
    default:
      return bad;
  }
}
