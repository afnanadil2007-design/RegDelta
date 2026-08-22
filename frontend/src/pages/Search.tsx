import { useState } from "react";
import { Link } from "react-router-dom";

import { Button, Card, EmptyState, ErrorState, Mono, PageHeader, SkeletonRows } from "@/components/ui";
import { useSearch } from "@/hooks/queries";
import type { RetrievalMode, SearchHit } from "@/types/api";

const MODES: { value: RetrievalMode; label: string; hint: string }[] = [
  { value: "hybrid_rerank", label: "Hybrid + rerank", hint: "production pipeline" },
  { value: "hybrid", label: "Hybrid (RRF)", hint: "fusion, no cross-encoder" },
  { value: "dense", label: "Dense", hint: "pgvector cosine only" },
  { value: "lexical", label: "Lexical", hint: "Postgres tsvector only" },
];

export default function Search() {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<RetrievalMode>("hybrid_rerank");
  const search = useSearch();

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) search.mutate({ query: query.trim(), mode });
  };

  const result = search.data;

  return (
    <div className="px-8 py-6">
      <PageHeader
        title="Search"
        description="The same retrieval pipeline the agent and the evaluation harness use."
      />

      <form onSubmit={submit} className="mb-5 flex flex-wrap items-center gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. upfront margin collection reporting timeline"
          className="min-w-[18rem] flex-1 rounded-md border border-border bg-card px-3 py-2 text-sm outline-none focus:border-ring"
        />
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value as RetrievalMode)}
          className="rounded-md border border-border bg-card px-2 py-2 text-sm"
        >
          {MODES.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label} — {m.hint}
            </option>
          ))}
        </select>
        <Button type="submit" variant="primary" disabled={search.isPending || !query.trim()}>
          {search.isPending ? "Searching…" : "Search"}
        </Button>
      </form>

      {search.isPending && <SkeletonRows rows={5} />}

      {search.isError && (
        <ErrorState what="search results" error={search.error} onRetry={() => search.reset()} />
      )}

      {result && result.below_threshold && (
        <Card className="border-impact-modified/40 bg-impact-modified/5 p-4">
          <p className="text-sm font-medium text-impact-modified">
            No result cleared the relevance threshold.
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            The pipeline returns an explicit refusal rather than a weak best guess.
            Top score was {result.top_score?.toFixed(3) ?? "—"}.
          </p>
        </Card>
      )}

      {result && !result.below_threshold && result.hits.length === 0 && (
        <EmptyState title="No matches" hint="Try broader wording or a different mode." />
      )}

      {result && result.hits.length > 0 && (
        <>
          <p className="mb-2 text-xs text-muted-foreground">
            {result.hits.length} results · mode <Mono>{result.mode}</Mono>
            {result.excluded_by_temporal_filter.length > 0 && (
              <span className="ml-2 text-impact-modified">
                {result.excluded_by_temporal_filter.length} excluded by the point-in-time
                filter
              </span>
            )}
          </p>
          <div className="space-y-2">
            {result.hits.map((hit) => (
              <HitCard key={hit.chunk_id} hit={hit} />
            ))}
          </div>
        </>
      )}

      {!result && !search.isPending && !search.isError && (
        <EmptyState
          title="Search the corpus"
          hint="Switch modes to see how dense, lexical, and fused retrieval differ on the same query."
        />
      )}
    </div>
  );
}

function HitCard({ hit }: { hit: SearchHit }) {
  return (
    <Card className="p-3">
      <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
        <Link to={`/circulars/${hit.circular_id}`} className="hover:underline">
          <Mono>{hit.circular_number}</Mono>
        </Link>
        <div className="flex items-center gap-2 font-mono text-[11px] text-muted-foreground">
          {hit.dense_rank !== null && <Contribution label="dense" rank={hit.dense_rank} />}
          {hit.lexical_rank !== null && (
            <Contribution label="lexical" rank={hit.lexical_rank} />
          )}
          <span title="final score">{hit.score.toFixed(3)}</span>
        </div>
      </div>
      <p className="line-clamp-3 text-[13px] leading-relaxed">{hit.text}</p>
      <div className="mt-1.5 text-[11px] text-muted-foreground">
        {hit.circular_title} · {hit.issue_date ?? "—"}
      </div>
    </Card>
  );
}

/** Shows which retriever contributed this hit, and at what rank. */
function Contribution({ label, rank }: { label: string; rank: number }) {
  return (
    <span
      className="rounded bg-muted px-1.5 py-0.5"
      title={`${label} retriever ranked this #${rank}`}
    >
      {label} #{rank}
    </span>
  );
}
