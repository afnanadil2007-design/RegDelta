import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import Search from "@/pages/Search";

const answer = {
  mode: "hybrid",
  hits: [
    {
      chunk_id: 1,
      circular_id: 7,
      circular_number: "SEBI/HO/MIRSD/CIR/P/2024/1",
      circular_title: "Client onboarding",
      issue_date: "2024-01-02",
      text: "Intermediaries shall complete client due diligence before activating a trading account.",
      char_start: 0,
      char_end: 86,
      heading_path: null,
      score: 0.03,
      dense_rank: 1,
      lexical_rank: 1,
      rrf_score: 0.03,
      rerank_score: null,
    },
  ],
  refused: false,
  top_score: 0.03,
  threshold: null,
  score_kind: "rrf",
  excluded_by_temporal_filter: [],
  elapsed_ms: 12,
};

function respond(url: string) {
  const body = url.endsWith("/search") ? answer : url.endsWith("/departments") ? ["MIRSD"] : {};
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

afterEach(() => vi.unstubAllGlobals());

describe("Search", () => {
  it("runs a shared link's search once, even when React remounts the page", async () => {
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async (input) => respond(String(input)),
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <StrictMode>
        <QueryClientProvider client={client}>
          <MemoryRouter
            initialEntries={["/search?q=client+due+diligence&mode=hybrid"]}
            future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
          >
            <Search />
          </MemoryRouter>
        </QueryClientProvider>
      </StrictMode>,
    );
    expect(await screen.findByText(/1 passage/)).toBeInTheDocument();
    const searches = fetchMock.mock.calls.filter(([input, init]) => {
      return String(input).endsWith("/search") && !init?.signal?.aborted;
    });
    expect(searches).toHaveLength(1);
    expect(JSON.parse(String(searches[0][1]?.body))).toEqual({
      query: "client due diligence",
      mode: "hybrid",
      department: null,
    });
  });
});
