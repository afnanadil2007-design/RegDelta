import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { CircularLeaf } from "@/components/assessment/CircularLeaf";
import { ClauseLeaf } from "@/components/assessment/ClauseLeaf";
import { DecisionBar } from "@/components/assessment/DecisionBar";
import { FindingNavigator, FindingsIndex, ImpactLegend } from "@/components/assessment/FindingsIndex";
import { isNotFound, RunFacts, RunNotices } from "@/components/assessment/RunSummary";
import { MemoSection, TraceSection } from "@/components/assessment/RunSections";
import { VerdictPlate } from "@/components/assessment/VerdictPlate";
import { Ident, PageHeader } from "@/components/lexicon";
import { Notice, EmptyState, RequestError, Skeleton } from "@/components/ui/feedback";
import {
  useAssessment,
  useAssessmentSteps,
  useCircular,
  usePolicyClauses,
  usePolicyPacks,
} from "@/hooks/queries";
import { useAssessmentStream } from "@/hooks/useAssessmentStream";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { groupFindings } from "@/lib/evidence";
import { formatDate } from "@/lib/format";
import type { ImpactType } from "@/types/api";

const IMPACTS = new Set<ImpactType>([
  "CONFLICT",
  "MODIFIED",
  "NEW_REQUIREMENT",
  "ALREADY_COVERED",
  "NO_MATCH",
]);

/**
 * The evidence workspace for one run: the findings index beside the circular
 * and the manual, the machine's interpretation as a plate, and the analyst's
 * decision. The selected finding and the impact filter live in the URL.
 */
export default function AssessmentWorkspace() {
  const { runId = null } = useParams();
  const [params, setParams] = useSearchParams();
  const assessment = useAssessment(runId);
  const run = assessment.data;
  const inProgress = run?.status === "RUNNING" || run?.status === "PENDING";

  const [generation, setGeneration] = useState(0);
  const trace = useAssessmentStream(runId, inProgress, generation);
  const storedSteps = useAssessmentSteps(runId, Boolean(run) && !inProgress);
  const steps = inProgress ? trace.steps : (storedSteps.data ?? trace.steps);

  const circular = useCircular(run?.circular_id ?? null);
  const packs = usePolicyPacks();
  const clauses = usePolicyClauses(run?.policy_pack_id ?? null);
  const pack = packs.data?.find((p) => p.id === run?.policy_pack_id);

  const impactParam = params.get("impact") as ImpactType | null;
  const impact = impactParam && IMPACTS.has(impactParam) ? impactParam : null;

  const findings = useMemo(() => run?.findings ?? [], [run?.findings]);
  const groups = useMemo(() => groupFindings(findings, circular.data?.paragraphs), [findings, circular.data]);
  const shownGroups = useMemo(
    () =>
      impact
        ? groups
            .map((g) => ({ ...g, findings: g.findings.filter((f) => f.impact_type === impact) }))
            .filter((g) => g.findings.length > 0)
        : groups,
    [groups, impact],
  );
  const order = useMemo(() => shownGroups.flatMap((g) => g.findings), [shownGroups]);

  const requested = params.get("finding");
  const requestedFinding = requested ? findings.find((f) => String(f.id) === requested) : undefined;
  const selected = requestedFinding ?? order[0] ?? findings[0];
  const unknownRequest = Boolean(requested) && findings.length > 0 && !requestedFinding && !inProgress;

  const update = (changes: Record<string, string | null>) => {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        for (const [key, value] of Object.entries(changes)) {
          if (value === null) next.delete(key);
          else next.set(key, value);
        }
        return next;
      },
      { replace: true },
    );
  };
  const select = (id: number) => update({ finding: String(id) });

  const [traceOpen, setTraceOpen] = useState(false);
  useEffect(() => {
    if (inProgress) setTraceOpen(true);
  }, [inProgress]);

  useDocumentTitle(run ? `${run.circular_title ?? "Assessment"} · Assessment` : "Assessment");

  if (assessment.isPending) {
    return <Skeleton lines={8} label="the assessment" />;
  }
  if (assessment.isError || !run) {
    if (isNotFound(assessment.error)) {
      return (
        <EmptyState
          title="No assessment with this ID"
          action={
            <Link to="/assessments" className="font-semibold text-ink">
              Go to all assessments
            </Link>
          }
        >
          The link may be from another database. Every stored run is listed on the assessments page.
        </EmptyState>
      );
    }
    return (
      <RequestError
        error={assessment.error}
        what="the assessment"
        onRetry={() => void assessment.refetch()}
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={run.circular_title ?? "Assessment"}
        context={
          <span className="flex flex-col gap-1">
            <span>
              {run.circular_number ? <Ident value={run.circular_number} /> : "Unknown circular"} against{" "}
              {run.policy_pack_name ?? "an unknown manual"}
              {run.policy_pack_version ? ` (version ${run.policy_pack_version})` : ""}
              {run.as_of ? ` · text in force on ${formatDate(run.as_of)}` : ""}
            </span>
            <RunFacts run={run} />
          </span>
        }
        actions={
          <Link to="/assessments" className="text-sm font-semibold text-ink">
            All assessments
          </Link>
        }
      />
      <RunNotices
        run={run}
        trace={trace}
        inProgress={inProgress}
        onReconnect={() => setGeneration((g) => g + 1)}
      />
      {unknownRequest ? (
        <Notice tone="info" title={`Finding ${requested} is not part of this run`}>
          Showing the first finding instead.
        </Notice>
      ) : null}

      {!selected ? (
        <div className="bg-paper px-5 py-4">
          <EmptyState title={inProgress ? "No findings yet" : "This run has no findings"}>
            {inProgress
              ? "Each obligation's finding appears as soon as it is judged and its quotes are checked. The trace below shows the agent's progress."
              : run.obligation_count === 0
                ? "The circular has no extracted obligations, so there was nothing to assess."
                : "No finding was stored. The trace below shows where the run stopped."}
          </EmptyState>
        </div>
      ) : (
        <div className="grid items-start gap-4 wide:grid-cols-[300px_minmax(0,1fr)]">
          <aside
            aria-label="Findings index"
            className="hidden bg-paper wide:sticky wide:top-[4.5rem] wide:flex wide:max-h-[calc(100dvh-5.5rem)] wide:flex-col"
          >
            <div className="px-4 pt-4">
              <ImpactLegend
                counts={run.counts}
                active={impact}
                onToggle={(value) => update({ impact: value })}
              />
            </div>
            <FindingsIndex
              groups={shownGroups}
              order={order}
              selectedId={selected.id}
              onSelect={select}
              className="min-h-0 overflow-y-auto"
            />
          </aside>

          <div className="flex min-w-0 flex-col gap-4">
            <div className="flex flex-col gap-3 bg-paper wide:hidden">
              <div className="px-4 pt-3">
                <ImpactLegend
                  counts={run.counts}
                  active={impact}
                  onToggle={(value) => update({ impact: value })}
                />
              </div>
              <FindingNavigator
                groups={shownGroups}
                order={order.includes(selected) ? order : [selected, ...order]}
                selectedId={selected.id}
                onSelect={select}
                className="pt-0"
              />
            </div>
            <div className="grid items-start gap-4 lg:grid-cols-2">
              <CircularLeaf
                finding={selected}
                detail={circular.data}
                loading={circular.isPending}
                error={circular.error}
                onRetry={() => void circular.refetch()}
              >
                <VerdictPlate finding={selected} provider={run.provider} />
              </CircularLeaf>
              <ClauseLeaf
                finding={selected}
                pack={pack}
                clauses={clauses.data}
                loading={clauses.isPending}
                error={clauses.error}
                onRetry={() => void clauses.refetch()}
              >
                <DecisionBar key={selected.id} finding={selected} runId={run.run_id} />
              </ClauseLeaf>
            </div>
          </div>
        </div>
      )}

      <MemoSection run={run} inProgress={inProgress} />
      <TraceSection
        steps={steps}
        live={inProgress}
        open={traceOpen}
        onToggle={() => setTraceOpen((open) => !open)}
        error={storedSteps.isError && !inProgress ? storedSteps.error : null}
        onRetry={() => void storedSteps.refetch()}
      />
    </div>
  );
}
