import { useState } from "react";
import { Link } from "react-router-dom";

import { Ident } from "@/components/lexicon";
import { Prose } from "@/components/Prose";
import { Button } from "@/components/ui/controls";
import { Notice } from "@/components/ui/feedback";
import { formatDate, formatDuration, plural } from "@/lib/format";
import { toBlocks, type Block } from "@/lib/prose";
import { MODE, SCORE } from "@/lib/labels";
import type { Span } from "@/lib/text";
import { segmentText } from "@/lib/text";
import type { SearchHit, SearchResponse } from "@/types/api";

/** Code-point spans of each query term in ``text``, for marking. */
function termSpans(text: string, terms: string[], start: number): Span[] {
  if (terms.length === 0) return [];
  const pattern = new RegExp(
    `(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`,
    "giu",
  );
  const spans: Span[] = [];
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0;
    // Convert the UTF-16 match position to code points.
    const before = Array.from(text.slice(0, index)).length;
    spans.push({ id: "term", start: start + before, end: start + before + Array.from(match[0]).length });
  }
  return spans;
}

const EXCERPT = 3;

/** The paragraphs with the most query terms, in reading order. */
function excerpt(blocks: Block[]): Block[] {
  const scored = blocks.map((block, index) => ({
    index,
    hits: block.parts.filter((part) => part.spanId === "term").length,
  }));
  const best = scored
    .filter((b) => b.hits > 0)
    .sort((a, b) => b.hits - a.hits || a.index - b.index)
    .slice(0, EXCERPT)
    .map((b) => b.index)
    .sort((a, b) => a - b);
  return (best.length ? best : [0, 1, 2]).map((i) => blocks[i]).filter(Boolean);
}

function HitEntry({
  hit,
  rank,
  terms,
  scoreLabel,
}: {
  hit: SearchHit;
  rank: number;
  terms: string[];
  scoreLabel: string;
}) {
  const [whole, setWhole] = useState(false);
  const { segments } = segmentText(hit.text, hit.char_start, termSpans(hit.text, terms, hit.char_start));
  const blocks = toBlocks(segments);
  const long = blocks.length > EXCERPT + 1;
  const ranks = [
    hit.dense_rank !== null ? `dense #${hit.dense_rank}` : null,
    hit.lexical_rank !== null ? `lexical #${hit.lexical_rank}` : null,
  ].filter(Boolean);
  return (
    <li className="grid grid-cols-[2.25rem_minmax(0,1fr)] gap-x-3 border-b border-rule py-4 first:pt-1 last:border-0">
      <span className="guide-words pt-1 text-right text-ink-soft">{rank}</span>
      <article className="flex min-w-0 flex-col gap-2">
        <header className="flex flex-col gap-0.5">
          <Link to={`/circulars/${hit.circular_id}`} className="font-semibold text-ink break-words">
            <Ident value={hit.circular_number} />
          </Link>
          <p className="text-sm text-ink-soft">
            {hit.circular_title} · {formatDate(hit.issue_date)}
            {hit.heading_path ? ` · ${hit.heading_path}` : ""}
          </p>
        </header>
        <Prose blocks={long && !whole ? excerpt(blocks) : blocks} className="doc-text" />
        {long ? (
          <div>
            <Button
              variant="quiet"
              className="-ml-3"
              aria-expanded={whole}
              onClick={() => setWhole((w) => !w)}
            >
              {whole
                ? "Show the matching paragraphs only"
                : `Show the whole passage (${blocks.length} paragraphs)`}
            </Button>
          </div>
        ) : null}
        <p className="text-xs text-ink-soft">
          {scoreLabel} {hit.score.toFixed(3)}
          {ranks.length ? ` · ${ranks.join(", ")}` : ""}
        </p>
      </article>
    </li>
  );
}

/** Results, a refusal, or an honest zero, with what the temporal filter removed. */
export function SearchResults({
  result,
  terms,
  asOf,
}: {
  result: SearchResponse;
  terms: string[];
  asOf?: string | null;
}) {
  const excluded = result.excluded_by_temporal_filter;
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-ink-soft" aria-live="polite">
        {result.refused ? "Refused" : `${plural(result.hits.length, "passage")}`} · {MODE[result.mode].label}{" "}
        · answered in {formatDuration(result.elapsed_ms)} on the server
      </p>
      {excluded.length > 0 ? (
        <Notice
          tone="info"
          title={`${plural(excluded.length, "circular")} left out: not in force on ${formatDate(asOf ?? null)}`}
        >
          <ul className="mt-1 flex flex-col gap-0.5">
            {excluded.map((circular) => (
              <li key={circular.circular_id}>
                <Link
                  to={`/circulars/${circular.circular_id}`}
                  className="font-semibold text-ink break-words"
                >
                  <Ident value={circular.circular_number} />
                </Link>{" "}
                {circular.title}
              </li>
            ))}
          </ul>
        </Notice>
      ) : null}
      {result.refused ? (
        <Notice tone="warning" title="No passage was relevant enough to show">
          The best cross-encoder score was {result.top_score?.toFixed(3) ?? "unknown"}, below the refusal
          threshold of {result.threshold?.toFixed(2) ?? "unknown"}. RegDelta declines rather than offer weak
          passages. Rephrase with the circular's own terms, or switch to Hybrid to see the closest passages
          anyway.
        </Notice>
      ) : result.hits.length === 0 ? (
        <Notice tone="info" title="Nothing matched">
          No passage in the corpus matched{asOf ? " among circulars in force on that date" : ""}. Try fewer or
          different words.
        </Notice>
      ) : (
        <ol className="flex flex-col">
          {result.hits.map((hit, index) => (
            <HitEntry
              key={hit.chunk_id}
              hit={hit}
              rank={index + 1}
              terms={terms}
              scoreLabel={SCORE[result.score_kind]}
            />
          ))}
        </ol>
      )}
    </div>
  );
}
