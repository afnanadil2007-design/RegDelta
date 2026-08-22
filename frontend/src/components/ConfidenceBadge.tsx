import { cn } from "@/lib/utils";

/**
 * Confidence never appears as a bare float: the band is the primary signal
 * and the number is available on hover.
 */
export function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const band =
    value >= 0.8
      ? { label: "High", tone: "bg-impact-covered/10 text-impact-covered" }
      : value >= 0.5
        ? { label: "Medium", tone: "bg-impact-modified/10 text-impact-modified" }
        : { label: "Low", tone: "bg-impact-none/10 text-impact-none" };

  return (
    <span
      title={`Confidence ${pct}%`}
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium",
        band.tone,
      )}
    >
      {band.label}
      <span className="font-mono opacity-60">{pct}</span>
    </span>
  );
}
