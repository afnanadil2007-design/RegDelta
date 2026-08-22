"""Stage 1 health endpoint test.

The endpoint reports ``database: down`` gracefully when no DB is reachable,
so this runs without Postgres. It proves the app assembles and routes.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_ok_without_database() -> None:
    client = TestClient(create_app())
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["env"] == "development"
    assert body["database"] in {"up", "down"}


def test_unknown_route_is_404() -> None:
    client = TestClient(create_app())
    assert client.get("/api/does-not-exist").status_code == 404
