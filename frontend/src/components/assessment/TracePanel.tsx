import { CircleAlert, CircleCheck, Clock } from "lucide-react";
import { useEffect, useState } from "react";

import { formatDuration, formatInteger } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AgentStep, StepStatus } from "@/types/api";

const NODE: Record<string, string> = {
  plan_assessment: "Plan",
  retrieve_clauses: "Retrieve clauses",
  judge_impact: "Judge impact",
  verify_grounding: "Locate quotes",
  synthesize_memo: "Write memo",
  assess_obligation: "Assess obligation",
};

const STATUS: Record<StepStatus, { word: string; icon: React.ReactNode }> = {
  RUNNING: { word: "Running", icon: <Clock aria-hidden className="size-4 text-ink-soft" /> },
  OK: { word: "Done", icon: <CircleCheck aria-hidden className="size-4 text-impact-covered" /> },
  ERROR: { word: "Error", icon: <CircleAlert aria-hidden className="size-4 text-error" /> },
};

/** Re-renders once a second while something is running. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
  return now;
}

function subject(step: AgentStep): string {
  const parts = [];
  if (step.obligation_id !== null) parts.push(`Obligation ${step.obligation_id}`);
  if (step.clause_number) parts.push(`clause ${step.clause_number}`);
  return parts.join(", ") || "Whole run";
}

/**
 * The agent's steps as a fixed-column table. Rows are keyed by sequence, so
 * a step that changes (running → done) updates in place instead of moving.
 */
export function TracePanel({ steps, live }: { steps: AgentStep[]; live: boolean }) {
  const running = steps.some((s) => s.status === "RUNNING");
  const now = useNow(live && running);
  const done = steps.filter((s) => s.status !== "RUNNING").length;
  const errors = steps.filter((s) => s.status === "ERROR").length;

  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-ink-soft" aria-live={live ? "polite" : undefined}>
        {steps.length === 0
          ? "No steps recorded yet."
          : `${formatInteger(done)} of ${formatInteger(steps.length)} steps finished${
              errors ? `, ${formatInteger(errors)} with an error` : ""
            }.`}
      </p>
      {steps.length > 0 ? (
        <div role="region" aria-label="Agent trace" tabIndex={0} className="overflow-x-auto">
          <table className="w-full min-w-[720px] table-fixed border-collapse text-sm">
            <colgroup>
              <col className="w-12" />
              <col className="w-36" />
              <col className="w-44" />
              <col className="w-24" />
              <col className="w-24" />
              <col />
            </colgroup>
            <thead>
              <tr className="border-b-[1.5px] border-ink text-left">
                <th scope="col" className="py-1.5 pr-2 text-right font-semibold">
                  #
                </th>
                <th scope="col" className="px-2 py-1.5 font-semibold">
                  Step
                </th>
                <th scope="col" className="px-2 py-1.5 font-semibold">
                  Subject
                </th>
                <th scope="col" className="px-2 py-1.5 font-semibold">
                  Status
                </th>
                <th scope="col" className="px-2 py-1.5 text-right font-semibold">
                  Time
                </th>
                <th scope="col" className="px-2 py-1.5 font-semibold">
                  Outcome
                </th>
              </tr>
            </thead>
            <tbody>
              {steps.map((step) => {
                const status = STATUS[step.status];
                const elapsed =
                  step.status === "RUNNING" ? now - new Date(step.started_at).getTime() : step.latency_ms;
                return (
                  <tr key={step.seq} className="border-b border-rule align-top">
                    <td className="py-1.5 pr-2 text-right text-ink-soft">{step.seq}</td>
                    <td className="px-2 py-1.5 font-medium">
                      {NODE[step.node] ?? step.node}
                      {step.attempt && step.attempt > 1 ? (
                        <span className="block text-xs text-ink-soft">attempt {step.attempt}</span>
                      ) : null}
                    </td>
                    <td className="px-2 py-1.5 text-ink-soft">{subject(step)}</td>
                    <td className="px-2 py-1.5">
                      <span className="inline-flex items-center gap-1.5">
                        {status.icon}
                        {status.word}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-2 py-1.5 text-right">
                      {elapsed === null ? "—" : formatDuration(Math.max(0, elapsed))}
                    </td>
                    <td className={cn("px-2 py-1.5 break-words", step.error && "text-error")}>
                      {step.error ?? step.summary ?? ""}
                      {step.tokens > 0 ? (
                        <span className="block text-xs text-ink-soft">
                          {formatInteger(step.tokens)} tokens
                        </span>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
