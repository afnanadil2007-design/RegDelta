import { ChevronLeft, ChevronRight, CircleCheck, CircleX, FileWarning, SearchX } from "lucide-react";
import { useEffect, useId, useRef, type KeyboardEvent } from "react";

import { GuideHead, ImpactTag, Plate, ShoulderArrow } from "@/components/lexicon";
import { IconButton, Select } from "@/components/ui/controls";
import type { FindingGroup } from "@/lib/evidence";
import { IMPACT, IMPACT_ORDER } from "@/lib/labels";
import { cn } from "@/lib/utils";
import type { AnalystDecision, Finding, FindingCounts, ImpactType, QuoteStatus } from "@/types/api";

const QUOTE_SHORT: Record<QuoteStatus, { word: string; icon: React.ReactNode }> = {
  VERIFIED: { word: "Quotes located", icon: null },
  FAILED: { word: "Quote not located", icon: <FileWarning aria-hidden className="size-3.5 text-error" /> },
  NOT_APPLICABLE: { word: "No clause", icon: <SearchX aria-hidden className="size-3.5 text-ink-soft" /> },
};

function DecisionGlyph({ decision }: { decision: AnalystDecision }) {
  if (decision === "ACCEPTED")
    return <CircleCheck aria-hidden className="size-4 text-ink" strokeWidth={2.25} />;
  if (decision === "REJECTED") return <CircleX aria-hidden className="size-4 text-ink" strokeWidth={2.25} />;
  return null;
}

/** The impact legend, a titled plate whose counts double as filters. */
export function ImpactLegend({
  counts,
  active,
  onToggle,
}: {
  counts: FindingCounts;
  active: ImpactType | null;
  onToggle: (impact: ImpactType | null) => void;
}) {
  return (
    <Plate tone="neutral" className="flex flex-col gap-2">
      <p id="impact-legend" className="guide-words text-ink-soft">
        Impact
      </p>
      <div role="group" aria-labelledby="impact-legend" className="flex flex-wrap gap-1.5">
        {IMPACT_ORDER.map((impact) => {
          const pressed = active === impact;
          const count = counts.by_impact[impact] ?? 0;
          const empty = count === 0 && !pressed;
          return (
            <button
              key={impact}
              type="button"
              aria-pressed={pressed}
              aria-disabled={empty || undefined}
              title={IMPACT[impact].meaning}
              onClick={() => !empty && onToggle(pressed ? null : impact)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-control border px-1.5 py-1 text-sm transition-colors duration-150",
                empty ? "cursor-default border-transparent" : "hover:border-ink-faint hover:bg-paper",
                pressed ? "border-ink bg-paper" : "border-transparent",
              )}
            >
              <ImpactTag impact={impact} />
              <span className="font-semibold text-ink">{count}</span>
            </button>
          );
        })}
      </div>
      {active ? (
        <p className="text-xs text-ink-soft">
          Showing {IMPACT[active].label.toLowerCase()} only.{" "}
          <button type="button" className="font-semibold text-ink underline" onClick={() => onToggle(null)}>
            Show all
          </button>
        </p>
      ) : null}
    </Plate>
  );
}

function entryLabel(finding: Finding): string {
  return finding.clause_number
    ? `${finding.clause_number} ${finding.clause_heading ?? ""}`.trim()
    : "No clause";
}

/**
 * The findings index: obligations as headwords, one entry per clause judged
 * against each. A listbox: arrow keys move the selection, Home and End jump.
 */
export function FindingsIndex({
  groups,
  order,
  selectedId,
  onSelect,
  className,
}: {
  groups: FindingGroup[];
  order: Finding[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  className?: string;
}) {
  const listId = useId();
  const list = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (selectedId === null) return;
    list.current
      ?.querySelector<HTMLElement>(`[data-finding="${selectedId}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [selectedId]);

  // The selection reaches this component through the URL, which updates a
  // render later; key repeat must chain from the last key, not the last render.
  const latest = useRef(selectedId);
  latest.current = selectedId;

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (order.length === 0) return;
    const index = order.findIndex((f) => f.id === latest.current);
    let next: number | null = null;
    if (event.key === "ArrowDown") next = Math.min(order.length - 1, index + 1);
    else if (event.key === "ArrowUp") next = Math.max(0, index - 1);
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = order.length - 1;
    if (next === null) return;
    event.preventDefault();
    latest.current = order[next].id;
    onSelect(order[next].id);
  };

  const firstLabel = groups[0]?.label;
  const lastLabel = groups[groups.length - 1]?.label;
  return (
    <div className={cn("flex min-h-0 flex-col gap-3 bg-paper px-4 py-4", className)}>
      <GuideHead first={firstLabel} title="Findings" last={lastLabel} id={`${listId}-head`} />
      {order.length === 0 ? (
        <p className="text-sm text-ink-soft">No findings match this filter.</p>
      ) : (
        <div
          ref={list}
          role="listbox"
          tabIndex={0}
          aria-labelledby={`${listId}-head`}
          aria-activedescendant={selectedId !== null ? `${listId}-${selectedId}` : undefined}
          onKeyDown={onKeyDown}
          className="-mx-2 flex flex-col gap-3 rounded-control px-2 py-1"
        >
          {groups.map((group) => (
            <div key={group.obligationId} role="group" aria-labelledby={`${listId}-g${group.obligationId}`}>
              <div
                id={`${listId}-g${group.obligationId}`}
                className="grid grid-cols-[2.25rem_minmax(0,1fr)] gap-x-2 pb-1"
              >
                <span className="guide-words pt-px text-right text-ink-soft">{group.label}</span>
                <span className="line-clamp-2 font-serif text-base text-ink">{group.obligationText}</span>
              </div>
              {group.findings.map((finding) => {
                const selected = finding.id === selectedId;
                const quote = QUOTE_SHORT[finding.quote_status];
                return (
                  <div
                    key={finding.id}
                    id={`${listId}-${finding.id}`}
                    data-finding={finding.id}
                    role="option"
                    aria-selected={selected}
                    onClick={() => onSelect(finding.id)}
                    className={cn(
                      "grid cursor-pointer grid-cols-[2.25rem_minmax(0,1fr)] gap-x-2 py-1.5 transition-colors duration-150",
                      selected ? "bg-raised" : "hover:bg-raised/70",
                    )}
                  >
                    <span className="flex items-center justify-end gap-1 pr-0.5">
                      <DecisionGlyph decision={finding.analyst_decision} />
                      {selected ? <ShoulderArrow /> : null}
                    </span>
                    <span className="flex min-w-0 flex-col gap-1 pr-2">
                      <span
                        className={cn(
                          "line-clamp-2 font-serif text-md font-bold text-ink",
                          selected && "underline decoration-ink decoration-[1.5px] underline-offset-4",
                        )}
                      >
                        {entryLabel(finding)}
                      </span>
                      <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-soft">
                        <ImpactTag impact={finding.impact_type} />
                        <span className="inline-flex items-center gap-1">
                          {quote.icon}
                          {quote.word}
                        </span>
                        {finding.analyst_decision !== "PENDING" ? (
                          <span className="font-semibold text-ink">
                            {finding.analyst_decision === "ACCEPTED" ? "Accepted" : "Rejected"}
                          </span>
                        ) : null}
                      </span>
                    </span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Below 1024px the index becomes a selector with previous and next. */
export function FindingNavigator({
  groups,
  order,
  selectedId,
  onSelect,
  className,
}: {
  groups: FindingGroup[];
  order: Finding[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  className?: string;
}) {
  const selectId = useId();
  const index = order.findIndex((f) => f.id === selectedId);
  return (
    <div className={cn("flex items-end gap-2 bg-paper px-4 py-3", className)}>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <label htmlFor={selectId} className="text-sm font-semibold text-ink">
          Finding {index === -1 ? "–" : index + 1} of {order.length}
        </label>
        <Select id={selectId} value={selectedId ?? ""} onChange={(e) => onSelect(Number(e.target.value))}>
          {groups.map((group) => (
            <optgroup key={group.obligationId} label={`${group.label} ${group.obligationText.slice(0, 60)}`}>
              {group.findings
                .filter((f) => order.includes(f))
                .map((finding) => (
                  <option key={finding.id} value={finding.id}>
                    {entryLabel(finding)} — {IMPACT[finding.impact_type].label}
                    {finding.analyst_decision !== "PENDING"
                      ? ` (${finding.analyst_decision.toLowerCase()})`
                      : ""}
                  </option>
                ))}
            </optgroup>
          ))}
        </Select>
      </div>
      <IconButton
        label="Previous finding"
        icon={<ChevronLeft aria-hidden className="size-5" />}
        disabled={index <= 0}
        onClick={() => onSelect(order[index - 1].id)}
        className="border border-ink-faint bg-raised"
      />
      <IconButton
        label="Next finding"
        icon={<ChevronRight aria-hidden className="size-5" />}
        disabled={index === -1 || index >= order.length - 1}
        onClick={() => onSelect(order[index + 1].id)}
        className="border border-ink-faint bg-raised"
      />
    </div>
  );
}
