import type { ReactNode } from "react";

import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { ImpactBadge } from "@/components/FindingsTable";
import { SpanHighlight } from "@/components/SpanHighlight";
import { AiGenerated, Button, Card, Mono } from "@/components/ui";
import type { Finding } from "@/types/api";

/**
 * Side-by-side evidence for one finding, with both spans highlighted: the
 * obligation on the left, the policy clause on the right. This is where an
 * analyst decides whether to accept a finding, so the two texts must be
 * legible together and the machine-written rationale must be visibly
 * separated from the source text.
 */
export function EvidencePane({
  finding,
  onDecide,
  deciding,
}: {
  finding: Finding;
  onDecide?: (decision: "ACCEPTED" | "REJECTED") => void;
  deciding?: boolean;
}) {
  return (
    <Card className="p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <ImpactBadge impact={finding.impact_type} />
          <Mono className="text-muted-foreground">
            clause {finding.clause_number ?? "—"}
          </Mono>
        </div>
        <div className="flex items-center gap-2">
          <ConfidenceBadge value={finding.confidence} />
          {finding.verified && (
            <span
              className="rounded bg-impact-covered/10 px-2 py-0.5 text-[11px] text-impact-covered"
              title={`Each quoted span was re-resolved against the source text — verified after ${finding.verification_attempts} attempt(s)`}
            >
              grounded
            </span>
          )}
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <Panel title="Circular — obligation">
          {finding.obligation_text ? (
            <SpanHighlight
              text={finding.obligation_text}
              start={finding.circular_span_start}
              end={finding.circular_span_end}
              baseOffset={finding.circular_span_start ?? 0}
              tone="amber"
            />
          ) : (
            <Muted>Obligation text unavailable.</Muted>
          )}
        </Panel>

        <Panel title="Policy — clause">
          {finding.clause_text ? (
            <SpanHighlight
              text={finding.clause_text}
              start={finding.clause_span_start}
              end={finding.clause_span_end}
              baseOffset={finding.clause_span_start ?? 0}
              tone="blue"
            />
          ) : (
            <Muted>No clause matched this obligation.</Muted>
          )}
        </Panel>
      </div>

      <div className="mt-3">
        <AiGenerated label="AI-generated rationale">{finding.rationale}</AiGenerated>
      </div>

      {onDecide && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button
            variant="primary"
            disabled={deciding || finding.analyst_decision === "ACCEPTED"}
            onClick={() => onDecide("ACCEPTED")}
          >
            Accept
          </Button>
          <Button
            disabled={deciding || finding.analyst_decision === "REJECTED"}
            onClick={() => onDecide("REJECTED")}
          >
            Reject
          </Button>
          <span className="text-xs text-muted-foreground">
            The analyst decides; nothing is applied automatically.
          </span>
        </div>
      )}
    </Card>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-md border border-border bg-background p-3">
      <div className="mb-1.5 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        {title}
      </div>
      <p className="text-[13px] leading-relaxed">{children}</p>
    </div>
  );
}

function Muted({ children }: { children: ReactNode }) {
  return <span className="text-muted-foreground">{children}</span>;
}
