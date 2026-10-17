/**
 * Source text arrives with hard line wraps (PDF extraction) and light
 * Markdown (the policy manual: ``###`` headings, ``-`` items, ``**bold**``,
 * ``code``). These helpers turn marked segments into reading blocks without
 * moving any mark: formatting is display only and offsets are never recomputed.
 */
import type { Segment } from "@/lib/text";

export type BlockKind = "heading" | "paragraph" | "item";

export interface Block {
  kind: BlockKind;
  parts: Segment[];
}

export interface Run {
  text: string;
  spanId: string | null;
  bold: boolean;
  code: boolean;
}

/** Remove the first ``count`` characters of a line, across segments. */
function dropPrefix(line: Segment[], count: number): Segment[] {
  const out: Segment[] = [];
  let remaining = count;
  for (const segment of line) {
    if (remaining >= segment.text.length) {
      remaining -= segment.text.length;
      continue;
    }
    out.push({ ...segment, text: segment.text.slice(remaining) });
    remaining = 0;
  }
  return out;
}

function splitLines(segments: Segment[]): Segment[][] {
  const lines: Segment[][] = [[]];
  for (const segment of segments) {
    segment.text.split("\n").forEach((piece, index) => {
      if (index > 0) lines.push([]);
      if (piece) lines[lines.length - 1].push({ text: piece, spanId: segment.spanId });
    });
  }
  return lines;
}

/**
 * Group lines into blocks: blank lines end a paragraph, soft wraps become a
 * space (marked when both sides belong to the same span, so a highlight does
 * not break at a line end), ``#`` lines are headings, ``-`` lines are items.
 * ``keepLines`` treats every line as its own paragraph (generated text such
 * as the memo, where a line break is meaningful).
 */
export function toBlocks(
  segments: Segment[],
  { stripPrefix, keepLines = false }: { stripPrefix?: RegExp; keepLines?: boolean } = {},
): Block[] {
  const blocks: Block[] = [];
  let current: Block | null = null;
  let first = true;
  for (let line of splitLines(segments)) {
    let plain = line.map((s) => s.text).join("");
    if (first && stripPrefix) {
      const match = stripPrefix.exec(plain);
      if (match) {
        line = dropPrefix(line, match[0].length);
        plain = plain.slice(match[0].length);
      }
    }
    first = false;
    if (!plain.trim()) {
      current = null;
      continue;
    }
    const heading = /^#{1,6}\s+/.exec(plain);
    if (heading) {
      blocks.push({ kind: "heading", parts: dropPrefix(line, heading[0].length) });
      current = null;
      continue;
    }
    const item = /^\s*[-*•]\s+/.exec(plain);
    if (item) {
      current = { kind: "item", parts: dropPrefix(line, item[0].length) };
      blocks.push(current);
      continue;
    }
    if (current && !keepLines) {
      const before = current.parts[current.parts.length - 1]?.spanId ?? null;
      const after = line[0]?.spanId ?? null;
      current.parts.push({ text: " ", spanId: before === after ? before : null }, ...line);
    } else {
      current = { kind: "paragraph", parts: [...line] };
      blocks.push(current);
    }
  }
  return blocks;
}

/** Split parts on ``**`` and backtick markers; the markers themselves are dropped. */
export function toRuns(parts: Segment[]): Run[] {
  const runs: Run[] = [];
  let bold = false;
  let code = false;
  for (const part of parts) {
    for (const token of part.text.split(/(\*\*|`)/)) {
      if (token === "**") bold = !bold;
      else if (token === "`") code = !code;
      else if (token) runs.push({ text: token, spanId: part.spanId, bold, code });
    }
  }
  return runs;
}
