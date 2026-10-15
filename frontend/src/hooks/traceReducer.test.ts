import { describe, expect, it } from "vitest";

import { initialTrace, traceReducer, type TraceState } from "@/hooks/traceReducer";
import type { AgentStep } from "@/types/api";

function step(seq: number, status: AgentStep["status"] = "OK"): AgentStep {
  return {
    seq,
    node: "judge_impact",
    status,
    summary: null,
    tokens: 0,
    cost_usd: null,
    latency_ms: status === "RUNNING" ? null : 10,
    error: null,
    obligation_id: 1,
    clause_number: "A.1",
    attempt: 1,
    started_at: "2026-10-15T00:00:00Z",
    finished_at: status === "RUNNING" ? null : "2026-10-15T00:00:01Z",
  };
}

function message(state: TraceState, event: string, data: unknown): TraceState {
  return traceReducer(state, {
    type: "message",
    event,
    data: typeof data === "string" ? data : JSON.stringify(data),
  });
}

describe("traceReducer", () => {
  it("replaces everything with a snapshot, so a reconnect cannot double steps", () => {
    let state = message(initialTrace, "snapshot", {
      status: "RUNNING",
      steps: [step(1), step(2, "RUNNING")],
    });
    state = message(state, "step", step(3));
    // Reconnect: the server resends the full state.
    state = traceReducer(state, { type: "connection-lost" });
    expect(state.connection).toBe("reconnecting");
    state = message(state, "snapshot", { status: "RUNNING", steps: [step(1), step(2), step(3)] });
    expect(state.steps.map((s) => s.seq)).toEqual([1, 2, 3]);
    expect(state.connection).toBe("live");
  });

  it("updates a re-sent step in place instead of appending it", () => {
    let state = message(initialTrace, "snapshot", {
      status: "RUNNING",
      steps: [step(1), step(2, "RUNNING")],
    });
    state = message(state, "step", step(2, "OK"));
    state = message(state, "step", step(2, "OK")); // duplicate delivery
    expect(state.steps).toHaveLength(2);
    expect(state.steps[1].status).toBe("OK");
  });

  it("keeps steps ordered by sequence when they arrive out of order", () => {
    let state = message(initialTrace, "snapshot", { status: "RUNNING", steps: [] });
    state = message(state, "step", step(3));
    state = message(state, "step", step(1));
    expect(state.steps.map((s) => s.seq)).toEqual([1, 3]);
  });

  it("counts and ignores malformed events without losing state", () => {
    let state = message(initialTrace, "snapshot", { status: "RUNNING", steps: [step(1)] });
    state = message(state, "step", "{not json");
    state = message(state, "step", { seq: "x", node: 1 });
    state = message(state, "mystery", {});
    state = message(state, "snapshot", { status: "NOT_A_STATUS", steps: [] });
    expect(state.malformed).toBe(4);
    expect(state.steps.map((s) => s.seq)).toEqual([1]);
  });

  it("drops malformed steps inside a snapshot and counts them", () => {
    const state = message(initialTrace, "snapshot", { status: "RUNNING", steps: [step(1), { seq: 2 }] });
    expect(state.steps).toHaveLength(1);
    expect(state.malformed).toBe(1);
  });

  it("ends on done with the terminal status and detail", () => {
    let state = message(initialTrace, "snapshot", { status: "RUNNING", steps: [] });
    state = message(state, "done", { status: "CAPPED", status_detail: "Call budget reached." });
    expect(state).toMatchObject({
      status: "CAPPED",
      statusDetail: "Call budget reached.",
      connection: "closed",
    });
    // A late transport error after the server closed the stream changes nothing.
    expect(traceReducer(state, { type: "connection-lost" }).connection).toBe("closed");
  });

  it("records why a stream ended early", () => {
    const state = message(initialTrace, "timeout", { message: "Stream limit reached." });
    expect(state).toMatchObject({
      ended: "timeout",
      endMessage: "Stream limit reached.",
      connection: "closed",
    });
  });

  it("reset keeps the steps already shown but clears the ending", () => {
    let state = message(initialTrace, "snapshot", { status: "RUNNING", steps: [step(1)] });
    state = message(state, "error", { message: "boom" });
    state = traceReducer(state, { type: "reset" });
    expect(state.ended).toBeNull();
    expect(state.connection).toBe("connecting");
    expect(state.steps).toHaveLength(1);
  });
});
