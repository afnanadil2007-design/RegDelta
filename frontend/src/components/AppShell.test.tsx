import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AppShell } from "@/components/AppShell";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { ImpactBadge } from "@/components/FindingsTable";
import { SpanHighlight } from "@/components/SpanHighlight";

function withProviders(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AppShell", () => {
  it("renders all six navigation entries", () => {
    render(withProviders(<AppShell />));
    for (const label of [
      "Dashboard",
      "Circulars",
      "Impact Assessment",
      "Point-in-Time",
      "Evaluation",
      "Search",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });
});

describe("ConfidenceBadge", () => {
  it("never shows a bare float", () => {
    render(<ConfidenceBadge value={0.87} />);
    expect(screen.getByText("High")).toBeInTheDocument();
    expect(screen.getByText("87")).toBeInTheDocument();
    expect(screen.queryByText("0.87")).not.toBeInTheDocument();
  });

  it("bands low confidence separately", () => {
    render(<ConfidenceBadge value={0.2} />);
    expect(screen.getByText("Low")).toBeInTheDocument();
  });
});

describe("ImpactBadge", () => {
  it("labels every impact type", () => {
    const { rerender } = render(<ImpactBadge impact="CONFLICT" />);
    expect(screen.getByText("Conflict")).toBeInTheDocument();
    rerender(<ImpactBadge impact="ALREADY_COVERED" />);
    expect(screen.getByText("Covered")).toBeInTheDocument();
  });
});

describe("SpanHighlight", () => {
  const text = "Brokers shall collect upfront margin from clients.";

  it("marks the span relative to the base offset", () => {
    // "shall collect" begins at index 8 of `text`; base 1000 shifts the offsets.
    render(<SpanHighlight text={text} start={1008} end={1021} baseOffset={1000} />);
    expect(screen.getByText("shall collect")).toBeInTheDocument();
  });

  it("renders plain text when offsets are out of range", () => {
    // A bad span must not break the page.
    const { container } = render(
      <SpanHighlight text={text} start={9000} end={9100} baseOffset={0} />,
    );
    expect(container.querySelector("mark")).toBeNull();
    expect(container.textContent).toBe(text);
  });

  it("renders plain text when there is no span", () => {
    const { container } = render(<SpanHighlight text={text} start={null} end={null} />);
    expect(container.querySelector("mark")).toBeNull();
  });
});
