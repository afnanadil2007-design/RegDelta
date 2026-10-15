import { useId, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { MarkPointer } from "@/components/assessment/MarkPointer";
import { GuideHead, Ident, SyntheticTag } from "@/components/lexicon";
import { Prose } from "@/components/Prose";
import { Button } from "@/components/ui/controls";
import { Notice, RequestError, Skeleton } from "@/components/ui/feedback";
import {
  around,
  circularSpan,
  clip,
  isSectionHeading,
  locate,
  numberPrefix,
  paragraphLabel,
} from "@/lib/evidence";
import { formatDate } from "@/lib/format";
import { toBlocks } from "@/lib/prose";
import { segmentText } from "@/lib/text";
import type { CircularDetail, Finding } from "@/types/api";

/**
 * The circular as a lexicon leaf: the paragraphs around the obligation, the
 * paragraph numbers in the shoulder, and an arrow at the quoted line.
 */
export function CircularLeaf({
  finding,
  detail,
  loading,
  error,
  onRetry,
  children,
}: {
  finding: Finding;
  detail: CircularDetail | undefined;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  children?: React.ReactNode;
}) {
  const headId = useId();
  const [whole, setWhole] = useState(false);
  const span = useMemo(() => circularSpan(finding), [finding]);

  const view = useMemo(() => {
    if (!detail) return null;
    const paragraphs = [...detail.paragraphs].sort((a, b) => a.order_index - b.order_index);
    const index = locate(paragraphs, span);
    const shown = whole || index === -1 ? { items: paragraphs, from: 0 } : around(paragraphs, index, 1);
    const labels = shown.items.map(paragraphLabel).filter(Boolean) as string[];
    return {
      found: index !== -1,
      total: paragraphs.length,
      shown: shown.items,
      first: labels[0],
      last: labels[labels.length - 1],
    };
  }, [detail, span, whole]);
  // The arrow and tick hang on the line where the quoted text starts.
  const firstMarked = view?.shown.find(
    (paragraph) => !isSectionHeading(paragraph) && clip(span, paragraph.char_start, paragraph.char_end),
  )?.id;

  return (
    <section aria-labelledby={headId} className="flex min-w-0 flex-col gap-3 bg-paper px-4 py-4 sm:px-5">
      <GuideHead id={headId} first={view?.first} title="Circular" last={view?.last} />
      {detail ? (
        <div className="flex flex-col gap-1">
          <p className="font-serif text-lg font-bold break-words">
            <Link
              to={`/circulars/${detail.circular.id}`}
              className="text-ink underline decoration-rule hover:decoration-ink"
            >
              <Ident value={detail.circular.circular_number} />
            </Link>
          </p>
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-soft">
            <span>{detail.circular.title}</span>
            <span>{formatDate(detail.circular.issue_date)}</span>
            {detail.circular.is_synthetic ? <SyntheticTag>Synthetic circular</SyntheticTag> : null}
          </p>
        </div>
      ) : null}

      {loading ? <Skeleton lines={6} label="the circular" /> : null}
      {error ? <RequestError error={error} what="the circular" onRetry={onRetry} /> : null}

      {view && !view.found ? (
        <Notice tone="warning" title="The quoted text is not inside any extracted paragraph">
          The stored offsets ({span.start}–{span.end}) fall outside the paragraph map, so the whole circular
          is shown without a mark. The obligation reads: “{finding.obligation_text}”
        </Notice>
      ) : null}

      {view ? (
        <div className="relative grid grid-cols-[2.25rem_minmax(0,1fr)] gap-x-5">
          {view.shown.map((paragraph) => {
            const local = clip(span, paragraph.char_start, paragraph.char_end);
            const first = local !== null && paragraph.id === firstMarked;
            const { segments } = segmentText(paragraph.text, paragraph.char_start, local ? [local] : []);
            const heading = isSectionHeading(paragraph);
            return (
              <div key={paragraph.id} className="contents">
                <span className="guide-words pt-0.5 text-right text-ink-soft">
                  {paragraphLabel(paragraph)}
                </span>
                <div className={heading ? "section-caps pb-1 pt-2 text-ink" : "doc-text pb-3"}>
                  {heading ? (
                    paragraph.text
                  ) : (
                    <Prose
                      blocks={toBlocks(segments, {
                        stripPrefix: numberPrefix(paragraph),
                        keepLines: !paragraph.para_number && !paragraph.heading_path,
                      })}
                      pointer={first ? <MarkPointer decision={finding.analyst_decision} /> : undefined}
                    />
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : null}

      {view && view.found && view.total > 3 ? (
        <div className="-my-2">
          <Button variant="quiet" className="-ml-3" onClick={() => setWhole((w) => !w)}>
            {whole
              ? "Show only the surrounding paragraphs"
              : `Show the whole circular (${view.total} paragraphs)`}
          </Button>
        </div>
      ) : null}
      {children}
    </section>
  );
}
