import { useLayoutEffect, useState, type RefObject } from "react";

import { toRuns, type Block } from "@/lib/prose";
import { cn } from "@/lib/utils";

/** How a span id is drawn. ``quote`` and ``obligation`` are the evidence marks. */
export const MARK_CLASS: Record<string, string> = {
  quote: "quote",
  obligation: "obligation",
  term: "bg-highlight",
};

/** Source text as reading blocks, with evidence marks kept at their offsets. */
export function Prose({ blocks, className }: { blocks: Block[]; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {blocks.map((block, index) => {
        const content = toRuns(block.parts).map((run, i) => {
          const body = run.code ? (
            <span className="font-sans text-[0.92em] font-semibold">{run.text}</span>
          ) : run.bold ? (
            <strong>{run.text}</strong>
          ) : (
            run.text
          );
          if (!run.spanId) return <span key={i}>{body}</span>;
          const Tag = run.spanId === "obligation" ? "span" : "mark";
          return (
            <Tag key={i} data-mark={run.spanId} className={MARK_CLASS[run.spanId] ?? "bg-highlight"}>
              {body}
            </Tag>
          );
        });
        if (block.kind === "heading") {
          return (
            <p key={index} className="font-bold">
              {content}
            </p>
          );
        }
        if (block.kind === "item") {
          return (
            <p key={index} className="relative pl-5">
              <span aria-hidden className="absolute left-1 text-ink-soft">
                –
              </span>
              {content}
            </p>
          );
        }
        return <p key={index}>{content}</p>;
      })}
    </div>
  );
}

/**
 * Vertical offset of the first evidence mark inside ``container``, for the
 * shoulder arrow. Re-measured when the selection changes and when the leaf
 * reflows (width change, zoom, fonts arriving).
 */
export function useMarkTop(container: RefObject<HTMLElement>, key: unknown): number | null {
  const [top, setTop] = useState<number | null>(null);
  useLayoutEffect(() => {
    const root = container.current;
    if (!root) return;
    const measure = () => {
      const mark = root.querySelector<HTMLElement>("[data-mark=quote], [data-mark=obligation]");
      if (!mark) {
        setTop(null);
        return;
      }
      const markBox = mark.getBoundingClientRect();
      const rootBox = root.getBoundingClientRect();
      setTop(Math.round(markBox.top - rootBox.top + markBox.height / 2));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(root);
    void document.fonts?.ready.then(measure);
    return () => observer.disconnect();
  }, [container, key]);
  return top;
}
