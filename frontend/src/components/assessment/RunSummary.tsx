import { ApiRequestError } from "@/api/client";
import { Button } from "@/components/ui/controls";
import { Notice } from "@/components/ui/feedback";
import type { TraceState } from "@/hooks/traceReducer";
import { formatDateTime, formatDuration, plural } from "@/lib/format";
import { providerLabel, RUN_STATUS } from "@/lib/labels";
import type { AssessmentSummary } from "@/types/api";

function costPhrase(run: AssessmentSummary): string {
  const usage = run.usage;
  if (run.provider?.deterministic) return "$0.00, run locally";
  if (usage.estimated_cost_usd === null) return "cost unknown: the model has no list price";
  const value = `$${usage.estimated_cost_usd.toFixed(4)}`;
  return usage.cost_complete
    ? `${value} estimated at list price`
    : `at least ${value} (${plural(usage.unpriced_calls, "unpriced call")})`;
}

/** The run's facts as one line under the title, so the evidence keeps the fold. */
export function RunFacts({ run }: { run: AssessmentSummary }) {
  const counts = run.counts;
  const finished = run.completed_at
    ? new Date(run.completed_at).getTime() - new Date(run.created_at).getTime()
    : null;
  const findings =
    counts.assessed_obligations < run.obligation_count
      ? `${plural(counts.total, "finding")} so far (${counts.assessed_obligations} of ${plural(run.obligation_count, "obligation")})`
      : `${plural(counts.total, "finding")} for ${plural(run.obligation_count, "obligation")}`;
  const parts = [
    providerLabel(run.provider),
    findings,
    `quotes located ${counts.quote_verified} of ${counts.total}`,
    `decided ${counts.decision_accepted + counts.decision_rejected} of ${counts.total}`,
    costPhrase(run),
    finished === null
      ? `started ${formatDateTime(run.created_at)}`
      : `${formatDuration(finished)}, finished ${formatDateTime(run.completed_at)}`,
  ];
  return (
    <p className="text-sm text-ink-soft">
      <span className="font-semibold text-ink">{RUN_STATUS[run.status].label}</span>
      {parts.map((part) => (
        <span key={part}> · {part}</span>
      ))}
    </p>
  );
}

/** What is unusual about this run, each with its cause and way forward. */
export function RunNotices({
  run,
  trace,
  inProgress,
  onReconnect,
}: {
  run: AssessmentSummary;
  trace: TraceState;
  inProgress: boolean;
  onReconnect: () => void;
}) {
  const notices: React.ReactNode[] = [];
  const counts = run.counts;

  if (inProgress) {
    notices.push(
      <Notice key="running" tone="info" title="Assessment in progress">
        {counts.assessed_obligations} of {plural(run.obligation_count, "obligation")} assessed. Findings
        appear here as each obligation is finished; you can review them while the rest run.
      </Notice>,
    );
    if (trace.connection === "reconnecting") {
      notices.push(
        <Notice key="reconnecting" tone="warning" title="Live trace disconnected, reconnecting">
          The browser is retrying on its own. When it reconnects the server resends every step, so nothing is
          lost or counted twice.
        </Notice>,
      );
    }
  }
  if (trace.ended) {
    notices.push(
      <Notice
        key="ended"
        tone="warning"
        title={trace.ended === "timeout" ? "The live trace timed out" : "The live trace stopped"}
        action={<Button onClick={onReconnect}>Reconnect</Button>}
      >
        {trace.endMessage ?? "The server closed the stream before the run finished."} The stored run is shown
        below.
      </Notice>,
    );
  }
  if (trace.malformed > 0) {
    notices.push(
      <Notice
        key="malformed"
        tone="warning"
        title={`${plural(trace.malformed, "trace event")} could not be read`}
      >
        They were skipped. The stored trace, loaded when the run finishes, is complete.
      </Notice>,
    );
  }
  if (run.status === "CAPPED") {
    notices.push(
      <Notice key="capped" tone="warning" title="Stopped at a limit">
        {run.status_detail ?? RUN_STATUS.CAPPED.meaning} {counts.assessed_obligations} of{" "}
        {plural(run.obligation_count, "obligation")} were assessed; their findings are kept.
      </Notice>,
    );
  }
  if (run.status === "FAILED") {
    notices.push(
      <Notice key="failed" tone="error" title="The run failed">
        {run.status_detail ?? "The run stopped on an error."} Findings stored before the failure are shown.
      </Notice>,
    );
  }
  if (run.failed_tasks > 0) {
    notices.push(
      <Notice
        key="tasks"
        tone="warning"
        title={`${plural(run.failed_tasks, "obligation")} could not be assessed`}
      >
        The judge failed on these after its retries, so they have no finding. Start a new assessment from the
        circular to try them again.
      </Notice>,
    );
  }
  if (counts.quote_failed > 0) {
    notices.push(
      <Notice
        key="quotes"
        tone="warning"
        title={`${plural(counts.quote_failed, "finding")} rest${counts.quote_failed === 1 ? "s" : ""} on a quote that was not located`}
      >
        The evidence they cite was not found in its source. Each one shows the quote that could not be found.
      </Notice>,
    );
  }
  return notices.length ? <div className="flex flex-col gap-2">{notices}</div> : null;
}

export function isNotFound(error: unknown): boolean {
  return error instanceof ApiRequestError && error.status === 404;
}
