import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DecisionBar } from "@/components/assessment/DecisionBar";
import { useAssessment } from "@/hooks/queries";
import type { AssessmentDetail, Finding } from "@/types/api";

const RUN = "00000000-0000-0000-0000-000000000001";

const finding: Finding = {
  id: 7,
  circular_id: 1,
  obligation_id: 3,
  obligation_text: "Brokers shall collect margin upfront.",
  obligation_char_start: 0,
  obligation_char_end: 37,
  policy_clause_id: 2,
  clause_number: "B.1",
  clause_heading: "Margin",
  clause_text: "Margin is collected upfront.",
  clause_char_start: 0,
  impact_type: "ALREADY_COVERED",
  rationale: "Same requirement.",
  model_confidence: 0.9,
  circular_span_start: 0,
  circular_span_end: 37,
  clause_span_start: 0,
  clause_span_end: 28,
  quote_status: "VERIFIED",
  verification_note: null,
  unlocated_quote: null,
  verification_attempts: 1,
  analyst_decision: "PENDING",
  decided_at: null,
};

function detail(f: Finding): AssessmentDetail {
  return { findings: [f], memo: null } as unknown as AssessmentDetail;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** Renders the bar from the query cache, as the workspace does. */
function Harness() {
  const query = useAssessment(RUN);
  const current = query.data?.findings[0];
  return current ? <DecisionBar finding={current} runId={RUN} /> : null;
}

function setup(responses: Array<() => Response>) {
  const calls: string[] = [];
  let saved = finding;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (init?.method === "POST") {
        const response = responses.shift()?.() ?? json({}, 500);
        if (response.ok) saved = (await response.clone().json()) as Finding;
        return response;
      }
      return json(detail(saved));
    }),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  client.setQueryData(["assessment", RUN], detail(finding));
  render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>,
  );
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe("DecisionBar", () => {
  it("never shows a decision the server did not store, and retries the same one", async () => {
    setup([
      () => json({ error: { code: "internal_error", message: "The database is unavailable." } }, 503),
      () => json({ ...finding, analyst_decision: "ACCEPTED", decided_at: "2026-10-15T08:00:00Z" }),
    ]);

    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(await screen.findByText("The decision was not saved")).toBeInTheDocument();
    expect(screen.getByText(/The database is unavailable/)).toBeInTheDocument();
    expect(screen.getByText("Not yet decided")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept" })).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Accept" })).toHaveAttribute("aria-pressed", "true"),
    );
    expect(screen.queryByText("The decision was not saved")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Accepted. Saved.");
  });

  it("explains an unreachable API", async () => {
    setup([
      () => {
        throw new TypeError("Failed to fetch");
      },
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(await screen.findByText(/could not be reached/)).toBeInTheDocument();
    expect(screen.getByText("Not yet decided")).toBeInTheDocument();
  });
});
