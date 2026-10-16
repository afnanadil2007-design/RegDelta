import { Fragment, type ReactNode } from "react";

import { Ident } from "@/components/lexicon";
import { toRuns, type Block } from "@/lib/prose";
import { cn } from "@/lib/utils";

/** How a span id is drawn. ``quote`` and ``obligation`` are the evidence marks. */
export const MARK_CLASS: Record<string, string> = {
  quote: "quote",
  obligation: "obligation",
  term: "bg-highlight",
};

const EVIDENCE = new Set(["quote", "obligation"]);

/** A slash-joined identifier such as a circular number: three or more slashes. */
const IDENTIFIER = /(\S+(?:\/\S+){3,})/;

/**
 * Text whose identifiers may wrap after a slash, as titles do, instead of
 * mid-segment ("…/CIR/202" + "4/306") on a phone. Only break opportunities
 * are added, so the text and its offsets are unchanged.
 */
function breakable(text: string): ReactNode {
  if (!text.includes("/")) return text;
  return text.split(IDENTIFIER).map((piece, i) => (i % 2 === 1 ? <Ident key={i} value={piece} /> : piece));
}

/**
 * Source text as reading blocks, with evidence marks kept at their offsets.
 * ``pointer`` is rendered immediately before the first evidence mark, so a
 * caller can hang something on the line where the evidence starts.
 */
export function Prose({
  blocks,
  className,
  pointer,
}: {
  blocks: Block[];
  className?: string;
  pointer?: ReactNode;
}) {
  let pointed = !pointer;
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {blocks.map((block, index) => {
        const content = toRuns(block.parts).map((run, i) => {
          const text = breakable(run.text);
          const body = run.code ? (
            <span className="font-sans text-[0.92em] font-semibold">{text}</span>
          ) : run.bold ? (
            <strong>{text}</strong>
          ) : (
            text
          );
          if (!run.spanId) return <span key={i}>{body}</span>;
          const Tag = run.spanId === "obligation" ? "span" : "mark";
          const mark = (
            <Tag data-mark={run.spanId} className={MARK_CLASS[run.spanId] ?? "bg-highlight"}>
              {body}
            </Tag>
          );
          if (pointed || !EVIDENCE.has(run.spanId)) return <Fragment key={i}>{mark}</Fragment>;
          pointed = true;
          return (
            <Fragment key={i}>
              {pointer}
              {mark}
            </Fragment>
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
            <p key={index} className="pl-5">
              {/* Floated, not positioned: a positioned paragraph would capture the leaf's pointer. */}
              <span aria-hidden className="float-left -ml-4 text-ink-soft">
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
