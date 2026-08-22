import type { ReactNode } from "react";
import { useState } from "react";

import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { Mono } from "@/components/ui";
import { cn } from "@/lib/utils";
import type { Finding, ImpactType } from "@/types/api";

const IMPACT_STYLE: Record<ImpactType, { label: string; className: string }> = {
  CONFLICT: { label: "Conflict", className: "bg-impact-conflict/10 text-impact-conflict" },
  MODIFIED: { label: "Modified", className: "bg-impact-modified/10 text-impact-modified" },
  NEW_REQUIREMENT: { label: "New", className: "bg-impact-new/10 text-impact-new" },
  ALREADY_COVERED: { label: "Covered", className: "bg-impact-covered/10 text-impact-covered" },
  NO_MATCH: { label: "No match", className: "bg-impact-none/10 text-impact-none" },
};

// Most actionable first when sorting by impact.
const IMPACT_ORDER: ImpactType[] = [
  "CONFLICT",
  "MODIFIED",
  "NEW_REQUIREMENT",
  "ALREADY_COVERED",
  "NO_MATCH",
];

export function ImpactBadge({ impact }: { impact: ImpactType }) {
  const style = IMPACT_STYLE[impact];
  return (
    <span
      className={cn(
        "inline-block whitespace-nowrap rounded px-2 py-0.5 text-[11px] font-medium",
        style.className,
      )}
    >
      {style.label}
    </span>
  );
}

type SortKey = "impact" | "confidence";

export function FindingsTable({
  findings,
  selectedId,
  onSelect,
}: {
  findings: Finding[];
  selectedId?: number | null;
  onSelect?: (finding: Finding) => void;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("impact");

  const sorted = [...findings].sort((a, b) => {
    if (sortKey === "confidence") return b.confidence - a.confidence;
    const delta =
      IMPACT_ORDER.indexOf(a.impact_type) - IMPACT_ORDER.indexOf(b.impact_type);
    return delta !== 0 ? delta : b.confidence - a.confidence;
  });

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-muted-foreground">
            <SortableTh onClick={() => setSortKey("impact")} active={sortKey === "impact"}>
              Impact
            </SortableTh>
            <th className="px-3 py-2 font-medium">Clause</th>
            <th className="px-3 py-2 font-medium">Obligation</th>
            <SortableTh
              onClick={() => setSortKey("confidence")}
              active={sortKey === "confidence"}
            >
              Confidence
            </SortableTh>
            <th className="px-3 py-2 font-medium">Decision</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((finding) => (
            <tr
              key={finding.id}
              onClick={() => onSelect?.(finding)}
              className={cn(
                "cursor-pointer border-b border-border/60 align-top transition-colors",
                selectedId === finding.id ? "bg-accent/50" : "hover:bg-muted/40",
              )}
            >
              <td className="px-3 py-2">
                <ImpactBadge impact={finding.impact_type} />
              </td>
              <td className="px-3 py-2">
                <Mono>{finding.clause_number ?? "—"}</Mono>
              </td>
              <td className="max-w-md px-3 py-2">
                <span className="line-clamp-2 text-[13px]">
                  {finding.obligation_text ?? "—"}
                </span>
              </td>
              <td className="px-3 py-2">
                <ConfidenceBadge value={finding.confidence} />
              </td>
              <td className="px-3 py-2">
                <DecisionPill decision={finding.analyst_decision} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SortableTh({
  children,
  onClick,
  active,
}: {
  children: ReactNode;
  onClick: () => void;
  active: boolean;
}) {
  return (
    <th className="px-3 py-2 font-medium">
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "inline-flex items-center gap-1 hover:text-foreground",
          active && "text-foreground",
        )}
      >
        {children}
        {active && <span aria-hidden>↓</span>}
      </button>
    </th>
  );
}

function DecisionPill({ decision }: { decision: Finding["analyst_decision"] }) {
  const tone =
    decision === "ACCEPTED"
      ? "bg-impact-covered/10 text-impact-covered"
      : decision === "REJECTED"
        ? "bg-impact-conflict/10 text-impact-conflict"
        : "bg-muted text-muted-foreground";
  return (
    <span className={cn("rounded px-2 py-0.5 text-[11px]", tone)}>
      {decision.toLowerCase()}
    </span>
  );
}
