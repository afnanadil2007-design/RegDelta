import { useId } from "react";
import { Link } from "react-router-dom";

import { AssessmentList } from "@/components/AssessmentList";
import { GuideHead, Ident, PageHeader, SyntheticTag } from "@/components/lexicon";
import { EmptyState, RequestError, Skeleton } from "@/components/ui/feedback";
import { useAssessments, useCirculars, useDepartments, useHealth, usePolicyPacks } from "@/hooks/queries";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { formatDate, formatInteger, plural } from "@/lib/format";
import { providerLabel } from "@/lib/labels";

function Leaf({
  title,
  first,
  last,
  children,
}: {
  title: string;
  first?: string;
  last?: string;
  children: React.ReactNode;
}) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="flex min-w-0 flex-col gap-4 bg-paper px-4 py-4 sm:px-6">
      <GuideHead id={id} first={first} title={title} last={last} />
      {children}
    </section>
  );
}

function Workflow() {
  return (
    <ol className="flex flex-col gap-3">
      {[
        ["Open a circular", "Its obligations are already extracted and marked in the text."],
        ["Start an assessment", "Each obligation is compared with the closest clauses of the policy manual."],
        [
          "Review the evidence",
          "Read the quoted passage beside the clause, check the quote status, and accept or reject.",
        ],
      ].map(([title, body], index) => (
        <li key={title} className="grid grid-cols-[2.25rem_minmax(0,1fr)] gap-x-2">
          <span className="guide-words pt-0.5 text-right text-ink-soft">{index + 1}</span>
          <span>
            <span className="block font-semibold">{title}</span>
            <span className="text-ink-soft">{body}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

/** Where the analyst starts: runs waiting for decisions, then what is new in the corpus. */
export default function Overview() {
  useDocumentTitle("Overview");
  const runs = useAssessments({ limit: 20 });
  const latest = useCirculars({ limit: 6 });
  const departments = useDepartments();
  const packs = usePolicyPacks();
  const health = useHealth();

  const open = runs.data?.items.filter(
    (run) => run.status === "RUNNING" || run.status === "PENDING" || run.counts.decision_pending > 0,
  );
  const pending = open?.reduce((sum, run) => sum + run.counts.decision_pending, 0) ?? 0;
  const items = latest.data?.items ?? [];

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Overview"
        context={
          <span className="inline-flex flex-wrap items-center gap-2">
            SEBI-style circulars compared, obligation by obligation, with a broker's compliance manual.
            <SyntheticTag>Synthetic data throughout</SyntheticTag>
          </span>
        }
      />
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_380px] wide:grid-cols-[minmax(0,1fr)_440px]">
        <Leaf
          title="Awaiting review"
          first={open?.length ? plural(open.length, "run") : undefined}
          last={pending ? `${formatInteger(pending)} undecided` : undefined}
        >
          {runs.isPending ? <Skeleton lines={5} label="assessments" /> : null}
          {runs.isError ? (
            <RequestError error={runs.error} what="assessments" onRetry={() => void runs.refetch()} />
          ) : null}
          {runs.data && runs.data.total === 0 ? (
            <>
              <EmptyState title="No assessment has been run yet">
                Every finding RegDelta makes comes from an assessment you start. This is how a review goes:
              </EmptyState>
              <Workflow />
              <p>
                <Link to="/circulars" className="font-semibold text-ink">
                  Choose a circular
                </Link>
              </p>
            </>
          ) : null}
          {open && runs.data && runs.data.total > 0 && open.length === 0 ? (
            <EmptyState
              title="Every finding has a decision"
              action={
                <Link to="/assessments" className="font-semibold text-ink">
                  See all assessments
                </Link>
              }
            >
              Nothing among the latest {plural(runs.data.items.length, "run")} is waiting for you.
            </EmptyState>
          ) : null}
          {open && open.length > 0 ? (
            <>
              <AssessmentList runs={open} label="Assessments awaiting review" />
              <Link to="/assessments" className="text-sm font-semibold text-ink">
                All assessments
              </Link>
            </>
          ) : null}
        </Leaf>

        <div className="flex flex-col gap-5">
          <Leaf
            title="Latest circulars"
            first={items.length ? formatDate(items[items.length - 1].issue_date) : undefined}
            last={items.length ? formatDate(items[0].issue_date) : undefined}
          >
            {latest.isPending ? <Skeleton lines={5} label="circulars" /> : null}
            {latest.isError ? (
              <RequestError error={latest.error} what="circulars" onRetry={() => void latest.refetch()} />
            ) : null}
            {latest.data && items.length === 0 ? (
              <EmptyState title="The corpus is empty">
                Build the demo database with <span className="font-semibold text-ink">make seed</span>.
              </EmptyState>
            ) : null}
            {items.length > 0 ? (
              <ul className="flex flex-col">
                {items.map((circular) => (
                  <li
                    key={circular.id}
                    className="flex flex-col gap-0.5 border-b border-rule py-2.5 first:pt-0 last:border-0"
                  >
                    <Link to={`/circulars/${circular.id}`} className="font-semibold text-ink break-words">
                      <Ident value={circular.circular_number} />
                    </Link>
                    <span>{circular.title}</span>
                    <span className="text-sm text-ink-soft">
                      {formatDate(circular.issue_date)} · {plural(circular.obligation_count, "obligation")}
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}
          </Leaf>
          <Leaf title="This database">
            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-base">
              <dt className="text-ink-soft">Circulars</dt>
              <dd>
                {latest.data ? formatInteger(latest.data.total) : "—"}
                {departments.data ? ` from ${plural(departments.data.length, "department")}` : ""}
              </dd>
              <dt className="text-ink-soft">Manual</dt>
              <dd>
                {packs.data?.length
                  ? packs.data
                      .map((pack) => `${pack.name} (${plural(pack.clause_count, "clause")})`)
                      .join("; ")
                  : packs.isPending
                    ? "—"
                    : "None loaded"}
              </dd>
              <dt className="text-ink-soft">Judge</dt>
              <dd>
                {health.data
                  ? health.data.provider.ready
                    ? providerLabel(health.data.provider)
                    : `Not configured: ${health.data.provider.reason ?? "see the API settings"}`
                  : "—"}
              </dd>
              <dt className="text-ink-soft">Schema</dt>
              <dd>{health.data?.schema_revision ?? "—"}</dd>
            </dl>
          </Leaf>
        </div>
      </div>
    </div>
  );
}
