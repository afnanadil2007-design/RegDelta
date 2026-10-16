"""The real-provider smoke run: when it starts, and what counts as a pass.

No test here makes, or could make, a provider call. The refusal and preflight
tests stop before the app is built; the outcome tests drive ``run`` with a
fake HTTP client that answers as the API would, so every ending (a valid
completed run, FAILED, CAPPED, unfinished, another run or provider, malformed
answers, HTTP failures, no provider activity, a failed export) is checked
without a network.
"""

from __future__ import annotations

import logging
import socket
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from psycopg import sql

from app.core.config import Settings, describe_database, get_settings
from evaluation import provider_smoke
from evaluation.provider_smoke import EXIT, Fixture, Outcome
from tests.test_database_guards import _admin, _drop, _run, _scratch_name, _sql


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any socket to a non-loopback address fails the test (libpq's are local)."""
    connect = socket.socket.connect

    def local_only(self: socket.socket, address: Any) -> None:
        host = address[0] if isinstance(address, tuple) else "unix"
        if host not in ("unix", "127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"network call to {address}")
        connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", local_only)


# --- refusals ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("env", "reason"),
    [
        ({}, "REGDELTA_ALLOW_PAID_CALLS=1"),
        ({"REGDELTA_ALLOW_PAID_CALLS": "1", "POSTGRES_DB": ""}, "name the database explicitly"),
        (
            {
                "REGDELTA_ALLOW_PAID_CALLS": "1",
                "POSTGRES_DB": "regdelta_demo",
                "DATABASE_URL": "postgresql+psycopg://u:Secret-1@h/regdelta_demo",
            },
            "DATABASE_URL is set (value not shown)",
        ),
        (
            {"REGDELTA_ALLOW_PAID_CALLS": "1", "POSTGRES_DB": "regdelta_demo"},
            "LLM_PROVIDER is deterministic",
        ),
        (
            {
                "REGDELTA_ALLOW_PAID_CALLS": "1",
                "POSTGRES_DB": "regdelta_demo",
                "LLM_PROVIDER": "groq",
                "GROQ_API_KEY": "",
            },
            "needs GROQ_API_KEY",
        ),
    ],
)
def test_the_smoke_run_refuses_without_explicit_preconditions(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], env: dict, reason: str
) -> None:
    monkeypatch.delenv("REGDELTA_ALLOW_PAID_CALLS", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "deterministic")
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert provider_smoke.main([]) == EXIT["REFUSED"]
    out = capsys.readouterr().out
    assert out.startswith("SMOKE REFUSED:") and reason in out
    assert "Secret-1" not in out


def test_the_smoke_limits_must_be_in_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in provider_smoke.LIMITS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("MAX_ASSESSMENT_CALLS", "300")
    _ready_provider(monkeypatch)
    assert provider_smoke.refusal() == "the smoke limits are not in effect: MAX_ASSESSMENT_CALLS"


def _ready_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGDELTA_ALLOW_PAID_CALLS", "1")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-placeholder-never-sent")


# --- preflight: the target must be the seeded synthetic database -------------------------


@pytest.fixture
def migrated_scratch() -> Iterator[str]:
    name = _scratch_name()
    result = _run("ingestion.prepare_db", name)
    if result.returncode != 0:
        _drop(name)
        pytest.skip(f"cannot prepare a scratch database: {result.stdout[-300:]}")
    yield name
    _drop(name)


SEED = (
    "INSERT INTO circulars (id, circular_number, title, doc_type, source_url, full_text,"
    " page_count, vision_page_count) VALUES (1, 'SEBI/HO/SYN/1', 't', 'circular',"
    " 'synthetic://regdelta/1.pdf', 'Brokers shall report margin by T+1 day.', 1, 0)",
    "INSERT INTO paragraphs (id, circular_id, order_index, text, char_start, char_end,"
    " extraction_method) VALUES (1, 1, 0, 'Brokers shall report margin by T+1 day.', 0, 39,"
    " 'text')",
    "INSERT INTO obligations (id, circular_id, paragraph_id, text, char_start, char_end)"
    " VALUES (7, 1, 1, 'Brokers shall report margin by T+1 day.', 0, 39)",
    "INSERT INTO policy_packs (id, name, version, is_synthetic) VALUES (3, 'Manual', '1', true)",
    "INSERT INTO policy_clauses (id, policy_pack_id, order_index, clause_number, text,"
    " char_start, char_end, embedding) VALUES (5, 3, 0, 'C.3', 'Report by T+2 days.', 0, 19,"
    " array_fill(0, ARRAY[384])::vector)",
)


def _target(database: str) -> Any:
    return get_settings().database_target().set(database=database)


def test_preflight_names_the_seeded_synthetic_database_it_will_use(migrated_scratch: str) -> None:
    _sql(migrated_scratch, *SEED)
    fixture = provider_smoke.preflight(_target(migrated_scratch), 12)
    assert fixture == Fixture(
        database=describe_database(_target(migrated_scratch)),
        circular_id=1,
        circular_number="SEBI/HO/SYN/1",
        obligation_ids=frozenset({7}),
        policy_pack_id=3,
        clause_ids=frozenset({5}),
    )
    assert fixture.database.endswith(f"/{migrated_scratch}")


@pytest.mark.parametrize(
    ("statements", "reason"),
    [
        ((), "holds no synthetic circular with extracted obligations"),
        (
            (
                *SEED,
                "INSERT INTO circulars (id, circular_number, title, doc_type, source_url,"
                " full_text, page_count, vision_page_count) VALUES (2, 'SEBI/HO/REAL/1', 't',"
                " 'circular',"
                " 'https://www.sebi.gov.in/1.html', 'x', 1, 0)",
            ),
            "1 circular(s) that are not from the synthetic corpus",
        ),
        ((*SEED, "UPDATE policy_clauses SET embedding = NULL"), "its seed did not finish"),
        ((*SEED[:3],), "holds no synthetic policy pack"),
        (
            (*SEED, "UPDATE alembic_version SET version_num = '0003_agent_run_seq'"),
            "is at revision 0003_agent_run_seq",
        ),
    ],
)
def test_preflight_refuses_a_database_that_is_not_the_seeded_target(
    migrated_scratch: str, statements: tuple[str, ...], reason: str
) -> None:
    if statements:
        _sql(migrated_scratch, *statements)
    refused = provider_smoke.preflight(_target(migrated_scratch), 12)
    assert isinstance(refused, str) and reason in refused
    assert migrated_scratch in refused


def test_preflight_refuses_a_database_that_is_not_regdelta() -> None:
    name = _scratch_name()
    _admin(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        _sql(name, "CREATE TABLE orders (id integer)")
        refused = provider_smoke.preflight(_target(name), 12)
    finally:
        _drop(name)
    assert refused == f"{describe_database(_target(name))} has no RegDelta migration history"


def test_an_unrelated_postgres_db_cannot_satisfy_the_smoke_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], migrated_scratch: str
) -> None:
    """Every precondition but the target holds; the app is never built."""
    _ready_provider(monkeypatch)
    monkeypatch.setenv("POSTGRES_DB", migrated_scratch)
    monkeypatch.setattr("app.main.create_app", _never_called)
    assert provider_smoke.main([]) == EXIT["REFUSED"]
    out = capsys.readouterr().out
    assert f"/{migrated_scratch} holds no synthetic circular" in out
    assert "gsk-placeholder-never-sent" not in out


def _never_called(*_: object, **__: object) -> None:
    raise AssertionError("the app must not be built for a refused smoke run")


# --- outcomes ------------------------------------------------------------------------------

RUN_ID = uuid.UUID("11111111-2222-4333-8444-555555555555")
FIXTURE = Fixture(
    database="regdelta@localhost:5432/regdelta_demo",
    circular_id=1,
    circular_number="SEBI/HO/SYN/1",
    obligation_ids=frozenset({7, 8}),
    policy_pack_id=3,
    clause_ids=frozenset({5, 6}),
)
CREATED = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)


def _settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        llm_provider="groq",
        llm_model="openai/gpt-oss-20b",
        groq_api_key="gsk-placeholder-never-sent",
        max_assessment_calls=12,
        max_assessment_tokens=20_000,
        assessment_timeout_seconds=300,
    )


def _finding(id_: int, obligation_id: int, clause_id: int | None = 5) -> dict[str, Any]:
    return {
        "id": id_,
        "circular_id": 1,
        "obligation_id": obligation_id,
        "obligation_text": "Brokers shall report margin by T+1 day.",
        "obligation_char_start": 0,
        "obligation_char_end": 39,
        "policy_clause_id": clause_id,
        "clause_number": "C.3" if clause_id else None,
        "clause_heading": None,
        "clause_text": "Report by T+2 days." if clause_id else None,
        "clause_char_start": 0 if clause_id else None,
        "impact_type": "MODIFIED" if clause_id else "NO_MATCH",
        "rationale": "T+1 is stricter than T+2.",
        "model_confidence": 0.8,
        "circular_span_start": 0,
        "circular_span_end": 39,
        "clause_span_start": 0,
        "clause_span_end": 19,
        "quote_status": "VERIFIED" if clause_id else "NOT_APPLICABLE",
        "verification_note": None,
        "unlocated_quote": None,
        "verification_attempts": 1,
        "analyst_decision": "PENDING",
        "decided_at": None,
    }


def _detail(**overrides: Any) -> dict[str, Any]:
    detail = {
        "id": 1,
        "run_id": str(RUN_ID),
        "circular_id": 1,
        "circular_number": "SEBI/HO/SYN/1",
        "circular_title": "t",
        "policy_pack_id": 3,
        "policy_pack_name": "Manual",
        "policy_pack_version": "1",
        "as_of": None,
        "status": "COMPLETED",
        "status_detail": None,
        "provider": {"name": "groq", "model": "openai/gpt-oss-20b", "deterministic": False},
        "graph_version": "v1",
        "usage": {
            "total_tokens": 3000,
            "estimated_cost_usd": 0.001,
            "cost_complete": True,
            "unpriced_calls": 0,
        },
        "failed_tasks": 0,
        "obligation_count": 2,
        "counts": {
            "total": 2,
            "assessed_obligations": 2,
            "quote_verified": 1,
            "quote_failed": 0,
            "quote_not_applicable": 1,
            "by_impact": {"MODIFIED": 1, "NO_MATCH": 1},
            "decision_pending": 2,
            "decision_accepted": 0,
            "decision_rejected": 0,
        },
        "created_at": CREATED.isoformat(),
        "completed_at": (CREATED + timedelta(seconds=90)).isoformat(),
        "memo": "Margin reporting moves from T+2 to T+1.",
        "findings": [_finding(1, 7), _finding(2, 8, None)],
    }
    detail.update(overrides)
    return detail


def _step(seq: int, node: str, tokens: int = 0) -> dict[str, Any]:
    return {
        "seq": seq,
        "node": node,
        "status": "OK",
        "summary": None,
        "tokens": tokens,
        "cost_usd": 0.0,
        "latency_ms": 10,
        "error": None,
        "obligation_id": None,
        "clause_number": None,
        "attempt": None,
        "started_at": CREATED.isoformat(),
        "finished_at": CREATED.isoformat(),
    }


STEPS = [
    _step(1, "plan_assessment"),
    _step(2, "retrieve_clauses"),
    _step(3, "judge_impact", 1800),
    _step(4, "verify_grounding"),
    _step(5, "synthesize_memo", 1200),
]


class FakeClient:
    """Answers the three requests the smoke run makes; never opens a socket."""

    def __init__(self, **answers: Any) -> None:
        self.answers = {
            "post": httpx.Response(202, json={"run_id": str(RUN_ID)}),
            "detail": httpx.Response(200, json=_detail()),
            "steps": httpx.Response(200, json=STEPS),
            **answers,
        }

    def _answer(self, key: str) -> Any:
        answer = self.answers[key]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def post(self, url: str, *, json: Any) -> Any:
        assert (url, json) == ("/api/assessments", {"circular_id": 1, "policy_pack_id": 3})
        return self._answer("post")

    def get(self, url: str) -> Any:
        return self._answer("steps" if url.endswith("/steps") else "detail")


def _outcome(calls: list[int] | None = None, **answers: Any) -> Outcome:
    return provider_smoke.run(FakeClient(**answers), FIXTURE, _settings(), calls or [5])


def _with(**overrides: Any) -> httpx.Response:
    return httpx.Response(200, json=_detail(**overrides))


def test_a_valid_completed_run_passes() -> None:
    outcome = _outcome()
    assert (outcome.name, outcome.code) == ("PASSED", 0)
    assert outcome.summary["calls"] == 5 and outcome.summary["run_id"] == str(RUN_ID)


@pytest.mark.parametrize(
    ("answers", "calls", "name", "reason"),
    [
        ({"detail": _with(status="FAILED", status_detail="gateway: 401")}, None, "FAILED", "401"),
        ({"detail": _with(status="CAPPED", status_detail="Call budget")}, None, "CAPPED", "budget"),
        ({"detail": _with(status="RUNNING")}, None, "INCOMPLETE", "RUNNING, not finished"),
        ({"detail": _with(status="PAUSED")}, None, "INCOMPLETE", "PAUSED, not finished"),
        ({"detail": _with(run_id=str(uuid.uuid4()))}, None, "INVALID", "not the run"),
        ({"detail": _with(circular_id=2)}, None, "INVALID", "not the run"),
        (
            {
                "detail": _with(
                    provider={"name": "deterministic", "model": "x", "deterministic": True}
                )
            },
            None,
            "INVALID",
            "used deterministic",
        ),
        (
            {"detail": _with(provider={"name": "groq", "model": "other", "deterministic": False})},
            None,
            "INVALID",
            "not groq / openai/gpt-oss-20b",
        ),
        ({"post": httpx.Response(202, content=b"{}")}, None, "MALFORMED", "start response"),
        ({"detail": httpx.Response(200, content=b"<html>")}, None, "MALFORMED", "not JSON"),
        ({"detail": httpx.Response(200, json=[1])}, None, "MALFORMED", "no status"),
        ({"detail": _with(usage=None)}, None, "MALFORMED", "API schema"),
        ({"steps": httpx.Response(200, json=[{"seq": 1}])}, None, "MALFORMED", "steps"),
        (
            {"post": httpx.Response(503, json={"error": {"code": "provider_unavailable"}})},
            None,
            "TRANSPORT",
            "HTTP 503 (provider_unavailable)",
        ),
        ({"detail": httpx.Response(500, content=b"")}, None, "TRANSPORT", "HTTP 500"),
        ({"post": httpx.ConnectError("refused")}, None, "TRANSPORT", "raised ConnectError"),
        ({"steps": httpx.ReadTimeout("slow")}, None, "TRANSPORT", "raised ReadTimeout"),
        ({}, [0], "INVALID", "0 provider calls"),
        ({}, [13], "INVALID", "13 provider calls, outside 1..12"),
        ({}, [], "INVALID", "reported 0 finished runs"),
        (
            {"steps": httpx.Response(200, json=[_step(1, "synthesize_memo", 3000)])},
            None,
            "INVALID",
            "no judgement reached the provider",
        ),
        (
            {
                "detail": _with(usage={**_detail()["usage"], "total_tokens": 0}),
                "steps": httpx.Response(200, json=[_step(1, "judge_impact")]),
            },
            None,
            "INVALID",
            "not positive",
        ),
        (
            {"detail": _with(usage={**_detail()["usage"], "total_tokens": 2999})},
            None,
            "INVALID",
            "differ from the steps' sum",
        ),
        (
            {
                "detail": _with(usage={**_detail()["usage"], "total_tokens": 21_000}),
                "steps": httpx.Response(
                    200, json=[_step(1, "judge_impact", 20_000), _step(2, "judge_impact", 1000)]
                ),
            },
            None,
            "INVALID",
            "step 2 called the provider after the token cap",
        ),
        (
            {"detail": _with(completed_at=(CREATED + timedelta(seconds=400)).isoformat())},
            None,
            "INVALID",
            "within the timeout",
        ),
        ({"detail": _with(failed_tasks=1)}, None, "INCOMPLETE", "1 task(s) failed"),
        (
            {"detail": _with(memo=None, status_detail="No finding had its quotes located")},
            None,
            "INCOMPLETE",
            "no memo was written (No finding had its quotes located)",
        ),
        ({"detail": _with(findings=[_finding(1, 7)])}, None, "INCOMPLETE", "1 of 2 obligations"),
        ({"detail": _with(findings=[])}, None, "INCOMPLETE", "2 of 2 obligations"),
        (
            {"detail": _with(findings=[_finding(1, 7), _finding(2, 99)])},
            None,
            "INVALID",
            "finding 2 is not about the fixture",
        ),
        (
            {"detail": _with(findings=[_finding(1, 7), _finding(2, 8, clause_id=42)])},
            None,
            "INVALID",
            "finding 2 is not about the fixture",
        ),
    ],
)
def test_every_other_ending_is_reported_under_its_own_name(
    answers: dict, calls: list[int] | None, name: str, reason: str
) -> None:
    outcome = provider_smoke.run(
        FakeClient(**answers), FIXTURE, _settings(), [5] if calls is None else calls
    )
    assert (outcome.name, outcome.code) == (name, EXIT[name]), outcome.reason
    assert outcome.code != 0
    assert reason in outcome.reason


def test_the_exit_codes_are_distinct() -> None:
    assert len(set(EXIT.values())) == len(EXIT) and EXIT["PASSED"] == 0


def test_the_app_reports_its_call_count_even_when_logging_is_quieter() -> None:
    logger = logging.getLogger("app.services.assessment")
    previous = logger.level
    logger.setLevel(logging.WARNING)
    try:
        with provider_smoke.finished_calls() as calls:
            logger.info("assessment.finished", extra={"calls": 4, "status": "COMPLETED"})
            logger.info("assessment.started")
        logger.info("assessment.finished", extra={"calls": 9})
        assert calls == [4]
        assert logger.level == logging.WARNING
    finally:
        logger.setLevel(previous)


# --- main: the client lifecycle and the export ------------------------------------------


class RecordingClient:
    entered = exited = False

    def __init__(self, app: object) -> None:
        self.app = app

    def __enter__(self) -> RecordingClient:
        RecordingClient.entered = True
        return self

    def __exit__(self, *_: object) -> None:
        RecordingClient.exited = True


@pytest.fixture
def stubbed_main(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """main() with the preconditions met and the run decided by ``outcome``."""
    exports: list[str] = []
    RecordingClient.entered = RecordingClient.exited = False
    monkeypatch.setattr(provider_smoke, "refusal", lambda: None)
    monkeypatch.setattr(provider_smoke, "preflight", lambda *_: FIXTURE)
    monkeypatch.setattr("fastapi.testclient.TestClient", RecordingClient)
    monkeypatch.setattr("app.main.create_app", lambda: object())
    yield exports


def _decide(monkeypatch: pytest.MonkeyPatch, outcome: Outcome) -> None:
    def run(client: Any, *_: object) -> Outcome:
        assert RecordingClient.entered and not RecordingClient.exited
        return outcome

    monkeypatch.setattr(provider_smoke, "run", run)


def test_export_follows_a_pass_and_its_failure_is_not_a_pass(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], stubbed_main: list[str]
) -> None:
    _decide(monkeypatch, Outcome("PASSED", "ok", {"run_id": str(RUN_ID)}))

    def broken_export(run_ids: list[str]) -> None:
        raise SystemExit("the candidates file is damaged")

    monkeypatch.setattr("evaluation.support_review.export", broken_export)
    assert provider_smoke.main(["--export"]) == EXIT["EXPORT_FAILED"]
    out = capsys.readouterr().out
    assert "SMOKE EXPORT_FAILED: the export raised SystemExit" in out
    assert "SMOKE PASSED" not in out
    assert RecordingClient.exited


def test_a_passing_run_is_exported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], stubbed_main: list[str]
) -> None:
    _decide(monkeypatch, Outcome("PASSED", "ok", {"run_id": str(RUN_ID)}))
    monkeypatch.setattr(
        "evaluation.support_review.export",
        lambda run_ids: stubbed_main.extend(run_ids) or (2, 0, []),
    )
    assert provider_smoke.main(["--export"]) == 0
    assert stubbed_main == [str(RUN_ID)]
    out = capsys.readouterr().out
    assert "exported 2 support-review candidates" in out and "SMOKE PASSED" in out


@pytest.mark.parametrize("name", ["CAPPED", "INCOMPLETE", "INVALID"])
def test_nothing_is_exported_from_a_run_that_did_not_pass(
    monkeypatch: pytest.MonkeyPatch, stubbed_main: list[str], name: str
) -> None:
    _decide(monkeypatch, Outcome(name, "no", {"run_id": str(RUN_ID)}))
    monkeypatch.setattr(
        "evaluation.support_review.export", lambda run_ids: stubbed_main.extend(run_ids)
    )
    assert provider_smoke.main(["--export"]) == EXIT[name]
    assert stubbed_main == []


def test_printed_output_never_holds_a_secret(capsys: pytest.CaptureFixture[str]) -> None:
    settings = _settings()
    provider_smoke.report(
        Outcome("TRANSPORT", "upstream said gsk-placeholder-never-sent", {"k": "regdelta"}),
        settings,
    )
    out = capsys.readouterr().out
    assert "gsk-placeholder-never-sent" not in out and "***" in out
