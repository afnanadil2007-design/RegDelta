import { Link, useSearchParams } from "react-router-dom";

import { AssessmentList } from "@/components/AssessmentList";
import { PageHeader } from "@/components/lexicon";
import { Pager } from "@/components/Pager";
import { EmptyState, RequestError, Skeleton } from "@/components/ui/feedback";
import { useAssessments } from "@/hooks/queries";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { plural } from "@/lib/format";

const LIMIT = 25;

export default function Assessments() {
  const [params, setParams] = useSearchParams();
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const runs = useAssessments({ limit: LIMIT, offset });

  useDocumentTitle("Assessments");

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Assessments"
        context="Each run compares one circular's obligations with the policy manual. Open a run to review its findings."
      />
      <section aria-label="Assessment runs" className="flex flex-col gap-4 bg-paper px-4 py-4 sm:px-6">
        {runs.isPending ? <Skeleton lines={6} label="assessments" /> : null}
        {runs.isError ? (
          <RequestError error={runs.error} what="assessments" onRetry={() => void runs.refetch()} />
        ) : null}
        {runs.data && runs.data.total === 0 ? (
          <EmptyState
            title="No assessments yet"
            action={
              <Link to="/circulars" className="font-semibold text-ink">
                Choose a circular to assess
              </Link>
            }
          >
            An assessment starts from a circular: open one, pick the policy manual, and start. The findings
            and the agent's trace appear as it runs.
          </EmptyState>
        ) : null}
        {runs.data && runs.data.total > 0 ? (
          <>
            <p className="text-sm text-ink-soft">
              {plural(runs.data.total, "run")}, newest first. New runs start from a{" "}
              <Link to="/circulars" className="text-ink">
                circular
              </Link>
              .
            </p>
            <AssessmentList runs={runs.data.items} label="Assessment runs" />
            <Pager
              offset={offset}
              limit={LIMIT}
              total={runs.data.total}
              noun="runs"
              onChange={(next) => setParams(next ? { offset: String(next) } : {})}
            />
          </>
        ) : null}
      </section>
    </div>
  );
}
