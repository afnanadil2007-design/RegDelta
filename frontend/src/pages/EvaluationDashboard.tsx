import { AblationTable } from "@/components/AblationTable";
import { Card, EmptyState, ErrorState, Mono, PageHeader, SkeletonRows } from "@/components/ui";
import { useEvalRuns } from "@/hooks/queries";

export default function EvaluationDashboard() {
  const runs = useEvalRuns();

  const retrieval = runs.data?.filter((r) => r.suite === "retrieval") ?? [];
  const latestSha = retrieval[0]?.git_sha;

  return (
    <div className="px-8 py-6">
      <PageHeader
        title="Evaluation"
        description="Retrieval quality, measured against a gold set mined from the corpus's citation graph."
      />

      {runs.isLoading ? (
        <SkeletonRows rows={8} />
      ) : runs.isError ? (
        <ErrorState what="evaluation runs" error={runs.error} onRetry={runs.refetch} />
      ) : retrieval.length === 0 ? (
        <EmptyState
          title="No evaluation runs recorded"
          hint="Run `make eval` to populate the ablation table."
        />
      ) : (
        <div className="space-y-6">
          <section>
            <div className="mb-2 flex items-baseline justify-between">
              <h2 className="text-sm font-semibold">Retrieval ablation</h2>
              {latestSha && (
                <Mono className="text-muted-foreground">commit {latestSha.slice(0, 8)}</Mono>
              )}
            </div>
            <Card className="p-1">
              <AblationTable runs={retrieval} />
            </Card>
            <p className="mt-2 text-xs text-muted-foreground">
              Relevance comes from resolved citations: a chunk counts as relevant when it
              belongs to the circular the querying paragraph cited. The{" "}
              <strong>semantic</strong> subset queries with the citing paragraph's prose;
              the <strong>identifier</strong> subset queries with the raw reference string.
              Reporting them separately is deliberate — either retriever alone fails one
              of them.
            </p>
          </section>

          <section>
            <h2 className="mb-2 text-sm font-semibold">Runs</h2>
            <Card>
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-muted-foreground">
                    <th className="px-4 py-2 font-medium">Suite</th>
                    <th className="px-4 py-2 font-medium">Mode</th>
                    <th className="px-4 py-2 font-medium">Commit</th>
                    <th className="px-4 py-2 font-medium">Dataset</th>
                    <th className="px-4 py-2 font-medium">Finished</th>
                  </tr>
                </thead>
                <tbody>
                  {(runs.data ?? []).map((run) => (
                    <tr key={run.id} className="border-b border-border/60">
                      <td className="px-4 py-2">{run.suite}</td>
                      <td className="px-4 py-2">
                        <Mono>{run.mode ?? "—"}</Mono>
                      </td>
                      <td className="px-4 py-2">
                        <Mono className="text-muted-foreground">
                          {run.git_sha.slice(0, 8)}
                        </Mono>
                      </td>
                      <td className="px-4 py-2 text-xs text-muted-foreground">
                        {run.dataset ?? "—"}
                      </td>
                      <td className="px-4 py-2 text-xs text-muted-foreground">
                        {run.finished_at ? new Date(run.finished_at).toLocaleString() : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </section>
        </div>
      )}
    </div>
  );
}
