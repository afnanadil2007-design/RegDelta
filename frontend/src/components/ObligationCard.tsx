import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { SpanHighlight } from "@/components/SpanHighlight";
import { Mono } from "@/components/ui";
import { cn } from "@/lib/utils";
import type { Obligation, Paragraph } from "@/types/api";

/**
 * One extracted obligation, with its source span highlighted inside the
 * paragraph it came from. Extracted text is shown as source, not as AI prose.
 */
export function ObligationCard({
  obligation,
  paragraph,
  selected,
  onSelect,
}: {
  obligation: Obligation;
  paragraph?: Paragraph;
  selected?: boolean;
  onSelect?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "w-full rounded-lg border p-3 text-left transition-colors",
        selected
          ? "border-ring bg-accent/50"
          : "border-border bg-card hover:border-ring/50 hover:bg-muted/40",
      )}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {obligation.modality && (
            <Mono className="rounded bg-muted px-1.5 py-0.5 uppercase">
              {obligation.modality}
            </Mono>
          )}
          {obligation.actor && (
            <span className="text-xs font-medium">{obligation.actor}</span>
          )}
        </div>
        {obligation.confidence !== null && (
          <ConfidenceBadge value={obligation.confidence} />
        )}
      </div>

      <p className="text-sm leading-relaxed">
        {paragraph ? (
          <SpanHighlight
            text={paragraph.text}
            start={obligation.char_start}
            end={obligation.char_end}
            baseOffset={paragraph.char_start}
          />
        ) : (
          obligation.text
        )}
      </p>

      <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
        <Mono>
          {obligation.char_start}–{obligation.char_end}
        </Mono>
        {obligation.deadline && <span>deadline: {obligation.deadline}</span>}
        {paragraph?.para_number && <span>para {paragraph.para_number}</span>}
      </div>
    </button>
  );
}
