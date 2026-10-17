import { describe, expect, it } from "vitest";

import { forceOn } from "@/lib/temporal";
import type { CircularDetail, Supersession } from "@/types/api";

function edge(
  type: Supersession["supersession_type"],
  effective: string | null,
  resolved = true,
): Supersession {
  return {
    id: 1,
    direction: "incoming",
    superseding_circular_id: 2,
    superseding_number: "B",
    superseding_title: null,
    superseded_circular_id: 1,
    superseded_number: "A",
    superseded_title: null,
    supersession_type: type,
    removes_from_force: type === "supersedes" || type === "rescinds",
    effective_date: effective,
    resolved,
    raw_reference: "B",
    evidence_paragraph_id: null,
  };
}

function circular(issued: string | null, supersessions: Supersession[]): CircularDetail {
  return {
    circular: {
      id: 1,
      circular_number: "A",
      title: "A",
      issue_date: issued,
      department: null,
      doc_type: "circular",
      page_count: 1,
      vision_page_count: 0,
      source_url: null,
      is_synthetic: true,
      obligation_count: 0,
      ingested_at: "2026-01-01T00:00:00Z",
    },
    provenance: { checksum: null, pdf_filename: null, ingested_at: "2026-01-01T00:00:00Z" },
    full_text: "",
    paragraphs: [],
    obligations: [],
    citations: [],
    cited_by: [],
    supersessions,
  };
}

describe("forceOn (mirrors the search as_of filter)", () => {
  it("is not in force before it was issued", () => {
    expect(forceOn(circular("2024-06-14", []), "2024-01-01").kind).toBe("not-issued");
  });

  it("leaves force on the effective date of a supersession, not before", () => {
    const detail = circular("2024-06-14", [edge("supersedes", "2024-12-11")]);
    expect(forceOn(detail, "2024-12-10").kind).toBe("in-force");
    expect(forceOn(detail, "2024-12-11")).toMatchObject({ kind: "out-of-force", since: "2024-12-11" });
  });

  it("stays in force when amended", () => {
    const state = forceOn(circular("2020-01-01", [edge("amends", "2021-01-01")]), "2022-01-01");
    expect(state.kind).toBe("in-force");
    expect(state.kind === "in-force" && state.amendedBy).toHaveLength(1);
  });

  it("does not apply an unresolved edge or one without an effective date", () => {
    expect(forceOn(circular("2020-01-01", [edge("rescinds", "2021-01-01", false)]), "2022-01-01").kind).toBe(
      "in-force",
    );
    const undated = forceOn(circular("2020-01-01", [edge("supersedes", null)]), "2022-01-01");
    expect(undated.kind === "in-force" && undated.undated).toHaveLength(1);
  });
});
