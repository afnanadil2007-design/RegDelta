"""HTTP API integration tests against the seeded test corpus.

These use the real routers, repositories, and retrieval models on the
``corpus`` fixture (five synthetic circulars and the shipped policy pack).
Assessment execution end to end is in test_assessment_flow.py.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app
from tests.conftest import SeededCorpus

MARGIN_2020 = "SEBI/HO/MIRSD/CIR/P/2020/99"
MARGIN_2024 = "SEBI/HO/MIRSD/MIRSD-PoD/CIR/P/2024/17"
CYBER_2024 = "SEBI/HO/ITD/ITD-PoD/CIR/P/2024/44"
CYBER_2025 = "SEBI/HO/ITD/ITD-PoD/CIR/P/2025/12"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


# --- health ---------------------------------------------------------------


def test_health_reports_database_schema_and_provider(client: TestClient, corpus) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["database"] == "up"
    assert body["schema_revision"] == "0004_evidence_provenance"
    assert body["provider"] == {
        "name": "deterministic",
        "model": "regdelta-rules-v1",
        "deterministic": True,
        "ready": True,
        "reason": None,
    }


# --- circulars --------------------------------------------------------------


def test_circular_page_lists_the_corpus_with_a_total(client: TestClient, corpus) -> None:
    body = client.get("/api/circulars?limit=2").json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert all(item["is_synthetic"] for item in body["items"])
    # Newest first.
    assert body["items"][0]["circular_number"] == CYBER_2025


def test_circular_filters_combine(client: TestClient, corpus) -> None:
    cyber = client.get("/api/circulars", params={"q": "cyber"}).json()
    assert {i["circular_number"] for i in cyber["items"]} == {CYBER_2024, CYBER_2025}

    mirsd_2024 = client.get(
        "/api/circulars",
        params={"department": "MIRSD", "date_from": "2024-01-01", "date_to": "2024-12-31"},
    ).json()
    assert mirsd_2024["total"] == 2  # margin 2024 and KYC 2024

    # LIKE wildcards in the search box are literal text, not patterns.
    assert client.get("/api/circulars", params={"q": "%"}).json()["total"] == 0


def test_inverted_date_range_is_a_validation_error(client: TestClient, corpus) -> None:
    response = client.get(
        "/api/circulars", params={"date_from": "2025-01-01", "date_to": "2024-01-01"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_date_range"


def test_circular_detail_offsets_resolve_against_full_text(
    client: TestClient, corpus: SeededCorpus
) -> None:
    body = client.get(f"/api/circulars/{corpus.id_of(MARGIN_2024)}").json()
    text = body["full_text"]
    assert body["paragraphs"] and body["obligations"]
    for paragraph in body["paragraphs"]:
        assert text[paragraph["char_start"] : paragraph["char_end"]] == paragraph["text"]
    for obligation in body["obligations"]:
        assert text[obligation["char_start"] : obligation["char_end"]] == obligation["text"]
        assert obligation["extractor"] == "rules-v2"
        assert obligation["model_confidence"] is None  # the rules extractor has none


def test_circular_detail_carries_provenance(client: TestClient, corpus: SeededCorpus) -> None:
    body = client.get(f"/api/circulars/{corpus.id_of(MARGIN_2024)}").json()
    provenance = body["provenance"]
    assert re.fullmatch(r"[0-9a-f]{64}", provenance["checksum"])
    assert "/" not in provenance["pdf_filename"], "a local filesystem path must not leak"
    assert body["circular"]["source_url"].startswith("synthetic://")


def test_supersession_and_amendment_edges_are_distinguished(
    client: TestClient, corpus: SeededCorpus
) -> None:
    margin = client.get(f"/api/circulars/{corpus.id_of(MARGIN_2024)}").json()
    (edge,) = [s for s in margin["supersessions"] if s["direction"] == "outgoing"]
    assert edge["superseded_circular_id"] == corpus.id_of(MARGIN_2020)
    assert edge["supersession_type"] == "supersedes"
    assert edge["removes_from_force"] is True
    assert edge["effective_date"] == "2024-02-12"

    old = client.get(f"/api/circulars/{corpus.id_of(MARGIN_2020)}").json()
    assert [s["direction"] for s in old["supersessions"]] == ["incoming"]
    assert [c["citing_circular_number"] for c in old["cited_by"]] == [MARGIN_2024]

    cyber = client.get(f"/api/circulars/{corpus.id_of(CYBER_2024)}").json()
    (amendment,) = cyber["supersessions"]
    assert amendment["direction"] == "incoming"
    assert amendment["supersession_type"] == "amends"
    assert amendment["removes_from_force"] is False


def test_unknown_circular_returns_the_error_envelope(client: TestClient, corpus) -> None:
    response = client.get("/api/circulars/99999999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "circular_not_found"


# --- search -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "score_kind", "has_threshold"),
    [
        ("dense", "cosine_similarity", False),
        ("lexical", "ts_rank_cd", False),
        ("hybrid", "rrf", False),
        ("hybrid_rerank", "cross_encoder_sigmoid", True),
    ],
)
def test_search_reports_what_its_scores_mean(
    client: TestClient, corpus, mode: str, score_kind: str, has_threshold: bool
) -> None:
    body = client.post(
        "/api/search", json={"query": "short-collection of margin reporting", "mode": mode}
    ).json()
    assert body["mode"] == mode
    assert body["score_kind"] == score_kind
    assert (body["threshold"] is not None) is has_threshold
    assert body["hits"], "a matching query should return passages"
    assert body["elapsed_ms"] >= 0
    hit = body["hits"][0]
    assert hit["dense_rank"] is not None or hit["lexical_rank"] is not None


def test_reranked_search_refuses_an_unrelated_query(client: TestClient, corpus) -> None:
    body = client.post(
        "/api/search", json={"query": "What is the capital of France?", "mode": "hybrid_rerank"}
    ).json()
    assert body["refused"] is True
    assert body["hits"] == []
    assert body["top_score"] < body["threshold"]


def test_as_of_hides_superseded_circulars_but_not_amended_ones(
    client: TestClient, corpus: SeededCorpus
) -> None:
    margin = client.post(
        "/api/search",
        json={"query": "short-collection of margin", "mode": "lexical", "as_of": "2025-06-01"},
    ).json()
    hit_ids = {h["circular_id"] for h in margin["hits"]}
    assert corpus.id_of(MARGIN_2020) not in hit_ids
    assert corpus.id_of(MARGIN_2024) in hit_ids
    assert [e["circular_number"] for e in margin["excluded_by_temporal_filter"]] == [MARGIN_2020]

    cyber = client.post(
        "/api/search",
        json={"query": "cyber security incidents", "mode": "lexical", "as_of": "2025-06-01"},
    ).json()
    assert corpus.id_of(CYBER_2024) in {h["circular_id"] for h in cyber["hits"]}
    assert cyber["excluded_by_temporal_filter"] == []


def test_as_of_before_the_supersession_keeps_the_old_circular(
    client: TestClient, corpus: SeededCorpus
) -> None:
    body = client.post(
        "/api/search",
        json={"query": "short-collection of margin", "mode": "lexical", "as_of": "2024-02-11"},
    ).json()
    hit_ids = {h["circular_id"] for h in body["hits"]}
    assert corpus.id_of(MARGIN_2020) in hit_ids
    # The superseding circular was not issued yet.
    assert corpus.id_of(MARGIN_2024) not in hit_ids


@pytest.mark.parametrize(
    "payload",
    [
        {"query": ""},
        {"query": "   "},
        {"query": "margin", "top_k": 0},
        {"query": "margin", "top_k": 500},
        {"query": "x" * 2001},
        {"query": "margin", "date_from": "2025-01-01", "date_to": "2024-01-01"},
        {"query": "margin", "mode": "keyword"},
    ],
)
def test_invalid_search_is_rejected_in_the_envelope(
    client: TestClient, corpus, payload: dict
) -> None:
    response = client.post("/api/search", json=payload)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert error["message"]
    assert isinstance(error["detail"], list) and error["detail"]


# --- policy packs -------------------------------------------------------------


def test_policy_pack_and_clauses(client: TestClient, corpus: SeededCorpus) -> None:
    (pack,) = client.get("/api/policy-packs").json()
    assert pack["id"] == corpus.policy_pack_id
    assert pack["is_synthetic"] is True
    assert pack["clause_count"] >= 40

    clauses = client.get(f"/api/policy-packs/{pack['id']}/clauses").json()
    numbers = [c["clause_number"] for c in clauses]
    assert len(numbers) == len(set(numbers)) == pack["clause_count"]


def test_unknown_policy_pack_returns_envelope(client: TestClient, corpus) -> None:
    response = client.get("/api/policy-packs/999999/clauses")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "policy_pack_not_found"


# --- assessment launch --------------------------------------------------------


def test_assessment_for_unknown_circular_is_rejected(client: TestClient, corpus) -> None:
    response = client.post("/api/assessments", json={"circular_id": 99999999, "policy_pack_id": 1})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "circular_not_found"


def test_assessment_for_unknown_policy_pack_is_rejected(
    client: TestClient, corpus: SeededCorpus
) -> None:
    response = client.post(
        "/api/assessments",
        json={"circular_id": corpus.id_of(MARGIN_2024), "policy_pack_id": 999999},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "policy_pack_not_found"


def test_assessment_without_a_provider_key_is_unavailable_not_broken(
    corpus: SeededCorpus,
) -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        llm_provider="groq", groq_api_key=None
    )
    response = TestClient(app).post(
        "/api/assessments",
        json={"circular_id": corpus.id_of(MARGIN_2024), "policy_pack_id": corpus.policy_pack_id},
    )
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "provider_unavailable"
    assert "GROQ_API_KEY" in error["message"]


def test_unknown_assessment_returns_envelope(client: TestClient, corpus) -> None:
    response = client.get("/api/assessments/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "assessment_not_found"


def test_assessments_page_shape(client: TestClient, corpus) -> None:
    body = client.get("/api/assessments?limit=5").json()
    assert set(body) == {"items", "total", "limit", "offset"}
    assert body["limit"] == 5


def test_eval_runs_endpoint(client: TestClient, corpus) -> None:
    response = client.get("/api/eval/runs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
