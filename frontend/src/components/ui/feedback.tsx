import { AlertTriangle, CircleSlash, Info, PlugZap } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { ApiRequestError, errorMessage } from "@/api/client";
import { Button } from "@/components/ui/controls";
import { cn } from "@/lib/utils";

type Tone = "info" | "warning" | "error" | "unavailable";

const TONE: Record<Tone, { box: string; icon: ReactNode }> = {
  info: {
    box: "border-impact-new bg-impact-new-tint",
    icon: <Info aria-hidden className="size-4 text-impact-new" />,
  },
  warning: {
    box: "border-impact-modified bg-impact-modified-tint",
    icon: <AlertTriangle aria-hidden className="size-4 text-impact-modified" />,
  },
  error: {
    box: "border-error bg-error-tint",
    icon: <AlertTriangle aria-hidden className="size-4 text-error" />,
  },
  unavailable: {
    box: "border-ink-soft bg-paper",
    icon: <PlugZap aria-hidden className="size-4 text-ink-soft" />,
  },
};

/** An inline message with its cause and, where one exists, the way out. */
export function Notice({
  tone,
  title,
  children,
  action,
  className,
}: {
  tone: Tone;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn("flex gap-3 border px-4 py-3", TONE[tone].box, className)}
    >
      <span className="mt-0.5 shrink-0">{TONE[tone].icon}</span>
      <div className="min-w-0 flex-1">
        <p className="font-semibold text-ink">{title}</p>
        {children ? <div className="mt-0.5 text-sm text-ink">{children}</div> : null}
      </div>
      {action ? <div className="shrink-0 self-center">{action}</div> : null}
    </div>
  );
}

/** A failed request, explained, with a retry that keeps whatever was typed. */
export function RequestError({
  error,
  what,
  onRetry,
}: {
  error: unknown;
  what: string;
  onRetry?: () => void;
}) {
  const unreachable = error instanceof ApiRequestError && error.code === "network_error";
  return (
    <Notice
      tone={unreachable ? "unavailable" : "error"}
      title={unreachable ? "The API is not reachable" : `Could not load ${what}`}
      action={onRetry ? <Button onClick={onRetry}>Try again</Button> : undefined}
    >
      {errorMessage(error)}
    </Notice>
  );
}

/**
 * Placeholder lines for content that is loading. Appears only after a short
 * delay so a fast response does not flash a skeleton.
 */
export function Skeleton({
  lines = 3,
  label,
  delay = 300,
}: {
  lines?: number;
  label: string;
  delay?: number;
}) {
  const [visible, setVisible] = useState(delay === 0);
  useEffect(() => {
    if (delay === 0) return;
    const timer = window.setTimeout(() => setVisible(true), delay);
    return () => window.clearTimeout(timer);
  }, [delay]);
  return (
    <div role="status" aria-live="polite" className="flex flex-col gap-2 py-2">
      <span className="sr-only">Loading {label}</span>
      {visible
        ? Array.from({ length: lines }, (_, i) => (
            <span
              key={i}
              aria-hidden
              className="block h-3 rounded-[2px] bg-rule/70"
              style={{ width: `${92 - ((i * 17) % 35)}%` }}
            />
          ))
        : null}
    </div>
  );
}

/** An empty view that says why it is empty and what to do next. */
export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-start gap-2 px-1 py-6">
      <p className="flex items-center gap-2 font-serif text-lg font-bold text-ink">
        <CircleSlash aria-hidden className="size-4 text-ink-soft" />
        {title}
      </p>
      {children ? <div className="max-w-measure text-base text-ink-soft">{children}</div> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
