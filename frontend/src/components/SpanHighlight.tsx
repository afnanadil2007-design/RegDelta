import { cn } from "@/lib/utils";

/**
 * Render `text` with the [start, end) slice highlighted.
 *
 * Offsets are relative to `baseOffset` (a paragraph's or clause's own start),
 * which is how the backend stores every span. Out-of-range offsets render the
 * plain text rather than throwing — a bad span must not break the page.
 */
export function SpanHighlight({
  text,
  start,
  end,
  baseOffset = 0,
  tone = "amber",
}: {
  text: string;
  start: number | null;
  end: number | null;
  baseOffset?: number;
  tone?: "amber" | "blue";
}) {
  if (start === null || end === null) return <>{text}</>;

  const from = start - baseOffset;
  const to = end - baseOffset;
  if (from < 0 || to > text.length || from >= to) return <>{text}</>;

  return (
    <>
      {text.slice(0, from)}
      <mark
        className={cn(
          "rounded px-0.5",
          tone === "amber"
            ? "bg-impact-modified/25 text-foreground"
            : "bg-impact-new/20 text-foreground",
        )}
      >
        {text.slice(from, to)}
      </mark>
      {text.slice(to)}
    </>
  );
}
