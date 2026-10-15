import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/AppShell";

function renderShell(health: unknown, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify(health), { status, headers: { "Content-Type": "application/json" } }),
    ),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AppShell />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const ready = {
  status: "ok",
  env: "test",
  database: "up",
  schema_revision: "0004_evidence_provenance",
  provider: {
    name: "deterministic",
    model: "regdelta-rules-v1",
    deterministic: true,
    ready: true,
    reason: null,
  },
};

afterEach(() => vi.unstubAllGlobals());

describe("AppShell", () => {
  it("lists every route and a skip link", () => {
    renderShell(ready);
    const nav = screen.getAllByRole("navigation", { name: "Main" })[0];
    for (const label of ["Overview", "Circulars", "Search", "Assessments", "Point in time", "Evaluation"]) {
      expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main");
  });

  it("states the judge in words", async () => {
    renderShell(ready);
    expect((await screen.findAllByText(/rule-based judge \(demo\)/)).length).toBeGreaterThan(0);
  });

  it("says when assessments cannot run", async () => {
    renderShell({ ...ready, provider: { ...ready.provider, ready: false, reason: "Set GROQ_API_KEY." } });
    expect((await screen.findAllByText(/provider not configured/)).length).toBeGreaterThan(0);
  });

  it("opens and closes the phone menu with its button and Escape", () => {
    renderShell(ready);
    const button = screen.getByRole("button", { name: "Open menu" });
    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.getByRole("button", { name: "Open menu" })).toHaveAttribute("aria-expanded", "false");
  });
});
