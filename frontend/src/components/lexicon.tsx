/**
 * The lexicon world's own parts (DESIGN.md): leaves with a guide head and a
 * shoulder, bordered plates where colour lives, and the three evidence states
 * (quote status, machine interpretation, analyst decision) as words + icons.
 */
import { CircleCheck, CircleDashed, CircleX, FileWarning, FlaskConical, SearchX } from "lucide-react";
import type { ReactNode } from "react";

import { formatDateTime } from "@/lib/format";
import { DECISION, IMPACT, QUOTE_STATUS } from "@/lib/labels";
import { cn } from "@/lib/utils";
import type { AnalystDecision, ImpactType, QuoteStatus } from "@/types/api";

/** One rule line: first item in view, the leaf's title, last item in view. */
export function GuideHead({
  first,
  title,
  last,
  as: Heading = "h2",
  id,
}: {
  first?: ReactNode;
  title: ReactNode;
  last?: ReactNode;
  as?: "h2" | "h3";
  id?: string;
}) {
  return (
    <div className="flex items-baseline gap-4 border-b-[1.5px] border-ink pb-1.5">
      {first ? <span className="guide-words shrink-0 text-ink-soft">{first}</span> : null}
      <Heading id={id} className="min-w-0 flex-1 truncate text-center font-serif text-md font-bold">
        {title}
      </Heading>
      {last ? <span className="guide-words shrink-0 text-ink-soft">{last}</span> : null}
    </div>
  );
}

/** A paper leaf. With ``shoulder``, a narrow index column runs down its outside. */
export function Leaf({
  head,
  children,
  className,
  labelledBy,
}: {
  head?: ReactNode;
  children: ReactNode;
  className?: string;
  labelledBy?: string;
}) {
  return (
    <section
      aria-labelledby={labelledBy}
      className={cn("flex min-w-0 flex-col gap-4 bg-paper px-5 py-4 sm:px-6", className)}
    >
      {head}
      {children}
    </section>
  );
}

/**
 * A circular number such as SEBI/HO/MIRSD/P/CIR/2024/306: it may break only
 * after a slash, never inside a segment.
 */
export function Ident({ value }: { value: string | null | undefined }) {
  if (!value) return null;
  const parts = value.split("/");
  return (
    <>
      {parts.map((part, index) => (
        <span key={index}>
          {part}
          {index < parts.length - 1 ? (
            <>
              /<wbr />
            </>
          ) : null}
        </span>
      ))}
    </>
  );
}

/** The shoulder's pointer: a solid arrow aimed at the line it indexes. */
export function ShoulderArrow({ className }: { className?: string }) {
  return (
    <svg aria-hidden viewBox="0 0 10 12" className={cn("h-3 w-2.5 fill-ink", className)}>
      <path d="M0 0 10 6 0 12Z" />
    </svg>
  );
}

/**
 * A plate: the only place colour appears. Printed plates carry a double rule,
 * an outer line and a hairline just inside it. ``neutral`` frames a chart or
 * a legend.
 */
export function Plate({
  tone,
  children,
  className,
}: {
  tone: string;
  children: ReactNode;
  className?: string;
}) {
  const [line, ground] =
    tone === "neutral"
      ? ["var(--ink-faint)", "var(--paper-raised)"]
      : [`var(--${tone})`, `var(--${tone}-tint)`];
  return (
    <div
      className={cn("border-[1.5px] px-4 py-3", className)}
      style={{
        borderColor: line,
        background: ground,
        boxShadow: `inset 0 0 0 3px ${ground}, inset 0 0 0 4px ${line}`,
      }}
    >
      {children}
    </div>
  );
}

/** The impact type as a small plate: always the word, never colour alone. */
export function ImpactTag({ impact, size = "sm" }: { impact: ImpactType; size?: "sm" | "md" }) {
  const meta = IMPACT[impact];
  return (
    <span
      className={cn(
        "inline-flex items-center whitespace-nowrap border font-semibold",
        size === "sm" ? "px-1.5 py-px text-xs" : "px-2 py-0.5 text-sm",
      )}
      style={{
        borderColor: `var(--${meta.tone})`,
        color: `var(--${meta.tone})`,
        background: `var(--${meta.tone}-tint)`,
      }}
    >
      {size === "sm" ? meta.short : meta.label}
    </span>
  );
}

const QUOTE_ICON: Record<QuoteStatus, ReactNode> = {
  VERIFIED: <CircleCheck aria-hidden className="size-4 text-impact-covered" />,
  FAILED: <FileWarning aria-hidden className="size-4 text-error" />,
  NOT_APPLICABLE: <SearchX aria-hidden className="size-4 text-ink-soft" />,
};

export function QuoteStatusTag({ status, detailed = false }: { status: QuoteStatus; detailed?: boolean }) {
  const meta = QUOTE_STATUS[status];
  return (
    <span className="inline-flex items-start gap-1.5 text-sm text-ink">
      <span className="mt-0.5 shrink-0">{QUOTE_ICON[status]}</span>
      <span>
        <span className="font-semibold">{meta.label}</span>
        {detailed ? <span className="block text-ink-soft">{meta.detail}</span> : null}
      </span>
    </span>
  );
}

const DECISION_ICON: Record<AnalystDecision, ReactNode> = {
  PENDING: <CircleDashed aria-hidden className="size-4 text-ink-soft" />,
  ACCEPTED: <CircleCheck aria-hidden className="size-4 text-ink" />,
  REJECTED: <CircleX aria-hidden className="size-4 text-ink" />,
};

/** The analyst's mark: who decided what, and when. */
export function DecisionMark({
  decision,
  decidedAt,
  compact = false,
}: {
  decision: AnalystDecision;
  decidedAt: string | null;
  compact?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-sm",
        decision === "PENDING" ? "text-ink-soft" : "font-semibold text-ink",
      )}
    >
      {DECISION_ICON[decision]}
      <span>
        {DECISION[decision]}
        {!compact && decidedAt && decision !== "PENDING" ? (
          <span className="font-normal text-ink-soft"> · {formatDateTime(decidedAt)}</span>
        ) : null}
      </span>
    </span>
  );
}

/** Labels synthetic or fictional material wherever it appears (PRODUCT.md). */
export function SyntheticTag({ children = "Synthetic" }: { children?: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 border border-ink-soft px-1.5 py-px text-xs font-semibold text-ink-soft">
      <FlaskConical aria-hidden className="size-3.5" />
      {children}
    </span>
  );
}

/** Page title with its context underneath (never a label above it). */
export function PageHeader({
  title,
  context,
  actions,
}: {
  title: ReactNode;
  context?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end gap-x-6 gap-y-3">
      <div className="min-w-0 flex-1">
        <h1 className="font-serif text-2xl font-bold text-ink">{title}</h1>
        {context ? <div className="mt-1 text-base text-ink-soft">{context}</div> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}
