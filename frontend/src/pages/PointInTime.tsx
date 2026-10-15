import { CalendarClock, CircleCheck, CircleSlash, Hourglass } from "lucide-react";
import { type ReactNode, useEffect, useId, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { GuideHead, Ident, PageHeader, ShoulderArrow, SyntheticTag } from "@/components/lexicon";
import {
  isAbort,
  ModeControl,
  QueryField,
  SubmitOrCancel,
  useCancellableSearch,
  useElapsed,
} from "@/components/SearchForm";
import { SearchResults } from "@/components/SearchResults";
import { Button, Field, Input } from "@/components/ui/controls";
import { EmptyState, Notice, RequestError, Skeleton } from "@/components/ui/feedback";
import { useCircular, useCirculars, useCircularsById } from "@/hooks/queries";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { formatDate } from "@/lib/format";
import { forceOn, isIsoDate, today, type ForceState } from "@/lib/temporal";
import { queryTerms } from "@/lib/text";
import { cn } from "@/lib/utils";
import type { CircularDetail, RetrievalMode, Supersession } from "@/types/api";

/** An icon and its words; when the words wrap, the icon stays beside the first line. */
function Marked({ icon, className, children }: { icon: ReactNode; className?: string; children: ReactNode }) {
  return (
    <span className={cn("inline-flex items-start gap-1.5", className)}>
      <span className="flex h-[1.5em] shrink-0 items-center">{icon}</span>
      <span>{children}</span>
    </span>
  );
}

function StateLine({ state, date }: { state: ForceState; date: string }) {
  const on = formatDate(date);
  switch (state.kind) {
    case "not-issued":
      return (
        <Marked icon={<Hourglass aria-hidden className="size-4" />} className="text-ink-soft">
          Not yet issued on {on}
        </Marked>
      );
    case "out-of-force":
      return (
        <Marked
          icon={<CircleSlash aria-hidden className="size-4" />}
          className="font-semibold text-impact-conflict"
        >
          Out of force on {on} (since {formatDate(state.since)})
        </Marked>
      );
    case "unknown-date":
      return <span className="text-ink-soft">No issue date recorded, so its force on {on} is unknown</span>;
    default:
      return (
        <Marked
          icon={<CircleCheck aria-hidden className="size-4" />}
          className="font-semibold text-impact-covered"
        >
          In force on {on}
          {state.amendedBy.length ? <span className="font-normal text-ink">, as amended</span> : null}
        </Marked>
      );
  }
}

function relation(edge: Supersession, selectedId: number): string {
  const effective = edge.effective_date
    ? ` from ${formatDate(edge.effective_date)}`
    : " (no effective date recorded)";
  const amends = edge.supersession_type === "amends";
  if (edge.superseding_circular_id === selectedId) {
    return amends
      ? `Amended by the selected circular${effective}`
      : `Taken out of force by the selected circular${effective}`;
  }
  return amends
    ? `Amends the selected circular${effective}`
    : `Takes the selected circular out of force${effective}`;
}

interface Node {
  detail: CircularDetail;
  edge: Supersession | null;
}

/** The selected circular and its direct predecessors and successors on one spine. */
function Timeline({
  selected,
  neighbours,
  date,
  children,
}: {
  selected: CircularDetail;
  neighbours: CircularDetail[];
  date: string;
  children?: React.ReactNode;
}) {
  const headId = useId();
  const nodes: Node[] = [
    { detail: selected, edge: null },
    ...neighbours.map((detail) => ({
      detail,
      edge:
        selected.supersessions.find(
          (s) =>
            s.superseded_circular_id === detail.circular.id ||
            s.superseding_circular_id === detail.circular.id,
        ) ?? null,
    })),
  ].sort((a, b) => (a.detail.circular.issue_date ?? "").localeCompare(b.detail.circular.issue_date ?? ""));
  const markerAt = nodes.findIndex((n) => (n.detail.circular.issue_date ?? "") > date);
  const rows: (Node | "marker")[] = [...nodes];
  rows.splice(markerAt === -1 ? rows.length : markerAt, 0, "marker");

  return (
    <section aria-labelledby={headId} className="flex flex-col gap-4 bg-paper px-4 py-4 sm:px-6">
      <GuideHead
        id={headId}
        first={formatDate(nodes[0]?.detail.circular.issue_date)}
        title="Timeline"
        last={formatDate(nodes[nodes.length - 1]?.detail.circular.issue_date)}
      />
      {neighbours.length === 0 ? (
        <p className="text-sm text-ink-soft">
          No other circular supersedes, rescinds, or amends this one, and it changes no other.
        </p>
      ) : null}
      <ol className="relative flex flex-col">
        <span
          aria-hidden
          className="absolute bottom-3 left-[6.75rem] top-3 w-[1.5px] bg-ink sm:left-[7.75rem]"
        />
        {rows.map((row) => {
          if (row === "marker") {
            return (
              <li
                key="marker"
                className="grid grid-cols-[6.25rem_1rem_minmax(0,1fr)] items-center gap-x-2 py-2 sm:grid-cols-[7.25rem_1rem_minmax(0,1fr)]"
              >
                <span className="guide-words text-right text-ink">{formatDate(date)}</span>
                <span
                  aria-hidden
                  className="relative z-10 mx-auto size-3 rotate-45 border-[1.5px] border-ink bg-paper"
                />
                <span className="flex items-center gap-2 text-sm font-semibold text-ink">
                  <CalendarClock aria-hidden className="size-4" /> Chosen date
                  <span aria-hidden className="h-px flex-1 border-t-[1.5px] border-dashed border-ink" />
                </span>
              </li>
            );
          }
          const { detail, edge } = row;
          const isSelected = detail.circular.id === selected.circular.id;
          const state = forceOn(detail, date);
          return (
            <li
              key={detail.circular.id}
              className="grid grid-cols-[6.25rem_1rem_minmax(0,1fr)] gap-x-2 py-2 sm:grid-cols-[7.25rem_1rem_minmax(0,1fr)]"
            >
              <span
                className={cn(
                  "guide-words flex items-start justify-end gap-1.5 pt-3 text-right",
                  isSelected ? "text-ink" : "text-ink-soft",
                )}
              >
                {isSelected ? <ShoulderArrow className="mt-1 shrink-0" /> : null}
                {formatDate(detail.circular.issue_date)}
                {isSelected ? <span className="sr-only"> (selected circular)</span> : null}
              </span>
              <span aria-hidden className="relative mt-[1.1rem] h-[1.5px] bg-ink" />
              <div
                className={cn(
                  "flex min-w-0 flex-col gap-1 bg-raised px-3 py-2.5",
                  isSelected ? "border-2 border-ink" : "border-[1.5px]",
                  !isSelected &&
                    (state.kind === "out-of-force" ? "border-dashed border-ink-faint" : "border-ink-faint"),
                )}
              >
                <Link to={`/circulars/${detail.circular.id}`} className="font-semibold text-ink break-words">
                  <Ident value={detail.circular.circular_number} />
                </Link>
                <span className="text-sm">{detail.circular.title}</span>
                {edge ? (
                  <span className="text-sm text-ink-soft">{relation(edge, selected.circular.id)}</span>
                ) : null}
                <span className="text-sm">
                  <StateLine state={state} date={date} />
                </span>
                {state.kind === "in-force" && state.undated.length ? (
                  <span className="text-xs text-ink-soft">
                    A superseding circular has no recorded effective date, so the date filter does not apply
                    it.
                  </span>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>
      {children}
    </section>
  );
}

function CircularLookup({ onPick }: { onPick: (id: number) => void }) {
  const [text, setText] = useState("");
  const [term, setTerm] = useState("");
  useEffect(() => {
    const timer = window.setTimeout(() => setTerm(text.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [text]);
  const matches = useCirculars({ q: term || undefined, limit: 6 });
  return (
    <div className="flex flex-col gap-2">
      <Field label="Find a circular" hint="Part of its number or title">
        {({ id, describedBy }) => (
          <Input
            id={id}
            type="search"
            value={text}
            aria-describedby={describedBy}
            onChange={(e) => setText(e.target.value)}
          />
        )}
      </Field>
      {matches.isError ? (
        <RequestError error={matches.error} what="circulars" onRetry={() => void matches.refetch()} />
      ) : null}
      {matches.data ? (
        matches.data.items.length === 0 ? (
          <p className="text-sm text-ink-soft">No circular matches “{term}”.</p>
        ) : (
          <ul className="flex flex-col" aria-label="Matching circulars">
            {matches.data.items.map((circular) => (
              <li key={circular.id}>
                <button
                  type="button"
                  onClick={() => onPick(circular.id)}
                  className="flex w-full flex-col items-start border-b border-rule px-1 py-2 text-left transition-colors duration-150 hover:bg-raised"
                >
                  <span className="text-sm font-semibold break-words">
                    <Ident value={circular.circular_number} />
                  </span>
                  <span className="text-sm text-ink-soft">
                    {circular.title} · {formatDate(circular.issue_date)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )
      ) : null}
    </div>
  );
}

/** What was in force on a date: one circular's lineage, and a search limited to that date. */
export default function PointInTime() {
  useDocumentTitle("Point in time");
  const [params, setParams] = useSearchParams();
  const asOfParam = params.get("as_of");
  const date = isIsoDate(asOfParam) ? asOfParam : today();
  const circularParam = Number(params.get("circular"));
  const circularId = Number.isInteger(circularParam) && circularParam > 0 ? circularParam : null;

  const set = (changes: Record<string, string | null>) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        for (const [key, value] of Object.entries(changes)) {
          if (value) next.set(key, value);
          else next.delete(key);
        }
        return next;
      },
      { replace: true },
    );

  const selected = useCircular(circularId);
  const neighbourIds = useMemo(() => {
    const ids = new Set<number>();
    for (const edge of selected.data?.supersessions ?? []) {
      const other =
        edge.direction === "outgoing" ? edge.superseded_circular_id : edge.superseding_circular_id;
      if (other && edge.resolved) ids.add(other);
    }
    return [...ids];
  }, [selected.data]);
  const neighbours = useCircularsById(neighbourIds);
  const neighbourDetails = neighbours.map((q) => q.data).filter((d): d is CircularDetail => Boolean(d));
  const neighboursLoading = neighbours.some((q) => q.isPending);
  const neighbourError = neighbours.find((q) => q.isError);

  const [text, setText] = useState(params.get("q") ?? "");
  const [mode, setMode] = useState<RetrievalMode>("hybrid");
  const [queryError, setQueryError] = useState<string | null>(null);
  const { search, run, cancel } = useCancellableSearch();
  const elapsed = useElapsed(search.isPending);

  const ask = (event: React.FormEvent) => {
    event.preventDefault();
    if (!text.trim()) {
      setQueryError("Type a question or a few words to search for.");
      return;
    }
    setQueryError(null);
    set({ q: text.trim() });
    run({ query: text.trim(), mode, as_of: date });
  };

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Point in time"
        context={
          <span className="inline-flex flex-wrap items-center gap-2">
            What was in force on a date. A superseded or rescinded circular drops out from its effective date;
            an amended one stays in force as amended.
            <SyntheticTag>Synthetic corpus</SyntheticTag>
          </span>
        }
      />
      <div className="flex flex-wrap items-end gap-3 bg-paper px-4 py-4 sm:px-6">
        <Field label="Date" hint="Everything on this page is shown as of this day.">
          {({ id, describedBy }) => (
            <Input
              id={id}
              type="date"
              className="w-48"
              value={date}
              aria-describedby={describedBy}
              onChange={(event) => isIsoDate(event.target.value) && set({ as_of: event.target.value })}
            />
          )}
        </Field>
        <Button variant="quiet" onClick={() => set({ as_of: null })} disabled={!asOfParam}>
          Today
        </Button>
      </div>

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-5">
          {circularId === null ? (
            <section
              aria-label="Choose a circular"
              className="flex flex-col gap-3 bg-paper px-4 py-4 sm:px-6"
            >
              <GuideHead title="Timeline" />
              <p className="text-base text-ink-soft">
                Pick a circular to see what it replaced, what replaced it, and which of them were in force on
                the date.
              </p>
              <CircularLookup onPick={(id) => set({ circular: String(id) })} />
            </section>
          ) : selected.isPending ? (
            <Skeleton lines={6} label="the timeline" />
          ) : selected.isError ? (
            <RequestError
              error={selected.error}
              what="the circular"
              onRetry={() => void selected.refetch()}
            />
          ) : selected.data ? (
            <>
              {neighbourError ? (
                <RequestError
                  error={neighbourError.error}
                  what="a related circular"
                  onRetry={() => void neighbourError.refetch()}
                />
              ) : null}
              {neighboursLoading ? <Skeleton lines={3} label="related circulars" /> : null}
              <Timeline selected={selected.data} neighbours={neighbourDetails} date={date}>
                <div>
                  <Button variant="quiet" className="-ml-3" onClick={() => set({ circular: null })}>
                    Choose another circular
                  </Button>
                </div>
              </Timeline>
            </>
          ) : null}
        </div>

        <section aria-label="Search on this date" className="flex flex-col gap-4 bg-paper px-4 py-4 sm:px-6">
          <GuideHead title="Search on this date" last={formatDate(date)} />
          <form onSubmit={ask} className="flex flex-col gap-4" noValidate>
            <QueryField
              label="What were the rules on…"
              hint="Only circulars issued by the date and still in force on it are searched."
              value={text}
              onChange={setText}
              error={queryError}
            />
            <ModeControl mode={mode} onChange={setMode} />
            <SubmitOrCancel pending={search.isPending} elapsed={elapsed} onCancel={cancel} />
          </form>
          {search.isPending ? <Skeleton lines={4} label="results" /> : null}
          {search.isError && !isAbort(search.error) ? (
            <RequestError
              error={search.error}
              what="results"
              onRetry={() => run({ query: text.trim(), mode, as_of: date })}
            />
          ) : null}
          {search.data && !search.isPending ? (
            <SearchResults result={search.data} terms={queryTerms(text)} asOf={date} />
          ) : null}
          {search.isIdle && !search.data ? (
            <EmptyState title="Ask about a date">
              For example, search “margin collection” as of 30 June 2023, then move the date past a
              superseding circular and search again to see which circulars drop out.
            </EmptyState>
          ) : null}
          {search.data && date !== (search.variables?.body.as_of ?? date) ? (
            <Notice tone="info" title="The date changed after this search">
              Search again to apply {formatDate(date)}.
            </Notice>
          ) : null}
        </section>
      </div>
    </div>
  );
}
