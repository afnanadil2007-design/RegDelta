import { Mono } from "@/components/ui";
import { cn } from "@/lib/utils";
import type { AgentStep, AssessmentStatus } from "@/types/api";

const NODE_LABEL: Record<string, string> = {
  plan_assessment: "Plan assessment",
  retrieve_clauses: "Retrieve policy clauses",
  judge_impact: "Judge impact",
  verify_grounding: "Verify grounding",
  check_token_cap: "Check token budget",
  synthesize_memo: "Write memo",
};

/**
 * The live agent timeline, driven by the SSE stream. Steps append as each
 * graph node completes, so the screen fills progressively rather than
 * blocking on the whole assessment.
 */
export function AgentTrace({
  steps,
  status,
  connected,
}: {
  steps: AgentStep[];
  status: AssessmentStatus | null;
  connected: boolean;
}) {
  const totalTokens = steps.reduce((sum, s) => sum + s.tokens, 0);
  const totalMs = steps.reduce((sum, s) => sum + (s.latency_ms ?? 0), 0);

  return (
    <div>
      <div className="mb-3 flex items-center justify-between text-xs text-muted-foreground">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "inline-block h-1.5 w-1.5 rounded-full",
              connected ? "animate-pulse bg-impact-covered" : "bg-muted-foreground/40",
            )}
          />
          {connected ? "streaming" : status ? `stream closed · ${status.toLowerCase()}` : "idle"}
        </div>
        <div className="flex gap-3 font-mono">
          <span>{steps.length} steps</span>
          <span>{totalTokens.toLocaleString()} tok</span>
          <span>{(totalMs / 1000).toFixed(1)}s</span>
        </div>
      </div>

      {steps.length === 0 ? (
        <p className="rounded-md border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
          Waiting for the first graph node to complete…
        </p>
      ) : (
        <ol className="space-y-1.5">
          {steps.map((step) => (
            <li
              key={step.seq}
              className={cn(
                "flex items-start gap-3 rounded-md border px-3 py-2",
                step.status === "ERROR"
                  ? "border-impact-conflict/40 bg-impact-conflict/5"
                  : "border-border bg-card",
              )}
            >
              <Mono className="mt-0.5 w-6 shrink-0 text-right text-muted-foreground">
                {step.seq}
              </Mono>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-[13px] font-medium">
                    {NODE_LABEL[step.node] ?? step.node}
                  </span>
                  <Mono className="shrink-0 text-muted-foreground">
                    {step.latency_ms !== null ? `${step.latency_ms}ms` : ""}
                    {step.tokens > 0 ? ` · ${step.tokens} tok` : ""}
                  </Mono>
                </div>
                {step.summary && (
                  <p className="mt-0.5 text-xs text-muted-foreground">{step.summary}</p>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
