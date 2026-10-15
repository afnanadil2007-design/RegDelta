/**
 * Placing a finding's evidence in its source: which spans to mark, which
 * paragraphs or clauses to show around them, and what the shoulder calls them.
 */
import { IMPACT_ORDER } from "@/lib/labels";
import type { Span } from "@/lib/text";
import type { Finding, Paragraph } from "@/types/api";

/** The circular-side mark: the located quote, else the obligation itself. */
export function circularSpan(finding: Finding): Span {
  if (finding.circular_span_start !== null && finding.circular_span_end !== null) {
    return { id: "quote", start: finding.circular_span_start, end: finding.circular_span_end };
  }
  return { id: "obligation", start: finding.obligation_char_start, end: finding.obligation_char_end };
}

export function clauseSpan(finding: Finding): Span | null {
  if (finding.clause_span_start === null || finding.clause_span_end === null) return null;
  return { id: "quote", start: finding.clause_span_start, end: finding.clause_span_end };
}

/** The part of ``span`` inside [start, end), or null when they do not meet. */
export function clip(span: Span, start: number, end: number): Span | null {
  const s = Math.max(span.start, start);
  const e = Math.min(span.end, end);
  return s < e ? { ...span, start: s, end: e } : null;
}

/** Index of the first item whose range meets the span; -1 if none does. */
export function locate<T extends { char_start: number; char_end: number }>(items: T[], span: Span): number {
  return items.findIndex((item) => span.start < item.char_end && span.end > item.char_start);
}

/** ``radius`` items either side of ``index``, clamped to the list. */
export function around<T>(items: T[], index: number, radius: number): { items: T[]; from: number } {
  const from = Math.max(0, index - radius);
  return { items: items.slice(from, index + radius + 1), from };
}

/** "¶3" for a numbered paragraph, "p. 2" otherwise, or null. */
export function paragraphLabel(paragraph: Paragraph): string | null {
  if (paragraph.para_number) return `¶${paragraph.para_number}`;
  return null;
}

/** A paragraph that only repeats its own section heading. */
export function isSectionHeading(paragraph: Paragraph): boolean {
  return !paragraph.para_number && paragraph.text.trim() === paragraph.heading_path?.trim();
}

/** Matches a paragraph's own leading number, which the shoulder already shows. */
export function numberPrefix(paragraph: Paragraph): RegExp | undefined {
  if (!paragraph.para_number) return undefined;
  const escaped = paragraph.para_number.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`^\\s*\\(?${escaped}[.)]\\s+`);
}

export interface FindingGroup {
  obligationId: number;
  obligationText: string;
  start: number;
  label: string;
  findings: Finding[];
}

/**
 * Findings grouped under the obligation they assess, in document order; within
 * an obligation the most consequential verdict comes first.
 */
export function groupFindings(findings: Finding[], paragraphs: Paragraph[] | undefined): FindingGroup[] {
  const groups = new Map<number, FindingGroup>();
  for (const finding of findings) {
    let group = groups.get(finding.obligation_id);
    if (!group) {
      group = {
        obligationId: finding.obligation_id,
        obligationText: finding.obligation_text,
        start: finding.obligation_char_start,
        label: "",
        findings: [],
      };
      groups.set(finding.obligation_id, group);
    }
    group.findings.push(finding);
  }
  const ordered = [...groups.values()].sort((a, b) => a.start - b.start || a.obligationId - b.obligationId);
  ordered.forEach((group, index) => {
    const paragraph = paragraphs?.find((p) => group.start >= p.char_start && group.start < p.char_end);
    group.label = (paragraph && paragraphLabel(paragraph)) ?? `${index + 1}`;
    group.findings.sort(
      (a, b) =>
        IMPACT_ORDER.indexOf(a.impact_type) - IMPACT_ORDER.indexOf(b.impact_type) ||
        (a.clause_number ?? "").localeCompare(b.clause_number ?? "", undefined, { numeric: true }),
    );
  });
  return ordered;
}
