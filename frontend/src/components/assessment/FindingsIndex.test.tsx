import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FindingsIndex } from "@/components/assessment/FindingsIndex";
import { groupFindings } from "@/lib/evidence";
import type { Finding } from "@/types/api";

function finding(id: number, obligation: number, clause: string, impact: Finding["impact_type"]): Finding {
  return {
    id,
    circular_id: 1,
    obligation_id: obligation,
    obligation_text: `Obligation ${obligation}`,
    obligation_char_start: obligation * 100,
    obligation_char_end: obligation * 100 + 50,
    policy_clause_id: id,
    clause_number: clause,
    clause_heading: null,
    clause_text: "",
    clause_char_start: 0,
    impact_type: impact,
    rationale: "",
    model_confidence: null,
    circular_span_start: null,
    circular_span_end: null,
    clause_span_start: null,
    clause_span_end: null,
    quote_status: "VERIFIED",
    verification_note: null,
    unlocated_quote: null,
    verification_attempts: 1,
    analyst_decision: id === 3 ? "ACCEPTED" : "PENDING",
    decided_at: null,
  };
}

const findings = [
  finding(1, 2, "A.2", "ALREADY_COVERED"),
  finding(2, 1, "A.1", "ALREADY_COVERED"),
  finding(3, 2, "A.4", "CONFLICT"),
];

describe("FindingsIndex", () => {
  it("groups by obligation in document order, most consequential verdict first", () => {
    const groups = groupFindings(findings, undefined);
    expect(groups.map((g) => g.obligationId)).toEqual([1, 2]);
    expect(groups[1].findings.map((f) => f.clause_number)).toEqual(["A.4", "A.2"]);
  });

  it("chains repeated arrow keys even before the selection re-renders", () => {
    const groups = groupFindings(findings, undefined);
    const order = groups.flatMap((g) => g.findings);
    const onSelect = vi.fn();
    render(<FindingsIndex groups={groups} order={order} selectedId={order[0].id} onSelect={onSelect} />);
    const list = screen.getByRole("listbox");
    fireEvent.keyDown(list, { key: "ArrowDown" });
    fireEvent.keyDown(list, { key: "ArrowDown" });
    fireEvent.keyDown(list, { key: "ArrowDown" }); // already at the end
    expect(onSelect.mock.calls.map(([id]) => id)).toEqual([order[1].id, order[2].id, order[2].id]);
    fireEvent.keyDown(list, { key: "Home" });
    expect(onSelect).toHaveBeenLastCalledWith(order[0].id);
  });

  it("marks the selected option and shows decisions in words", () => {
    const groups = groupFindings(findings, undefined);
    const order = groups.flatMap((g) => g.findings);
    render(<FindingsIndex groups={groups} order={order} selectedId={3} onSelect={() => {}} />);
    const selected = screen.getByRole("option", { selected: true });
    expect(selected).toHaveTextContent("A.4");
    expect(selected).toHaveTextContent("Accepted");
    expect(screen.getByRole("listbox")).toHaveAttribute("aria-activedescendant", selected.id);
  });
});
