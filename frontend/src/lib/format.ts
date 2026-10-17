import type { Usage } from "@/types/api";

const DATE = new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric" });
const DATE_TIME = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});
const INTEGER = new Intl.NumberFormat("en-GB");

/** "11 Dec 2024"; an absent date says so rather than inventing one. */
export function formatDate(iso: string | null | undefined, missing = "No date"): string {
  if (!iso) return missing;
  const date = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  return Number.isNaN(date.getTime()) ? missing : DATE.format(date);
}

export function formatDateTime(iso: string | null | undefined, missing = "Not yet"): string {
  if (!iso) return missing;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? missing : DATE_TIME.format(date);
}

export function formatInteger(value: number): string {
  return INTEGER.format(value);
}

/** "320 ms", "4.8 s", "2 min 05 s". */
export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "Not recorded";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  const minutes = Math.floor(ms / 60_000);
  const seconds = Math.round((ms % 60_000) / 1000);
  return `${minutes} min ${String(seconds).padStart(2, "0")} s`;
}

/**
 * Estimated list-price cost. Unknown is never shown as $0: a model with no
 * price in the table makes the estimate unavailable or partial.
 */
export function describeCost(usage: Usage, deterministic: boolean): { value: string; note?: string } {
  if (deterministic) return { value: "$0.00", note: "Rule-based judge, run locally" };
  if (usage.estimated_cost_usd === null) {
    return { value: "Unknown", note: "The model has no list price in RegDelta's pricing table" };
  }
  const value = `$${usage.estimated_cost_usd.toFixed(4)}`;
  if (!usage.cost_complete) {
    return { value: `at least ${value}`, note: `${usage.unpriced_calls} call(s) used an unpriced model` };
  }
  return { value, note: "List-price estimate, not a bill" };
}

export function plural(count: number, singular: string, pluralForm = `${singular}s`): string {
  return `${formatInteger(count)} ${count === 1 ? singular : pluralForm}`;
}
