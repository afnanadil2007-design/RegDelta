import { useId, useMemo, useRef } from "react";

import { DecisionTick } from "@/components/assessment/DecisionTick";
import { GuideHead, ShoulderArrow, SyntheticTag } from "@/components/lexicon";
import { Prose, useMarkTop } from "@/components/Prose";
import { EmptyState, RequestError, Skeleton } from "@/components/ui/feedback";
import { around, clauseSpan, clip } from "@/lib/evidence";
import { toBlocks } from "@/lib/prose";
import { segmentText } from "@/lib/text";
import { cn } from "@/lib/utils";
import type { Finding, PolicyClause, PolicyPack } from "@/types/api";

/**
 * The policy manual as a leaf: the clause the finding cites, with its
 * neighbours for context, clause numbers in the shoulder, and the quote marked.
 */
export function ClauseLeaf({
  finding,
  pack,
  clauses,
  loading,
  error,
  onRetry,
  children,
}: {
  finding: Finding;
  pack: PolicyPack | undefined;
  clauses: PolicyClause[] | undefined;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  children?: React.ReactNode;
}) {
  const headId = useId();
  const body = useRef<HTMLDivElement>(null);
  const span = clauseSpan(finding);

  const view = useMemo(() => {
    if (finding.policy_clause_id === null) return null;
    const cited: PolicyClause = {
      id: finding.policy_clause_id,
      clause_number: finding.clause_number ?? "",
      heading: finding.clause_heading,
      heading_path: null,
      text: finding.clause_text ?? "",
      char_start: finding.clause_char_start ?? 0,
      char_end: (finding.clause_char_start ?? 0) + Array.from(finding.clause_text ?? "").length,
    };
    const list = clauses ?? [cited];
    const index = list.findIndex((c) => c.id === finding.policy_clause_id);
    const shown = index === -1 ? { items: [cited], from: 0 } : around(list, index, 1);
    return {
      shown: shown.items,
      citedPath: list[index]?.heading_path ?? null,
      first: shown.items[0]?.clause_number,
      last: shown.items[shown.items.length - 1]?.clause_number,
    };
  }, [finding, clauses]);

  const markTop = useMarkTop(body, `${finding.id}-${view?.shown.length ?? 0}`);

  return (
    <section aria-labelledby={headId} className="flex min-w-0 flex-col gap-4 bg-paper px-4 py-4 sm:px-5">
      <GuideHead id={headId} first={view?.first} title="Policy manual" last={view?.last} />
      <div className="flex flex-col gap-1">
        <p className="font-serif text-lg font-bold">{pack ? pack.name : "Policy manual"}</p>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-soft">
          {view?.citedPath ? <span>{view.citedPath}</span> : null}
          {pack ? <span>Version {pack.version}</span> : null}
          {pack?.is_synthetic ? <SyntheticTag>Fictional manual</SyntheticTag> : null}
        </p>
      </div>

      {view === null ? (
        <EmptyState title="No clause to compare">
          No clause in the manual scored above the relevance threshold for this obligation, so no judgement
          was made. Check the manual directly if you expected a match.
        </EmptyState>
      ) : (
        <>
          {loading ? <Skeleton lines={2} label="neighbouring clauses" /> : null}
          {error ? <RequestError error={error} what="the neighbouring clauses" onRetry={onRetry} /> : null}
          <div ref={body} className="relative grid grid-cols-[2.25rem_minmax(0,1fr)] gap-x-3">
            {markTop !== null ? (
              <>
                <span
                  aria-hidden
                  className="pointer-events-none absolute left-[1.55rem] transition-[top] duration-[180ms] ease-settle"
                  style={{ top: markTop - 6 }}
                >
                  <ShoulderArrow />
                </span>
                <span
                  className="pointer-events-none absolute left-0 transition-[top] duration-[180ms] ease-settle"
                  style={{ top: markTop - 9 }}
                >
                  <DecisionTick decision={finding.analyst_decision} />
                </span>
              </>
            ) : null}
            {view.shown.map((clause) => {
              const isCited = clause.id === finding.policy_clause_id;
              const local = isCited && span ? clip(span, clause.char_start, clause.char_end) : null;
              const { segments } = segmentText(clause.text, clause.char_start, local ? [local] : []);
              return (
                <div key={clause.id} className="contents">
                  <span
                    className={cn("guide-words pt-0.5 text-right", isCited ? "text-ink" : "text-ink-soft")}
                  >
                    {clause.clause_number}
                  </span>
                  <div className={cn("doc-text pb-3", !isCited && "text-ink-soft")}>
                    <Prose blocks={toBlocks(segments)} />
                    {isCited && !span ? (
                      <p className="mt-1 font-sans text-sm text-ink-soft">
                        {finding.quote_status === "FAILED" && finding.circular_span_start !== null
                          ? "The passage quoted from this clause was not found in it; the interpretation shows what was quoted."
                          : "No passage of this clause was quoted."}
                      </p>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
      {children}
    </section>
  );
}
