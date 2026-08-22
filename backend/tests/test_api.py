"""API integration tests against the live database.

These use the real routers and the real repositories; only the model provider
is absent, so assessment *execution* is covered by its own unit tests rather
than here.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def _skip_without_corpus(response) -> list:
    if response.status_code != 200:
        pytest.skip("corpus not seeded — run `make seed`")
    data = response.json()
    if not data:
        pytest.skip("corpus not seeded — run `make seed`")
    return data


def test_health_reports_database_up(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    if body["database"] != "up":
        pytest.skip("database not reachable")


def test_circulars_list_and_detail_round_trip(client: TestClient) -> None:
    circulars = _skip_without_corpus(client.get("/api/circulars?limit=3"))
    first = circulars[0]
    assert first["circular_number"]

    detail = client.get(f"/api/circulars/{first['id']}")
    assert detail.status_code == 200
    body = detail.json()

    assert body["circular"]["id"] == first["id"]
    assert body["full_text"]
    assert body["paragraphs"]

    # The provenance contract, over the API surface this time.
    for paragraph in body["paragraphs"]:
        sliced = body["full_text"][paragraph["char_start"] : paragraph["char_end"]]
        assert sliced == paragraph["text"]


def test_unknown_circular_returns_the_error_envelope(client: TestClient) -> None:
    response = client.get("/api/circulars/99999999")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "circular_not_found"
    assert "99999999" in body["error"]["message"]


def test_departments_endpoint(client: TestClient) -> None:
    response = client.get("/api/circulars/departments")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.parametrize("mode", ["dense", "lexical", "hybrid", "hybrid_rerank"])
def test_search_works_in_every_mode(client: TestClient, mode: str) -> None:
    """The four ablation modes are the same code path the UI uses."""
    _skip_without_corpus(client.get("/api/circulars?limit=1"))
    response = client.post(
        "/api/search",
        json={"query": "upfront margin collection reporting", "mode": mode},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == mode
    assert isinstance(body["hits"], list)
    # Either results, or an explicit refusal — never a silent empty answer.
    assert body["hits"] or body["below_threshold"] or body["top_score"] is None


def test_search_exposes_per_retriever_ranks(client: TestClient) -> None:
    """The UI shows fusion contributions, so ranks must survive to the API."""
    _skip_without_corpus(client.get("/api/circulars?limit=1"))
    body = client.post(
        "/api/search", json={"query": "cyber security incident reporting", "mode": "hybrid"}
    ).json()
    if not body["hits"]:
        pytest.skip("no hits for this query")
    hit = body["hits"][0]
    assert "dense_rank" in hit and "lexical_rank" in hit
    assert hit["dense_rank"] is not None or hit["lexical_rank"] is not None


def test_search_rejects_an_empty_query(client: TestClient) -> None:
    assert client.post("/api/search", json={"query": ""}).status_code == 422


def test_point_in_time_filter_is_accepted(client: TestClient) -> None:
    _skip_without_corpus(client.get("/api/circulars?limit=1"))
    response = client.post(
        "/api/search",
        json={"query": "margin collection", "mode": "lexical", "as_of": "2021-01-01"},
    )
    assert response.status_code == 200
    assert "excluded_by_temporal_filter" in response.json()


def test_policy_pack_and_clauses(client: TestClient) -> None:
    packs = client.get("/api/policy-packs")
    assert packs.status_code == 200
    data = packs.json()
    if not data:
        pytest.skip("policy pack not seeded")

    pack = data[0]
    assert pack["is_synthetic"] is True, "the shipped pack must be flagged synthetic"
    assert pack["clause_count"] >= 40

    clauses = client.get(f"/api/policy-packs/{pack['id']}/clauses")
    assert clauses.status_code == 200
    numbers = [c["clause_number"] for c in clauses.json()]
    assert len(numbers) == len(set(numbers))


def test_unknown_policy_pack_returns_envelope(client: TestClient) -> None:
    response = client.get("/api/policy-packs/999999/clauses")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "policy_pack_not_found"


def test_assessment_for_unknown_circular_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/assessments", json={"circular_id": 99999999, "policy_pack_id": 1}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "circular_not_found"


def test_unknown_assessment_returns_envelope(client: TestClient) -> None:
    response = client.get("/api/assessments/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "assessment_not_found"


def test_eval_runs_endpoint(client: TestClient) -> None:
    response = client.get("/api/eval/runs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
