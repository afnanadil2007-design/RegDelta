/**
 * Offsets from the API are Unicode code-point offsets (Python and Postgres
 * agree on them). JavaScript strings index UTF-16 code units, which differ as
 * soon as a text contains a character outside the Basic Multilingual Plane.
 * Every highlight goes through these helpers.
 */

const SURROGATE = /[\uD800-\uDFFF]/;

/** UTF-16 index of the code point at ``codePoint`` within ``text``. */
export function toUtf16Index(text: string, codePoint: number): number {
  if (codePoint <= 0) return 0;
  if (!SURROGATE.test(text)) return Math.min(codePoint, text.length);
  let units = 0;
  let points = 0;
  for (const character of text) {
    if (points === codePoint) return units;
    units += character.length;
    points += 1;
  }
  return units;
}

/** Number of code points in ``text``. */
export function codePointLength(text: string): number {
  return SURROGATE.test(text) ? Array.from(text).length : text.length;
}

/** ``text[start:end]`` with code-point offsets, as Python would slice it. */
export function sliceCodePoints(text: string, start: number, end: number): string {
  return text.slice(toUtf16Index(text, start), toUtf16Index(text, end));
}

export interface Span {
  /** Absolute code-point offsets in the source's coordinate space. */
  start: number;
  end: number;
  id: string;
}

export interface Segment {
  text: string;
  /** The span this segment belongs to, or null for unmarked text. */
  spanId: string | null;
}

export interface Segmentation {
  segments: Segment[];
  /** Spans that do not fit inside the shown text: shown as a warning, never guessed. */
  outOfRange: string[];
}

/**
 * Split ``text`` (which starts at absolute offset ``textStart``) into marked
 * and unmarked segments. Overlapping spans keep the earlier one; a span that
 * falls outside the text is reported instead of being placed approximately.
 */
export function segmentText(text: string, textStart: number, spans: Span[]): Segmentation {
  const length = codePointLength(text);
  const outOfRange: string[] = [];
  const local = spans
    .map((span) => ({ ...span, start: span.start - textStart, end: span.end - textStart }))
    .filter((span) => {
      const valid = span.start >= 0 && span.end <= length && span.start < span.end;
      if (!valid) outOfRange.push(span.id);
      return valid;
    })
    .sort((a, b) => a.start - b.start || a.end - b.end);

  const segments: Segment[] = [];
  let cursor = 0;
  for (const span of local) {
    if (span.start < cursor) continue; // overlap: the earlier span wins
    if (span.start > cursor) {
      segments.push({ text: sliceCodePoints(text, cursor, span.start), spanId: null });
    }
    segments.push({ text: sliceCodePoints(text, span.start, span.end), spanId: span.id });
    cursor = span.end;
  }
  if (cursor < length) segments.push({ text: sliceCodePoints(text, cursor, length), spanId: null });
  return { segments, outOfRange };
}

/** Lower-cased word tokens of a query, for marking query terms in a passage. */
export function queryTerms(query: string): string[] {
  const stop = new Set([
    "the",
    "and",
    "for",
    "of",
    "to",
    "in",
    "a",
    "an",
    "on",
    "by",
    "or",
    "with",
    "are",
    "was",
    "were",
    "this",
    "that",
    "from",
    "into",
    "than",
    "before",
    "after",
    "shall",
    "must",
  ]);
  return Array.from(
    new Set(
      query
        .toLowerCase()
        .split(/[^\p{L}\p{N}+/-]+/u)
        .filter((term) => term.length > 2 && !stop.has(term)),
    ),
  );
}
