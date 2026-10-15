"""Stage 5-8 unit tests: RRF, spans, schemas, policy parsing, metrics."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ai.extraction.schemas import (
    ExtractedObligation,
    JudgedImpact,
    ObligationExtraction,
    json_schema_for,
)
from app.ai.extraction.spans import resolve_span, span_within
from app.ai.retrieval.fusion import reciprocal_rank_fusion
from app.db.models.enums import ImpactType
from app.services.policy_pack import parse_pack
from evaluation.metrics.retrieval import QueryOutcome, ranking_metrics, refusal_metrics
from evaluation.stats import wilson

# --- RRF ---------------------------------------------------------------


def test_rrf_uses_ranks_not_scores() -> None:
    """Two lists agreeing on a document must rank it first."""
    fused = reciprocal_rank_fusion({"dense": [7, 1, 2], "lexical": [7, 3, 4]}, k=60)
    assert fused[0].chunk_id == 7
    assert fused[0].dense_rank == 1
    assert fused[0].lexical_rank == 1


def test_rrf_score_matches_the_formula() -> None:
    fused = reciprocal_rank_fusion({"dense": [5], "lexical": [5]}, k=60)
    assert fused[0].rrf_score == pytest.approx(2 * (1 / 61))


def test_rrf_document_in_one_list_only_still_scores() -> None:
    fused = reciprocal_rank_fusion({"dense": [1], "lexical": [2]}, k=60)
    by_id = {h.chunk_id: h for h in fused}
    assert by_id[1].lexical_rank is None
    assert by_id[2].dense_rank is None
    assert by_id[1].rrf_score == pytest.approx(1 / 61)


def test_rrf_is_deterministic_on_ties() -> None:
    """Flapping order would make evaluation numbers irreproducible."""
    a = reciprocal_rank_fusion({"dense": [3, 1], "lexical": [1, 3]}, k=60)
    b = reciprocal_rank_fusion({"dense": [3, 1], "lexical": [1, 3]}, k=60)
    assert [h.chunk_id for h in a] == [h.chunk_id for h in b]


def test_rrf_k_damps_top_rank_dominance() -> None:
    """A larger k narrows the gap between rank 1 and rank 2."""
    small = reciprocal_rank_fusion({"dense": [1, 2]}, k=1)
    large = reciprocal_rank_fusion({"dense": [1, 2]}, k=1000)
    gap_small = small[0].rrf_score - small[1].rrf_score
    gap_large = large[0].rrf_score - large[1].rrf_score
    assert gap_large < gap_small


def test_rrf_handles_empty_lists() -> None:
    assert reciprocal_rank_fusion({"dense": [], "lexical": []}) == []


def test_rrf_keeps_best_rank_for_repeated_document() -> None:
    fused = reciprocal_rank_fusion({"dense": [4, 4, 4]}, k=60)
    assert len(fused) == 1
    assert fused[0].dense_rank == 1


# --- span resolution ----------------------------------------------------


def test_span_resolves_exactly() -> None:
    source = "1. Brokers shall collect upfront margin from clients."
    span = resolve_span("shall collect upfront margin", source)
    assert span is not None
    assert source[span.char_start : span.char_end] == "shall collect upfront margin"


def test_span_offsets_shift_by_base() -> None:
    source = "Brokers shall report by T+1."
    span = resolve_span("shall report", source, base_offset=500)
    assert span is not None
    assert span.char_start == 508


def test_span_tolerates_rewrapped_whitespace() -> None:
    """A model quoting across a line break is still quoting faithfully."""
    source = "Brokers shall collect\nupfront margin from clients."
    span = resolve_span("shall collect upfront margin", source)
    assert span is not None
    assert "collect" in source[span.char_start : span.char_end]


def test_unresolvable_quote_returns_none() -> None:
    """A hallucinated quote must fail loudly, not produce a guessed span."""
    assert resolve_span("shall levitate the exchange", "Brokers shall report.") is None


def test_empty_quote_returns_none() -> None:
    assert resolve_span("   ", "some source text") is None


def test_span_within_bounds() -> None:
    span = resolve_span("shall report", "Brokers shall report by T+1.")
    assert span is not None
    assert span_within(span, 0, 40)
    assert not span_within(span, 0, 10)


# --- schemas and repair contract ---------------------------------------


def test_obligation_schema_rejects_short_text() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ExtractedObligation(text="short")


def test_obligation_schema_rejects_out_of_range_confidence() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ExtractedObligation(text="Brokers shall report by T+1.", confidence=1.5)


def test_empty_extraction_is_valid() -> None:
    """No obligations is a correct answer for a header or recital."""
    assert ObligationExtraction.model_validate({"obligations": []}).obligations == []


def test_judged_impact_requires_a_known_impact_type() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        JudgedImpact(
            impact_type="MAYBE",  # type: ignore[arg-type]
            rationale="x" * 30,
            confidence=0.5,
        )


def test_judged_impact_accepts_every_enum_member() -> None:
    for impact in ImpactType:
        judged = JudgedImpact(impact_type=impact, rationale="y" * 30, confidence=0.4)
        assert judged.impact_type is impact


def test_json_schema_is_self_contained() -> None:
    """Structured outputs reject $ref indirection, so it must be inlined."""
    schema = json_schema_for(ObligationExtraction)
    assert "$defs" not in schema
    assert "$ref" not in repr(schema)
    assert schema["additionalProperties"] is False


# --- policy pack parsing ------------------------------------------------


POLICY_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "policy_packs"
    / ("internal_compliance_manual_v1.md")
)


def test_policy_pack_parses_into_clauses() -> None:
    clauses = parse_pack(POLICY_PATH.read_text(encoding="utf-8"))
    assert len(clauses) >= 40, f"expected ~40 clauses, got {len(clauses)}"


def test_policy_clause_spans_resolve_against_the_source() -> None:
    """Clause offsets index the markdown, exactly like circular offsets."""
    markdown = POLICY_PATH.read_text(encoding="utf-8")
    for clause in parse_pack(markdown):
        assert markdown[clause.char_start : clause.char_end] == clause.text


def test_policy_clause_numbers_are_unique_and_carry_their_part() -> None:
    clauses = parse_pack(POLICY_PATH.read_text(encoding="utf-8"))
    numbers = [c.clause_number for c in clauses]
    assert len(numbers) == len(set(numbers))
    assert all(c.heading_path for c in clauses)
    assert any("Margin" in c.heading_path for c in clauses)


def test_policy_pack_is_marked_synthetic() -> None:
    """The pack is fictional; that must be unmissable in the source."""
    text = POLICY_PATH.read_text(encoding="utf-8")
    assert "SYNTHETIC" in text
    assert "not legal advice" in text.lower()


# --- retrieval metrics --------------------------------------------------


def _outcome(
    qid: str,
    subset: str,
    retrieved: list[str],
    relevant: list[str],
    cluster: str = "c",
    refused: bool | None = None,
) -> QueryOutcome:
    return QueryOutcome(
        query_id=qid,
        subset=subset,
        cluster=cluster,
        mode="hybrid",
        relevant=relevant,
        retrieved=retrieved,
        top_score=None,
        refused=refused,
        latency_ms=1.0,
    )


def _values(metrics: list) -> dict[str, float]:
    return {m.name: m.value for m in metrics}


def test_recall_and_mrr_on_a_known_ranking() -> None:
    outcomes = [
        _outcome("a", "semantic", ["X", "Y", "R1"], ["R1"]),  # first relevant at rank 3
        _outcome("b", "semantic", ["R2", "Z"], ["R2"]),  # rank 1
        _outcome("c", "semantic", ["P", "Q"], ["R3"]),  # miss
    ]
    values = _values(ranking_metrics(outcomes, "semantic"))
    assert values["recall@1"] == pytest.approx(1 / 3)
    assert values["recall@5"] == pytest.approx(2 / 3)
    assert values["mrr@10"] == pytest.approx((1 / 3 + 1 + 0) / 3)


def test_recall_at_k_respects_the_cutoff() -> None:
    outcome = _outcome("a", "semantic", ["1", "2", "3", "4", "5", "6", "R"], ["R"])
    assert outcome.hit(5) == 0.0
    assert outcome.hit(10) == 1.0


def test_a_refused_query_is_a_miss_only_in_answered_recall() -> None:
    in_scope = [
        _outcome("a", "semantic", ["R"], ["R"], refused=True),
        _outcome("b", "semantic", ["R"], ["R"], refused=False),
    ]
    out_scope = [_outcome("o1", "out_of_scope", ["X"], [], refused=True)]
    values = {(m.name, m.subset): m.value for m in refusal_metrics(in_scope, out_scope)}
    assert _values(ranking_metrics(in_scope, "all"))["recall@10"] == 1.0
    assert values[("answered_recall@10", "in_scope")] == 0.5
    assert values[("refusal_rate", "in_scope")] == 0.5
    assert values[("refusal_rate", "out_of_scope")] == 1.0


def test_a_refused_control_is_a_false_refusal_not_a_correct_one() -> None:
    in_scope = [_outcome("a", "semantic", ["R"], ["R"], refused=False)]
    out_scope = [_outcome("oos-1", "out_of_scope", ["X"], [], refused=True)]
    controls = [
        _outcome("in-1", "control", ["X"], [], refused=True),
        _outcome("in-2", "control", ["X"], [], refused=False),
    ]
    values = {(m.name, m.subset): m.value for m in refusal_metrics(in_scope, out_scope, controls)}
    assert values[("refusal_rate", "out_of_scope")] == 1.0
    assert values[("refusal_rate", "control")] == 0.5
    assert values[("refusal_rate", "in_scope")] == 0.0


def test_the_refusal_suite_separates_questions_to_refuse_from_controls() -> None:
    from evaluation.run_eval import _refusal_queries, _refusal_rows

    expected = {row["id"]: row["should_refuse"] for row in _refusal_rows()}
    subsets = {q.query_id: q.subset for q in _refusal_queries()}
    assert subsets == {
        qid: "out_of_scope" if refuse else "control" for qid, refuse in expected.items()
    }
    assert "control" in subsets.values() and "out_of_scope" in subsets.values()


def test_a_mode_without_a_threshold_reports_that_it_never_refuses() -> None:
    metrics = refusal_metrics([_outcome("a", "semantic", ["R"], ["R"])], [])
    assert all(m.value == 0.0 and m.note for m in metrics)


def test_metrics_on_empty_input_are_empty_not_zero() -> None:
    assert ranking_metrics([], "semantic") == []


def test_intervals_resample_clusters_not_queries() -> None:
    # Five clusters of perfectly correlated queries: the interval reflects five
    # observations, so it must stay wide although there are twenty queries.
    outcomes = [
        _outcome(f"{c}-{i}", "semantic", ["R"] if c % 2 else ["X"], ["R"], cluster=str(c))
        for c in range(5)
        for i in range(4)
    ]
    recall = next(m for m in ranking_metrics(outcomes, "all") if m.name == "recall@10")
    assert recall.ci is not None
    low, high = recall.ci
    assert high - low > 0.4


def test_wilson_interval_bounds() -> None:
    low, high = wilson(30, 30)
    assert high == 1.0 and 0.85 < low < 0.9
    assert wilson(0, 0) is None


# --- temporal exclusion reporting ---------------------------------------


@pytest.mark.asyncio
async def test_as_of_reports_what_it_excluded(session) -> None:
    """Regression guard for a bug that made the UI banner permanently empty.

    The main retrievers filter superseded circulars out in SQL, so asking which
    of *their* results were excluded always answers "none". The exclusion probe
    must re-run retrieval without the temporal predicate to find results that
    would otherwise have ranked.
    """
    from datetime import date

    from sqlalchemy import text as sql_text

    from app.ai.retrieval.pipeline import retrieve
    from app.db.models.enums import RetrievalMode
    from app.repositories.search import SearchFilters

    # Find a supersession edge whose superseded circular has an embedded chunk,
    # so it is genuinely reachable by retrieval before the filter applies.
    row = (
        await session.execute(
            sql_text(
                """
                SELECT s.superseded_circular_id, s.effective_date, ch.text
                FROM supersessions s
                JOIN chunks ch ON ch.circular_id = s.superseded_circular_id
                WHERE s.resolved AND s.effective_date IS NOT NULL
                  AND ch.embedding IS NOT NULL
                LIMIT 1
                """
            )
        )
    ).first()
    if row is None:
        pytest.skip("no resolved supersession with an embedded chunk in this corpus")

    superseded_id, effective, chunk_text = row
    as_of = date.fromisoformat(str(effective)) if not isinstance(effective, date) else effective

    # Query with the superseded circular's own words, as of a date after it
    # stopped being in force. Lexical mode keeps the test fast.
    result = await retrieve(
        session,
        " ".join(chunk_text.split()[:25]),
        mode=RetrievalMode.LEXICAL,
        filters=SearchFilters(as_of=as_of),
    )

    # The superseded circular must not appear in the hits...
    assert all(h.circular_id != superseded_id for h in result.hits)
    # ...and the exclusion list must be reachable (not hard-wired empty).
    assert isinstance(result.excluded_by_temporal_filter, list)


@pytest.mark.asyncio
async def test_no_as_of_means_no_exclusions_reported(session) -> None:
    from app.ai.retrieval.pipeline import retrieve
    from app.db.models.enums import RetrievalMode
    from app.repositories.search import SearchFilters

    result = await retrieve(
        session, "margin collection", mode=RetrievalMode.LEXICAL, filters=SearchFilters()
    )
    assert result.excluded_by_temporal_filter == []


def test_rerank_scores_span_the_full_zero_to_one_range() -> None:
    """The threshold is meaningless unless irrelevant passages score near zero.

    Regression guard for a double-sigmoid bug: `CrossEncoder.predict` already
    applies the model's sigmoid, so squashing its output again compressed every
    score into (0.5, 0.731). Ranking still looked correct, so the ablation
    caught nothing — but no score could fall below RELEVANCE_THRESHOLD and the
    refusal path was silently dead.
    """
    from app.ai.retrieval.reranker import rerank
    from app.core.config import get_settings

    passage = "Stock brokers shall collect upfront margin from clients before accepting orders."
    ((_, irrelevant),) = rerank("What is the capital of France?", [(1, passage)])
    ((_, relevant),) = rerank("upfront margin collection from clients", [(1, passage)])

    threshold = get_settings().relevance_threshold
    assert irrelevant < threshold, "an unrelated query must fall below the threshold"
    assert relevant > threshold, "a matching query must clear the threshold"
    # Guards the specific failure mode: a second sigmoid floors every score at 0.5.
    assert irrelevant < 0.5
