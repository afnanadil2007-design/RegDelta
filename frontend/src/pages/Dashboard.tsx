import { Link } from "react-router-dom";

import { Card, EmptyState, ErrorState, Mono, PageHeader, SkeletonRows } from "@/components/ui";
import { useAssessments, useCirculars, usePolicyPacks } from "@/hooks/queries";
import type { CircularSummary } from "@/types/api";

export default function Dashboard() {
  const circulars = useCirculars();
  const assessments = useAssessments();
  const packs = usePolicyPacks();

  return (
    <div className="px-8 py-6">
      <PageHeader
        title="Dashboard"
        description="Corpus overview and recent assessment activity."
      />

      <div className="mb-6 grid gap-3 sm:grid-cols-3">
        <Stat
          label="Circulars ingested"
          value={circulars.data?.length}
          loading={circulars.isLoading}
        />
        <Stat
          label="Policy clauses"
          value={packs.data?.reduce((n, p) => n + p.clause_count, 0)}
          loading={packs.isLoading}
        />
        <Stat
          label="Assessments run"
          value={assessments.data?.length}
          loading={assessments.isLoading}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section>
          <h2 className="mb-2 text-sm font-semibold">Recent circulars</h2>
          {circulars.isLoading ? (
            <SkeletonRows rows={6} />
          ) : circulars.isError ? (
            <ErrorState what="circulars" error={circulars.error} onRetry={circulars.refetch} />
          ) : !circulars.data?.length ? (
            <EmptyState
              title="No circulars ingested yet"
              hint="Run `make seed` to build the demo corpus."
            />
          ) : (
            <Card>
              <ul className="divide-y divide-border">
                {circulars.data.slice(0, 8).map((circular) => (
                  <CircularRow key={circular.id} circular={circular} />
                ))}
              </ul>
            </Card>
          )}
        </section>

        <section>
          <h2 className="mb-2 text-sm font-semibold">Recent assessments</h2>
          {assessments.isLoading ? (
            <SkeletonRows rows={4} />
          ) : assessments.isError ? (
            <ErrorState
              what="assessments"
              error={assessments.error}
              onRetry={assessments.refetch}
            />
          ) : !assessments.data?.length ? (
            <EmptyState
              title="No assessments yet"
              hint="Open a circular and run an impact assessment against a policy pack."
            />
          ) : (
            <Card>
              <ul className="divide-y divide-border">
                {assessments.data.slice(0, 8).map((assessment) => (
                  <li key={assessment.id}>
                    <Link
                      to={`/assessments/${assessment.run_id}`}
                      className="flex items-center justify-between px-4 py-2.5 hover:bg-muted/50"
                    >
                      <Mono className="truncate">{assessment.circular_number}</Mono>
                      <span className="ml-3 shrink-0 text-xs text-muted-foreground">
                        {assessment.status.toLowerCase()}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </section>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  loading,
}: {
  label: string;
  value: number | undefined;
  loading: boolean;
}) {
  return (
    <Card className="px-4 py-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      {loading ? (
        <div className="mt-1 h-7 w-16 animate-pulse rounded bg-muted" />
      ) : (
        <div className="mt-0.5 font-mono text-2xl">{value ?? 0}</div>
      )}
    </Card>
  );
}

function CircularRow({ circular }: { circular: CircularSummary }) {
  return (
    <li>
      <Link
        to={`/circulars/${circular.id}`}
        className="flex items-start justify-between gap-3 px-4 py-2.5 hover:bg-muted/50"
      >
        <div className="min-w-0">
          <Mono className="block truncate">{circular.circular_number}</Mono>
          <span className="line-clamp-1 text-xs text-muted-foreground">
            {circular.title}
          </span>
        </div>
        <span className="shrink-0 text-xs text-muted-foreground">
          {circular.issue_date ?? "—"}
        </span>
      </Link>
    </li>
  );
}
