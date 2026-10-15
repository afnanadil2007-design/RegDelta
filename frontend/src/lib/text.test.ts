import { describe, expect, it } from "vitest";

import { toBlocks, toRuns } from "@/lib/prose";
import { codePointLength, queryTerms, segmentText, sliceCodePoints, toUtf16Index } from "@/lib/text";

// "𝟓" (U+1D7D3) is one code point but two UTF-16 units, as Python and Postgres
// count it differently from JavaScript.
const ASTRAL = "Margin 𝟓% shall be collected upfront.";

describe("code-point offsets", () => {
  it("slices as Python would", () => {
    expect(codePointLength(ASTRAL)).toBe(ASTRAL.length - 1);
    expect(sliceCodePoints(ASTRAL, 7, 9)).toBe("𝟓%");
    expect(sliceCodePoints(ASTRAL, 10, 15)).toBe("shall");
    expect(toUtf16Index(ASTRAL, 9)).toBe(10);
  });

  it("is the identity on plain text", () => {
    expect(toUtf16Index("abcdef", 4)).toBe(4);
    expect(sliceCodePoints("abcdef", 1, 3)).toBe("bc");
  });
});

describe("segmentText", () => {
  it("places a span after an astral character at the right place", () => {
    // The text starts at absolute offset 100 in the full document.
    const { segments, outOfRange } = segmentText(ASTRAL, 100, [{ id: "quote", start: 110, end: 115 }]);
    expect(outOfRange).toEqual([]);
    expect(segments).toEqual([
      { text: "Margin 𝟓% ", spanId: null },
      { text: "shall", spanId: "quote" },
      { text: " be collected upfront.", spanId: null },
    ]);
  });

  it("reports a span outside the text instead of guessing", () => {
    const { segments, outOfRange } = segmentText("short", 0, [{ id: "quote", start: 3, end: 40 }]);
    expect(outOfRange).toEqual(["quote"]);
    expect(segments).toEqual([{ text: "short", spanId: null }]);
  });

  it("keeps the earlier of two overlapping spans", () => {
    const { segments } = segmentText("abcdefgh", 0, [
      { id: "a", start: 1, end: 4 },
      { id: "b", start: 3, end: 6 },
    ]);
    expect(segments.map((s) => [s.text, s.spanId])).toEqual([
      ["a", null],
      ["bcd", "a"],
      ["efgh", null],
    ]);
  });
});

describe("prose blocks", () => {
  it("joins soft wraps inside a mark without breaking the mark", () => {
    const { segments } = segmentText("1. Clients shall pay\nmargin upfront.\n\nNext.", 0, [
      { id: "quote", start: 3, end: 36 },
    ]);
    const blocks = toBlocks(segments, { stripPrefix: /^1[.)]\s+/ });
    expect(blocks).toHaveLength(2);
    expect(blocks[0].parts.every((p) => p.spanId === "quote")).toBe(true);
    expect(blocks[0].parts.map((p) => p.text).join("")).toBe("Clients shall pay margin upfront.");
  });

  it("reads manual headings, items, bold, and code without the markers", () => {
    const blocks = toBlocks([{ text: "### A.5 Re-KYC\n- every **ten** years for `LOW` risk", spanId: null }]);
    expect(blocks.map((b) => b.kind)).toEqual(["heading", "item"]);
    const runs = toRuns(blocks[1].parts);
    expect(runs.map((r) => r.text).join("")).toBe("every ten years for LOW risk");
    expect(runs.find((r) => r.text === "ten")?.bold).toBe(true);
    expect(runs.find((r) => r.text === "LOW")?.code).toBe(true);
  });

  it("keeps meaningful line breaks when asked", () => {
    expect(toBlocks([{ text: "Line one\nLine two", spanId: null }], { keepLines: true })).toHaveLength(2);
  });
});

describe("queryTerms", () => {
  it("drops short and stop words and duplicates", () => {
    expect(queryTerms("The margin, and the MARGIN before 2024/306")).toEqual(["margin", "2024/306"]);
  });
});
