import { Check, Undo2, X } from "lucide-react";
import { useState } from "react";

import { errorMessage } from "@/api/client";
import { DecisionMark } from "@/components/lexicon";
import { Button } from "@/components/ui/controls";
import { Notice } from "@/components/ui/feedback";
import { useSetDecision } from "@/hooks/queries";
import { DECISION } from "@/lib/labels";
import type { AnalystDecision, Finding } from "@/types/api";

/**
 * Accept or reject one finding. The saved decision is shown only after the
 * server confirms it; a failure says so and keeps the previous decision.
 * Render it with ``key={finding.id}`` so each finding starts clean.
 */
export function DecisionBar({ finding, runId }: { finding: Finding; runId: string }) {
  const mutation = useSetDecision(runId);
  const [announcement, setAnnouncement] = useState("");
  const pending = mutation.isPending ? mutation.variables?.decision : undefined;

  const decide = (decision: AnalystDecision) => {
    mutation.mutate(
      { findingId: finding.id, decision },
      {
        onSuccess: (saved) =>
          setAnnouncement(
            saved.analyst_decision === "PENDING"
              ? "Decision cleared."
              : `${DECISION[saved.analyst_decision]}. Saved.`,
          ),
      },
    );
  };

  const current = finding.analyst_decision;
  return (
    <div className="flex flex-col gap-3 border-t-[1.5px] border-ink pt-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-ink">Your decision</p>
          <DecisionMark decision={current} decidedAt={finding.decided_at} />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant={current === "ACCEPTED" ? "primary" : "secondary"}
            aria-pressed={current === "ACCEPTED"}
            busy={pending === "ACCEPTED"}
            disabled={mutation.isPending}
            icon={<Check aria-hidden className="size-4" />}
            onClick={() => decide("ACCEPTED")}
          >
            Accept
          </Button>
          <Button
            variant={current === "REJECTED" ? "primary" : "secondary"}
            aria-pressed={current === "REJECTED"}
            busy={pending === "REJECTED"}
            disabled={mutation.isPending}
            icon={<X aria-hidden className="size-4" />}
            onClick={() => decide("REJECTED")}
          >
            Reject
          </Button>
          {current !== "PENDING" ? (
            <Button
              variant="quiet"
              busy={pending === "PENDING"}
              disabled={mutation.isPending}
              icon={<Undo2 aria-hidden className="size-4" />}
              onClick={() => decide("PENDING")}
            >
              Clear
            </Button>
          ) : null}
        </div>
      </div>
      {mutation.isError ? (
        <Notice
          tone="error"
          title="The decision was not saved"
          action={
            <Button onClick={() => mutation.variables && decide(mutation.variables.decision)}>
              Try again
            </Button>
          }
        >
          {errorMessage(mutation.error)} The finding still shows its last saved decision.
        </Notice>
      ) : null}
      <p role="status" aria-live="polite" className="sr-only">
        {announcement}
      </p>
    </div>
  );
}
