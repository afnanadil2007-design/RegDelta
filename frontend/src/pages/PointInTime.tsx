import { useState } from "react";
import { Link } from "react-router-dom";

import { Button, Card, EmptyState, ErrorState, Mono, PageHeader, SkeletonRows } from "@/components/ui";
import { useSearch } from "@/hooks/queries";

/**
 * The one place in the application with a free-text question field.
 * Everything else is structured navigation — this is not a chat interface.
 */
export default function PointInTime() {
  const [question, setQuestion] = useState("");
  const [asOf, setAsOf] = useState("2023-06-30");
  const search = useSearch();

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (question.trim()) {
      search.mutate({ query: question.trim(), as_of: asOf, mode: "hybrid_rerank" });
    }
  };

  const result = search.data;

  return (
    <div className="px-8 py-6">
      <PageHeader
        title="Point-in-Time Explorer"
        description="Ask what was in force on a given date. Superseded circulars are excluded."
      />

      <form onSubmit={submit} className="mb-5 flex flex-wrap items-end gap-2">
        <div className="min-w-[20rem] flex-1">
          <label className="mb-1 block text-xs text-muted-foreground" htmlFor="pit-question">
            Question
          </label>
          <input
            id="pit-question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="What were the margin reporting timelines?"
            className="w-full rounded-md border border-border bg-card px-3 py-2 text-sm outline-none focus:border-ring"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-muted-foreground" htmlFor="pit-date">
            As of
          </label>
          <input
            id="pit-date"
            type="date"
            value={asOf}
            onChange={(e) => setAsOf(e.target.value)}
            className="rounded-md border border-border bg-card px-3 py-2 text-sm outline-none focus:border-ring"
          />
        </div>
        <Button type="submit" variant="primary" disabled={search.isPending || !question.trim()}>
          {search.isPending ? "Searching…" : "Ask"}
        </Button>
      </form>

      {result && result.excluded_by_temporal_filter.length > 0 && (
        <Card className="mb-4 border-impact-modified/40 bg-impact-modified/5 p-3">
          <p className="text-sm text-impact-modified">
            {result.excluded_by_temporal_filter.length} result
            {result.excluded_by_temporal_filter.length === 1 ? "" : "s"} that would
            otherwise have ranked here were excluded: the circular was superseded on or
            before {asOf}.
          </p>
        </Card>
      )}

      {search.isPending && <SkeletonRows rows={5} />}
      {search.isError && (
        <ErrorState what="the answer" error={search.error} onRetry={() => search.reset()} />
      )}

      {result?.below_threshold && (
        <Card className="border-impact-modified/40 bg-impact-modified/5 p-4">
          <p className="text-sm font-medium text-impact-modified">
            Nothing in force on {asOf} answers this question confidently.
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            RegDelta refuses rather than answering from weak evidence.
          </p>
        </Card>
      )}

      {result && !result.below_threshold && result.hits.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">
            In force on <Mono>{asOf}</Mono> · {result.hits.length} passages
          </p>
          {result.hits.map((hit) => (
            <Card key={hit.chunk_id} className="p-3">
              <div className="mb-1 flex items-center justify-between gap-2">
                <Link to={`/circulars/${hit.circular_id}`} className="hover:underline">
                  <Mono>{hit.circular_number}</Mono>
                </Link>
                <span className="text-[11px] text-muted-foreground">
                  issued {hit.issue_date ?? "—"}
                </span>
              </div>
              <p className="line-clamp-4 text-[13px] leading-relaxed">{hit.text}</p>
            </Card>
          ))}
        </div>
      )}

      {!result && !search.isPending && !search.isError && (
        <EmptyState
          title="Ask a point-in-time question"
          hint="The as-of date filters out circulars superseded by then, using the supersession edges mined from the corpus."
        />
      )}
    </div>
  );
}
