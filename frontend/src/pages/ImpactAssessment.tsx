import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { AgentTrace } from "@/components/AgentTrace";
import { EvidencePane } from "@/components/EvidencePane";
import { FindingsTable } from "@/components/FindingsTable";
import {
  AiGenerated,
  Card,
  EmptyState,
  ErrorState,
  Mono,
  PageHeader,
  SkeletonRows,
} from "@/components/ui";
import { useAssessment, useAssessments, useSetDecision } from "@/hooks/queries";
import { useAssessmentStream } from "@/hooks/useAssessmentStream";
import type { Finding } from "@/types/api";

export default function ImpactAssessment() {
  const { runId } = useParams<{ runId: string }>();
  return runId ? <AssessmentView runId={runId} /> : <AssessmentList />;
}

function AssessmentList() {
  const assessments = useAssessments();

  return (
    <div className="px-8 py-6">
      <PageHeader
        title="Impact Assessment"
        description="Assessments of circulars against the internal policy pack."
      />
      {assessments.isLoading ? (
        <SkeletonRows rows={6} />
      ) : assessments.isError ? (
        <ErrorState
          what="assessments"
          error={assessments.error}
          onRetry={assessments.refetch}
        />
      ) : !assessments.data?.length ? (
        <EmptyState
          title="No assessments yet"
          hint="Open a circular and choose “Run impact assessment”."
        />
      ) : (
        <Card>
          <ul className="divide-y divide-border">
            {assessments.data.map((a) => (
              <li key={a.id}>
                <a
                  href={`/assessments/${a.run_id}`}
                  className="flex items-center justify-between px-4 py-3 hover:bg-muted/50"
                >
                  <Mono>{a.circular_number}</Mono>
                  <span className="text-xs text-muted-foreground">
                    {a.status.toLowerCase()} · {a.total_tokens.toLocaleString()} tok
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function AssessmentView({ runId }: { runId: string }) {
  const stream = useAssessmentStream(runId);
  const isRunning = stream.status === null;
  const assessment = useAssessment(runId, isRunning);
  const setDecision = useSetDecision(runId);
  const [selected, setSelected] = useState<Finding | null>(null);

  // Keep the selected finding in sync with refetched data.
  useEffect(() => {
    if (!selected || !assessment.data) return;
    const fresh = assessment.data.findings.find((f) => f.id === selected.id);
    if (fresh && fresh.analyst_decision !== selected.analyst_decision) setSelected(fresh);
  }, [assessment.data, selected]);

  const data = assessment.data;
  const status = data?.status ?? stream.status;

  return (
    <div className="px-8 py-6">
      <PageHeader
        title="Impact Assessment"
        description={data?.circular_number ?? runId}
        actions={
          status && (
            <span className="rounded-full bg-muted px-2.5 py-1 font-mono text-xs">
              {status.toLowerCase()}
            </span>
          )
        }
      />

      {status === "FAILED" && (
        <Card className="mb-4 border-impact-conflict/30 bg-impact-conflict/5 p-4">
          <p className="text-sm font-medium text-impact-conflict">Assessment failed</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {data?.error_reason ??
              "The assessment could not be completed. Check the provider configuration."}
          </p>
          <p className="mt-2 text-xs text-muted-foreground">
            Run ID <Mono>{data?.run_id ?? runId}</Mono>
          </p>
        </Card>
      )}
      {status === "CAPPED" && data?.error_reason && (
        <Card className="mb-4 border-impact-modified/40 bg-impact-modified/5 p-3">
          <p className="text-sm text-impact-modified">{data.error_reason}</p>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-6 min-w-0">
          <section>
            <h2 className="mb-2 text-sm font-semibold">
              Findings{" "}
              <span className="font-normal text-muted-foreground">
                ({data?.findings.length ?? 0})
              </span>
            </h2>
            {assessment.isLoading ? (
              <SkeletonRows rows={5} />
            ) : !data?.findings.length ? (
              <EmptyState
                title={isRunning ? "Findings will appear as the agent works" : "No findings"}
                hint={
                  isRunning
                    ? "The trace on the right updates as each graph node completes."
                    : "The agent produced no verified findings for this circular."
                }
              />
            ) : (
              <Card>
                <FindingsTable
                  findings={data.findings}
                  selectedId={selected?.id ?? null}
                  onSelect={setSelected}
                />
              </Card>
            )}
          </section>

          {selected && (
            <section>
              <h2 className="mb-2 text-sm font-semibold">Evidence</h2>
              <EvidencePane
                finding={selected}
                deciding={setDecision.isPending}
                onDecide={(decision) =>
                  setDecision.mutate({ findingId: selected.id, decision })
                }
              />
            </section>
          )}

          {data?.memo && (
            <section>
              <h2 className="mb-2 text-sm font-semibold">Memo</h2>
              <AiGenerated label="AI-generated memo">
                <div className="whitespace-pre-wrap">{data.memo}</div>
              </AiGenerated>
            </section>
          )}
        </div>

        <aside>
          <h2 className="mb-2 text-sm font-semibold">Agent trace</h2>
          <Card className="p-3">
            <AgentTrace
              steps={stream.steps}
              status={stream.status}
              connected={stream.connected}
            />
          </Card>
          {data && (
            <div className="mt-3 space-y-1 px-1 text-xs text-muted-foreground">
              <Row label="Tokens" value={data.total_tokens.toLocaleString()} />
              <Row label="Est. API cost" value={`$${data.total_cost_usd.toFixed(4)}`} />
              <Row label="Run" value={data.run_id.slice(0, 8)} />
              <p className="pt-1 text-[10px] leading-snug text-muted-foreground/80">
                Cost is a list-price estimate from token usage, not a billed amount.
              </p>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span>{label}</span>
      <Mono>{value}</Mono>
    </div>
  );
}
