import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ErrorBar, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { GuideHead, PageHeader, Plate, SyntheticTag } from "@/components/lexicon";
import { SegmentedControl } from "@/components/ui/controls";
import { EmptyState, RequestError, Skeleton } from "@/components/ui/feedback";
import { Table, Td, Th } from "@/components/ui/table";
import { useEvalRuns } from "@/hooks/queries";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { formatDateTime, formatInteger } from "@/lib/format";
import { MODE } from "@/lib/labels";
import type { EvalMetric, EvalRun, RetrievalMode } from "@/types/api";

const MODE_ORDER: RetrievalMode[] = ["dense", "lexical", "hybrid", "hybrid_rerank"];

const METRIC_LABEL: Record<string, string> = {
  "recall@1": "Recall@1",
  "recall@5": "Recall@5",
  "recall@10": "Recall@10",
  "mrr@10": "MRR@10",
  refusal_rate: "Refused",
  "answered_recall@10": "Recall@10, refusals as misses",
  latency_p50_ms: "Latency p50 (ms)",
  latency_p95_ms: "Latency p95 (ms)",
  latency_mean_ms: "Latency mean (ms)",
};

/** What each query subset is, in the analyst's words. */
const SUBSET_LABEL: Record<string, string> = {
  all: "All labelled",
  semantic: "Semantic",
  identifier: "Identifier",
  in_scope: "Refusal, labelled",
  control: "Refusal, controls",
  out_of_scope: "Refusal, out of scope",
};

const SUBSET_ORDER = Object.keys(SUBSET_LABEL);

function label(name: string): string {
  return METRIC_LABEL[name] ?? name.replace(/_/g, " ");
}

function subsetLabel(subset: string): string {
  return SUBSET_LABEL[subset] ?? subset.replace(/_/g, " ");
}

/** A mode with no refusal threshold stores 0 with this note; it never refused anything. */
function neverRefuses(metric: EvalMetric): boolean {
  const note = metric.detail?.note;
  return typeof note === "string" && note.startsWith("This mode has no refusal threshold");
}

function detailNumber(metric: EvalMetric, key: string): number | null {
  const value = metric.detail?.[key];
  return typeof value === "number" ? value : null;
}

/** "0.760 (0.640–0.850)"; latency as whole milliseconds. */
function formatMetric(metric: EvalMetric): string {
  if (neverRefuses(metric)) return "never refuses";
  if (metric.metric_name.includes("latency") || metric.metric_name.endsWith("_ms")) {
    return formatInteger(Math.round(metric.metric_value));
  }
  const low = detailNumber(metric, "ci_low");
  const high = detailNumber(metric, "ci_high");
  const value = metric.metric_value.toFixed(3);
  return low !== null && high !== null ? `${value} (${low.toFixed(3)}–${high.toFixed(3)})` : value;
}

/** The newest finished run per key. */
function latestBy<K>(runs: EvalRun[], key: (run: EvalRun) => K): Map<K, EvalRun> {
  const out = new Map<K, EvalRun>();
  for (const run of runs) {
    const k = key(run);
    const current = out.get(k);
    if (!current || run.started_at > current.started_at) out.set(k, run);
  }
  return out;
}

function Provenance({ run }: { run: EvalRun }) {
  const config = run.config ?? {};
  const dirty = typeof config.dirty_digest === "string" ? config.dirty_digest : null;
  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm">
      <dt className="text-ink-soft">Code</dt>
      <dd className="break-words">
        {run.git_sha}
        {dirty ? ` with uncommitted changes (digest ${dirty.slice(0, 12)})` : ""}
      </dd>
      <dt className="text-ink-soft">Dataset</dt>
      <dd className="break-words">{run.dataset ?? "Not recorded"}</dd>
      <dt className="text-ink-soft">Finished</dt>
      <dd>{formatDateTime(run.finished_at, "Did not finish")}</dd>
      {run.notes ? (
        <>
          <dt className="text-ink-soft">Notes</dt>
          <dd>{run.notes}</dd>
        </>
      ) : null}
    </dl>
  );
}

function RetrievalAblation({ runs }: { runs: EvalRun[] }) {
  const latest = latestBy(runs, (run) => run.mode ?? "unknown");
  const modes = MODE_ORDER.filter((mode) => latest.has(mode));
  const subsets = useMemo(() => {
    const all = new Set<string>();
    latest.forEach((run) => run.results.forEach((r) => all.add(r.subset ?? "all")));
    const rank = (s: string) => (SUBSET_ORDER.includes(s) ? SUBSET_ORDER.indexOf(s) : SUBSET_ORDER.length);
    return [...all].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
  }, [latest]);
  const [subset, setSubset] = useState("all");
  const active = subsets.includes(subset) ? subset : (subsets[0] ?? "all");

  const metricNames = useMemo(() => {
    const names: string[] = [];
    latest.forEach((run) =>
      run.results
        .filter((r) => (r.subset ?? "all") === active)
        .forEach((r) => !names.includes(r.metric_name) && names.push(r.metric_name)),
    );
    return names;
  }, [latest, active]);

  const find = (mode: string, name: string) =>
    latest.get(mode)?.results.find((r) => r.metric_name === name && (r.subset ?? "all") === active);
  const queries = (mode: string) => {
    const any = latest.get(mode)?.results.find((r) => (r.subset ?? "all") === active);
    return any ? detailNumber(any, "n_queries") : null;
  };

  // Only ranking quality is charted; refusal and latency read better as numbers.
  const chartMetric = metricNames.includes("recall@10") ? "recall@10" : undefined;
  const chartData = modes.map((mode) => {
    const metric = chartMetric ? find(mode, chartMetric) : undefined;
    const low = metric ? detailNumber(metric, "ci_low") : null;
    const high = metric ? detailNumber(metric, "ci_high") : null;
    return {
      mode: MODE[mode].label,
      value: metric?.metric_value ?? 0,
      error:
        low !== null && high !== null && metric
          ? [metric.metric_value - low, high - metric.metric_value]
          : undefined,
    };
  });
  const tableLabel = `Retrieval metrics by mode, ${subsetLabel(active).toLowerCase()} queries`;

  return (
    <section aria-labelledby="ablation-head" className="flex flex-col gap-4 bg-paper px-4 py-4 sm:px-6">
      <GuideHead
        id="ablation-head"
        first={MODE[modes[0]]?.label}
        title="Retrieval ablation"
        last={MODE[modes[modes.length - 1]]?.label}
      />
      <p className="max-w-measure text-base text-ink-soft">
        Every mode answers the same query manifest through the same code path the search page uses. Relevance
        is judged against a gold set; see the provenance below for which one.
      </p>
      {subsets.length > 1 ? (
        <SegmentedControl
          label="Queries"
          value={active}
          options={subsets.map((s) => ({
            value: s,
            label: subsetLabel(s),
          }))}
          onChange={setSubset}
        />
      ) : null}
      <Table label={tableLabel} minWidth={640}>
        <thead>
          <tr>
            <Th>Mode</Th>
            <Th align="right">Queries</Th>
            {metricNames.map((name) => (
              <Th key={name} align="right">
                {label(name)}
              </Th>
            ))}
          </tr>
        </thead>
        <tbody>
          {modes.map((mode) => (
            <tr key={mode}>
              <Td className="font-semibold">{MODE[mode].label}</Td>
              <Td align="right">{queries(mode) ?? "—"}</Td>
              {metricNames.map((name) => {
                const metric = find(mode, name);
                return (
                  <Td key={name} align="right" className="whitespace-nowrap">
                    {metric ? formatMetric(metric) : "—"}
                  </Td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </Table>
      {chartMetric ? (
        <Plate tone="neutral">
          <figure className="flex flex-col gap-2">
            <figcaption className="text-sm font-semibold text-ink">
              {label(chartMetric)} by mode{chartData.some((d) => d.error) ? ", with 95% intervals" : ""} (the
              table above has the same numbers)
            </figcaption>
            <div className="h-56 w-full" aria-hidden>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
                  <CartesianGrid vertical={false} stroke="var(--rule)" />
                  <XAxis
                    dataKey="mode"
                    tick={{ fill: "var(--ink)", fontSize: 12 }}
                    axisLine={{ stroke: "var(--ink)" }}
                    tickLine={false}
                  />
                  <YAxis
                    domain={[0, 1]}
                    tick={{ fill: "var(--ink-soft)", fontSize: 12 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    cursor={{ fill: "var(--desk)" }}
                    formatter={(value: number) => value.toFixed(3)}
                    contentStyle={{ border: "1px solid var(--ink)", borderRadius: 3, fontSize: 13 }}
                  />
                  <Bar
                    dataKey="value"
                    name={label(chartMetric)}
                    fill="var(--new)"
                    maxBarSize={56}
                    isAnimationActive={false}
                  >
                    <ErrorBar dataKey="error" width={6} stroke="var(--ink)" strokeWidth={1.5} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </figure>
        </Plate>
      ) : null}
      <div className="grid gap-4 md:grid-cols-2">
        {modes.map((mode) => (
          <div key={mode} className="flex flex-col gap-1">
            <h3 className="text-sm font-semibold">{MODE[mode].label} run</h3>
            <Provenance run={latest.get(mode) as EvalRun} />
          </div>
        ))}
      </div>
    </section>
  );
}

function SuiteRun({ run }: { run: EvalRun }) {
  return (
    <section aria-labelledby={`suite-${run.id}`} className="flex flex-col gap-4 bg-paper px-4 py-4 sm:px-6">
      <GuideHead
        id={`suite-${run.id}`}
        title={`${run.suite.charAt(0).toUpperCase()}${run.suite.slice(1)} suite`}
      />
      <Table label={`${run.suite} metrics`}>
        <thead>
          <tr>
            <Th>Metric</Th>
            <Th>Subset</Th>
            <Th align="right">Value</Th>
            <Th align="right">N</Th>
          </tr>
        </thead>
        <tbody>
          {run.results.map((metric, index) => (
            <tr key={`${metric.metric_name}-${metric.subset}-${index}`}>
              <Td>{label(metric.metric_name)}</Td>
              <Td>{(metric.subset ?? "all").replace(/_/g, " ")}</Td>
              <Td align="right">{formatMetric(metric)}</Td>
              <Td align="right">{detailNumber(metric, "n") ?? detailNumber(metric, "n_queries") ?? "—"}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
      <Provenance run={run} />
    </section>
  );
}

/** Measured results stored by the evaluation harness, with their provenance. */
export default function Evaluation() {
  useDocumentTitle("Evaluation");
  const runs = useEvalRuns();
  const retrieval = runs.data?.filter((run) => run.suite === "retrieval") ?? [];
  const others = [
    ...latestBy(runs.data?.filter((run) => run.suite !== "retrieval") ?? [], (run) => run.suite).values(),
  ];

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Evaluation"
        context={
          <span className="inline-flex flex-wrap items-center gap-2">
            Measurements of this build on its own corpus. They describe the pipeline, not performance on real
            SEBI circulars.
            <SyntheticTag>Synthetic corpus</SyntheticTag>
          </span>
        }
      />
      {runs.isPending ? <Skeleton lines={8} label="evaluation runs" /> : null}
      {runs.isError ? (
        <RequestError error={runs.error} what="evaluation runs" onRetry={() => void runs.refetch()} />
      ) : null}
      {runs.data && runs.data.length === 0 ? (
        <div className="bg-paper px-5 py-4">
          <EmptyState title="No evaluation has been recorded in this database">
            Run <span className="font-semibold text-ink">make eval</span> against this database to measure
            every retrieval mode on the same queries. Results, with the code version that produced them,
            appear here.
          </EmptyState>
        </div>
      ) : null}
      {retrieval.length > 0 ? <RetrievalAblation runs={retrieval} /> : null}
      {others.map((run) => (
        <SuiteRun key={run.id} run={run} />
      ))}
    </div>
  );
}
