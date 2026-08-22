import { Link } from "react-router-dom";

import { cn } from "@/lib/utils";
import type { Citation } from "@/types/api";

/**
 * A reference as printed in the circular. Resolved references link to the
 * cited circular; unresolved ones are shown too — they are evidence about
 * corpus coverage, not noise to hide.
 */
export function CitationChip({
  citation,
  onHover,
}: {
  citation: Citation;
  onHover?: (citationId: number | null) => void;
}) {
  const body = (
    <span
      onMouseEnter={() => onHover?.(citation.id)}
      onMouseLeave={() => onHover?.(null)}
      className={cn(
        "inline-flex items-center gap-1.5 rounded border px-2 py-1 font-mono text-[11px] transition-colors",
        citation.resolved
          ? "border-border bg-card hover:border-ring hover:bg-muted"
          : "border-dashed border-impact-none/40 bg-transparent text-muted-foreground",
      )}
      title={
        citation.resolved
          ? `Resolved via ${citation.resolution_method}`
          : "Not found in this corpus"
      }
    >
      {citation.raw_reference}
      {!citation.resolved && <span className="not-italic opacity-60">unresolved</span>}
    </span>
  );

  return citation.resolved && citation.cited_circular_id ? (
    <Link to={`/circulars/${citation.cited_circular_id}`}>{body}</Link>
  ) : (
    body
  );
}
