import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/controls";
import { formatInteger } from "@/lib/format";

/** "41–60 of 300" with previous and next; the page lives in the caller's URL. */
export function Pager({
  offset,
  limit,
  total,
  onChange,
  noun,
}: {
  offset: number;
  limit: number;
  total: number;
  onChange: (offset: number) => void;
  noun: string;
}) {
  if (total <= limit && offset === 0) return null;
  const last = Math.min(offset + limit, total);
  return (
    <nav aria-label={`${noun} pages`} className="flex flex-wrap items-center gap-3">
      <p className="text-sm text-ink-soft" aria-live="polite">
        {total === 0
          ? "None"
          : `${formatInteger(offset + 1)}–${formatInteger(last)} of ${formatInteger(total)} ${noun}`}
      </p>
      <div className="ml-auto flex gap-2">
        <Button
          disabled={offset === 0}
          onClick={() => onChange(Math.max(0, offset - limit))}
          icon={<ChevronLeft aria-hidden className="size-4" />}
        >
          Previous
        </Button>
        <Button disabled={last >= total} onClick={() => onChange(offset + limit)}>
          Next
          <ChevronRight aria-hidden className="size-4" />
        </Button>
      </div>
    </nav>
  );
}
