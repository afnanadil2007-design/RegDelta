import { Link } from "react-router-dom";

import { Ident, ImpactTag } from "@/components/lexicon";
import { Table, Td, Th } from "@/components/ui/table";
import { formatDateTime } from "@/lib/format";
import { IMPACT_ORDER, providerLabel, RUN_STATUS } from "@/lib/labels";
import { cn } from "@/lib/utils";
import type { AssessmentSummary } from "@/types/api";

function ImpactCounts({ run }: { run: AssessmentSummary }) {
  const present = IMPACT_ORDER.filter((impact) => (run.counts.by_impact[impact] ?? 0) > 0);
  if (present.length === 0) return <span className="text-ink-soft">None yet</span>;
  return (
    <span className="flex flex-wrap gap-1.5">
      {present.map((impact) => (
        <span key={impact} className="inline-flex items-center gap-1">
          <ImpactTag impact={impact} />
          <span className="font-semibold">{run.counts.by_impact[impact]}</span>
        </span>
      ))}
    </span>
  );
}

function StatusText({ run }: { run: AssessmentSummary }) {
  const tone =
    run.status === "FAILED" ? "text-error" : run.status === "CAPPED" ? "text-impact-modified" : "text-ink";
  return (
    <span className={cn("font-semibold", tone)}>
      {RUN_STATUS[run.status].label}
      {run.failed_tasks > 0 ? (
        <span className="block text-xs font-normal text-ink-soft">{run.failed_tasks} not assessed</span>
      ) : null}
    </span>
  );
}

function decided(run: AssessmentSummary): string {
  return `${run.counts.decision_accepted + run.counts.decision_rejected} of ${run.counts.total}`;
}

/** Assessment runs: a table from 768px, a ruled list below it. */
export function AssessmentList({ runs, label }: { runs: AssessmentSummary[]; label: string }) {
  return (
    <>
      <Table label={label} className="hidden md:block">
        <thead>
          <tr>
            <Th>Circular</Th>
            <Th>Status</Th>
            <Th>Findings</Th>
            <Th align="right">Quotes located</Th>
            <Th align="right">Decided</Th>
            <Th>Started</Th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.run_id}>
              <Td className="max-w-[28rem]">
                <Link to={`/assessments/${run.run_id}`} className="font-semibold text-ink break-words">
                  {run.circular_title ?? "Untitled circular"}
                </Link>
                <span className="block text-sm text-ink-soft break-words">
                  <Ident value={run.circular_number} /> · {run.policy_pack_name ?? "Unknown manual"} ·{" "}
                  {providerLabel(run.provider)}
                </span>
              </Td>
              <Td>
                <StatusText run={run} />
              </Td>
              <Td>
                <ImpactCounts run={run} />
              </Td>
              <Td align="right">
                {run.counts.quote_verified} of {run.counts.total}
              </Td>
              <Td align="right">{decided(run)}</Td>
              <Td className="whitespace-nowrap text-sm text-ink-soft">{formatDateTime(run.created_at)}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
      <ul aria-label={label} className="flex flex-col md:hidden">
        {runs.map((run) => (
          <li key={run.run_id} className="flex flex-col gap-1.5 border-b border-rule py-3 first:pt-0">
            <Link to={`/assessments/${run.run_id}`} className="font-semibold text-ink break-words">
              {run.circular_title ?? "Untitled circular"}
            </Link>
            <span className="text-sm text-ink-soft break-words">
              <Ident value={run.circular_number} />
            </span>
            <ImpactCounts run={run} />
            <span className="flex flex-wrap gap-x-4 text-sm">
              <StatusText run={run} />
              <span>Decided {decided(run)}</span>
              <span className="text-ink-soft">{formatDateTime(run.created_at)}</span>
            </span>
          </li>
        ))}
      </ul>
    </>
  );
}
