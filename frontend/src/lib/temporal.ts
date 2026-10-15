/**
 * Whether a circular was in force on a date, decided exactly as the search
 * filter decides it (backend/app/repositories/search.py): a resolved
 * supersedes or rescinds edge that took effect on or before the date takes
 * it out of force; an amendment leaves it in force as amended; an edge with no
 * recorded effective date is not applied, and the UI says so.
 */
import type { CircularDetail, Supersession } from "@/types/api";

export type ForceState =
  | { kind: "not-issued" }
  | { kind: "out-of-force"; since: string; by: Supersession }
  | { kind: "in-force"; amendedBy: Supersession[]; undated: Supersession[] }
  | { kind: "unknown-date" };

export function forceOn(detail: CircularDetail, date: string): ForceState {
  const issued = detail.circular.issue_date;
  if (!issued) return { kind: "unknown-date" };
  if (issued > date) return { kind: "not-issued" };
  const incoming = detail.supersessions.filter((s) => s.direction === "incoming" && s.resolved);
  const removal = incoming
    .filter((s) => s.removes_from_force && s.effective_date !== null && s.effective_date <= date)
    .sort((a, b) => (a.effective_date ?? "").localeCompare(b.effective_date ?? ""))[0];
  if (removal) return { kind: "out-of-force", since: removal.effective_date as string, by: removal };
  return {
    kind: "in-force",
    amendedBy: incoming.filter(
      (s) => !s.removes_from_force && (s.effective_date === null || s.effective_date <= date),
    ),
    undated: incoming.filter((s) => s.removes_from_force && s.effective_date === null),
  };
}

/** Local calendar date as YYYY-MM-DD (not UTC, which can be a day off). */
export function today(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

export function isIsoDate(value: string | null): value is string {
  return value !== null && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value));
}
