"""One bounded assessment with a real model provider: the smoke check for G02.

    REGDELTA_ALLOW_PAID_CALLS=1 LLM_PROVIDER=groq POSTGRES_DB=regdelta_demo \\
        python -m evaluation.provider_smoke [--export]

Every automated test uses the deterministic provider. This is the one check
that a real provider works end to end, and it can spend money, so it starts
only when every precondition is explicit, and refuses (exit 2, before any
provider call) otherwise:

* ``REGDELTA_ALLOW_PAID_CALLS=1``; a provider other than ``deterministic``
  whose key is present (it is never printed); ``POSTGRES_DB`` named in the
  environment, and no DATABASE_URL;
* the target (the database ``Settings.database_target()`` resolves, printed
  as user@host:port/name) is one ``ingestion.seed`` built: at this
  checkout's migration head, holding only circulars the synthetic generator
  wrote (``synthetic://regdelta/``), one with obligations, and the seed's
  synthetic manual (by name and version) with every clause embedded. A
  database that merely exists under that name does not pass, nor does the
  test suite's database, whose fixtures are synthetic but not the seed's;
* the run is capped harder than the defaults, and the caps must be the
  settings in effect: 12 provider calls, 20,000 tokens, 300 s, one call at a
  time, 1,024 tokens per judge answer (the memo call allows 4,000);
* nothing else may be using that database: start-up marks unfinished runs
  there as failed.

The fixture is the synthetic circular with the fewest obligations, assessed
against the synthetic manual. Exit 0 means only this: the run reached
COMPLETED and its record checks out.

* It is the run that was started (run id, circular, pack), by the configured
  provider and model, not the deterministic one.
* The provider did real work: at least one call and at most the cap (the
  app's own count), tokens above zero that equal the sum over the steps, and
  at least one judgement with tokens. No step began after the token cap was
  reached, and the run finished within the timeout (30 s allowed for start-up
  and clock skew).
* The fixture's expected behaviour: every finding belongs to the circular, its
  obligations and the manual; every obligation has at least one finding; no
  task failed; and a memo was written. A missing memo is not a pass even when
  the app skips it by design (no finding had located quotes): the memo path
  was then not exercised.

Every other ending has its own name and exit code: FAILED 3 and CAPPED 4
(the run's own status), INCOMPLETE 5 (not finished, an unknown status, or
completed without the output above), MALFORMED 6 (a response that is not the
API's schema), TRANSPORT 7 (an exception or an unexpected HTTP status) and
INVALID 8 (well formed but wrong: another run, another provider, no provider
activity, a limit exceeded). ``--export`` adds the findings to the
semantic-support candidates, where they are grouped as real-model output,
only after a pass; if the export fails the exit is EXPORT_FAILED 9.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from sqlalchemy.engine import URL

    from app.core.config import Settings

LIMITS = {
    "MAX_ASSESSMENT_CALLS": "12",
    "MAX_ASSESSMENT_TOKENS": "20000",
    "ASSESSMENT_TIMEOUT_SECONDS": "300",
    "LLM_MAX_CONCURRENCY": "1",
    "LLM_MAX_TOKENS": "1024",
}
EXIT = {
    "PASSED": 0,
    "REFUSED": 2,
    "FAILED": 3,
    "CAPPED": 4,
    "INCOMPLETE": 5,
    "MALFORMED": 6,
    "TRANSPORT": 7,
    "INVALID": 8,
    "EXPORT_FAILED": 9,
}
TERMINAL = ("COMPLETED", "FAILED", "CAPPED")
START_UP_ALLOWANCE = timedelta(seconds=30)


@dataclass(frozen=True)
class Fixture:
    """What the run assesses, read from the target database before it starts."""

    database: str
    circular_id: int
    circular_number: str
    obligation_ids: frozenset[int]
    policy_pack_id: int
    clause_ids: frozenset[int]


@dataclass
class Outcome:
    name: str
    reason: str
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def code(self) -> int:
        return EXIT[self.name]


class Client(Protocol):
    def post(self, url: str, *, json: Any) -> Any: ...
    def get(self, url: str) -> Any: ...


def refusal() -> str | None:
    """Why the smoke run must not start, or None. Makes no connection."""
    from app.core.config import DatabaseConfigError, get_settings

    if os.environ.get("REGDELTA_ALLOW_PAID_CALLS") != "1":
        return "set REGDELTA_ALLOW_PAID_CALLS=1 to allow calls that may be billed"
    if not os.environ.get("POSTGRES_DB"):
        return "name the database explicitly with POSTGRES_DB (a seeded synthetic one)"
    settings = get_settings()
    try:
        settings.database_target()
    except DatabaseConfigError as exc:
        return str(exc)
    if settings.llm_provider == "deterministic":
        return "LLM_PROVIDER is deterministic; set groq or anthropic for a real-provider run"
    ready, reason = settings.provider_readiness()
    if not ready:
        return reason
    off = [n for n, v in LIMITS.items() if getattr(settings, n.lower()) != int(v)]
    return f"the smoke limits are not in effect: {', '.join(off)}" if off else None


def preflight(url: URL, max_calls: int) -> Fixture | str:
    """The fixture in the database ``url`` names, or why that database is not a target."""
    import psycopg
    from alembic.script import ScriptDirectory

    from app.core.config import describe_database, psycopg_args
    from ingestion.generate_corpus import SOURCE_URL_PREFIX
    from ingestion.prepare_db import BACKEND
    from ingestion.seed import PACK_NAME, PACK_VERSION

    name = describe_database(url)
    head = ScriptDirectory(str(BACKEND / "alembic")).get_current_head()
    try:
        connection = psycopg.connect(**psycopg_args(url), connect_timeout=10)
    except psycopg.Error as exc:
        return f"cannot connect to {name} ({type(exc).__name__})"
    with connection:
        if not connection.execute("SELECT to_regclass('alembic_version') IS NOT NULL").fetchone()[
            0
        ]:
            return f"{name} has no RegDelta migration history"
        revisions = {r[0] for r in connection.execute("SELECT version_num FROM alembic_version")}
        if revisions != {head}:
            return f"{name} is at revision {', '.join(sorted(revisions)) or 'none'}, not {head}"
        outside = connection.execute(
            "SELECT count(*) FROM circulars WHERE NOT starts_with(coalesce(source_url, ''), %s)",
            (SOURCE_URL_PREFIX,),
        ).fetchone()[0]
        if outside:
            return f"{name} holds {outside} circular(s) that the synthetic seed did not write"
        # Every circular is the seed's now; pick the one with the fewest obligations.
        row = connection.execute(
            "SELECT c.id, c.circular_number, array_agg(o.id ORDER BY o.id) FROM circulars c"
            " JOIN obligations o ON o.circular_id = c.id"
            " GROUP BY c.id ORDER BY count(o.id), c.id LIMIT 1"
        ).fetchone()
        if row is None:
            return f"{name} holds no synthetic circular with extracted obligations"
        pack = connection.execute(
            "SELECT id FROM policy_packs WHERE is_synthetic AND name = %s AND version = %s"
            " ORDER BY id LIMIT 1",
            (PACK_NAME, PACK_VERSION),
        ).fetchone()
        if pack is None:
            return f"{name} holds no seeded synthetic manual ({PACK_NAME} {PACK_VERSION})"
        clauses = connection.execute(
            "SELECT id, embedding IS NOT NULL FROM policy_clauses WHERE policy_pack_id = %s",
            (pack[0],),
        ).fetchall()
    if not clauses or not all(embedded for _, embedded in clauses):
        return f"{name}: the synthetic manual has no clauses, or its seed did not finish"
    obligations = frozenset(row[2])
    if len(obligations) + 1 > max_calls:
        return (
            f"{row[1]} has {len(obligations)} obligations: one call each plus the memo "
            f"exceeds the {max_calls}-call cap"
        )
    return Fixture(
        database=name,
        circular_id=row[0],
        circular_number=row[1],
        obligation_ids=obligations,
        policy_pack_id=pack[0],
        clause_ids=frozenset(c for c, _ in clauses),
    )


def _http(client: Client, method: str, path: str, expected: int, **kwargs: Any) -> Any:
    """The response, or an Outcome when the call raised or answered another status."""
    try:
        response = getattr(client, method)(path, **kwargs)
    except Exception as exc:  # noqa: BLE001 - every failure to get an answer is TRANSPORT
        return Outcome("TRANSPORT", f"{method.upper()} {path} raised {type(exc).__name__}")
    if response.status_code != expected:
        try:
            code = response.json()["error"]["code"]
        except Exception:  # noqa: BLE001 - an error body is optional
            code = "no API error code"
        return Outcome(
            "TRANSPORT", f"{method.upper()} {path} answered HTTP {response.status_code} ({code})"
        )
    return response


def run(client: Client, fixture: Fixture, settings: Settings, calls: list[int]) -> Outcome:
    """Start the fixture's assessment and decide what its record shows.

    ``calls`` holds the provider-call count the app reported for each run it
    finished in this process (its ``assessment.finished`` log record).
    """
    from pydantic import TypeAdapter, ValidationError

    from app.routers.schemas import AgentStepOut, AssessmentDetail, CreateAssessmentResponse

    started = _http(
        client,
        "post",
        "/api/assessments",
        202,
        json={"circular_id": fixture.circular_id, "policy_pack_id": fixture.policy_pack_id},
    )
    if isinstance(started, Outcome):
        return started
    try:
        run_id = CreateAssessmentResponse.model_validate_json(started.content).run_id
    except ValidationError:
        return Outcome("MALFORMED", "the start response is not {run_id}")

    answer = _http(client, "get", f"/api/assessments/{run_id}", 200)
    if isinstance(answer, Outcome):
        return answer
    try:
        raw = json.loads(answer.content)
    except ValueError:
        return Outcome("MALFORMED", "the run record is not JSON")
    status = raw.get("status") if isinstance(raw, dict) else None
    if not isinstance(status, str):
        return Outcome("MALFORMED", "the run record has no status")
    if status not in TERMINAL:
        return Outcome("INCOMPLETE", f"the run is {status}, not finished", {"run_id": str(run_id)})
    try:
        detail = AssessmentDetail.model_validate(raw)
    except ValidationError as exc:
        return Outcome(
            "MALFORMED",
            f"the run record does not match the API schema ({exc.error_count()} errors)",
        )

    summary = _summary(detail, calls)
    if (detail.run_id, detail.circular_id, detail.policy_pack_id) != (
        run_id,
        fixture.circular_id,
        fixture.policy_pack_id,
    ):
        return Outcome("INVALID", "the record is not the run that was started", summary)
    provider = detail.provider
    if provider is None or (provider.name, provider.model, provider.deterministic) != (
        settings.llm_provider,
        settings.effective_model,
        False,
    ):
        return Outcome(
            "INVALID",
            f"the run used {provider.name if provider else 'no provider'}, "
            f"not {settings.llm_provider} / {settings.effective_model}",
            summary,
        )
    if status != "COMPLETED":
        return Outcome(status, detail.status_detail or "no detail recorded", summary)

    answer = _http(client, "get", f"/api/assessments/{run_id}/steps", 200)
    if isinstance(answer, Outcome):
        answer.summary = summary
        return answer
    try:
        steps = TypeAdapter(list[AgentStepOut]).validate_json(answer.content)
    except ValidationError:
        return Outcome("MALFORMED", "the steps do not match the API schema", summary)

    if problem := _activity_problem(detail, steps, calls, settings):
        return Outcome("INVALID", problem, summary)
    if problem := _fixture_problem(detail, fixture):
        return Outcome(*problem, summary)
    return Outcome("PASSED", "completed within the limits, with findings and a memo", summary)


def _summary(detail: Any, calls: list[int]) -> dict[str, Any]:
    return {
        "run_id": str(detail.run_id),
        "status": detail.status.value,
        "status_detail": detail.status_detail,
        "provider": detail.provider.model_dump() if detail.provider else None,
        "calls": calls[-1] if calls else None,
        "usage": detail.usage.model_dump(),
        "failed_tasks": detail.failed_tasks,
        "findings_by_quote_status": dict(Counter(f.quote_status.value for f in detail.findings)),
        "memo_first_line": (detail.memo or "").splitlines()[:1],
    }


def _activity_problem(
    detail: Any, steps: list[Any], calls: list[int], settings: Settings
) -> str | None:
    if len(calls) != 1:
        return f"the app reported {len(calls)} finished runs in this process, not one"
    if not 1 <= calls[0] <= settings.max_assessment_calls:
        return f"{calls[0]} provider calls, outside 1..{settings.max_assessment_calls}"
    total = detail.usage.total_tokens
    if total <= 0 or sum(s.tokens for s in steps) != total:
        return f"run tokens {total} are not positive or differ from the steps' sum"
    if not any(s.node == "judge_impact" and s.tokens > 0 for s in steps):
        return "no judgement reached the provider"
    if any(s.finished_at is None for s in steps):
        return "a step never finished"
    spent = 0
    for step in sorted(steps, key=lambda s: s.seq):
        if step.tokens and spent >= settings.max_assessment_tokens:
            return f"step {step.seq} called the provider after the token cap was reached"
        spent += step.tokens
    limit = timedelta(seconds=settings.assessment_timeout_seconds) + START_UP_ALLOWANCE
    if detail.completed_at is None or detail.completed_at - detail.created_at > limit:
        return "the run did not finish within the timeout"
    return None


def _fixture_problem(detail: Any, fixture: Fixture) -> tuple[str, str] | None:
    """(outcome, reason) when the run's output is not what the fixture expects."""
    for f in detail.findings:
        if (
            f.circular_id != fixture.circular_id
            or f.obligation_id not in fixture.obligation_ids
            or (f.policy_clause_id is not None and f.policy_clause_id not in fixture.clause_ids)
        ):
            return "INVALID", f"finding {f.id} is not about the fixture's circular and manual"
    if detail.obligation_count != len(fixture.obligation_ids):
        return "INVALID", f"the run planned {detail.obligation_count} obligations, not " + str(
            len(fixture.obligation_ids)
        )
    unanswered = fixture.obligation_ids - {f.obligation_id for f in detail.findings}
    if unanswered:
        total = len(fixture.obligation_ids)
        return "INCOMPLETE", f"{len(unanswered)} of {total} obligations have no finding"
    if detail.failed_tasks:
        return "INCOMPLETE", f"{detail.failed_tasks} task(s) failed"
    if not (detail.memo or "").strip():
        return "INCOMPLETE", f"no memo was written ({detail.status_detail or 'no note'})"
    return None


def export_run(run_id: str) -> Outcome | str:
    """Add a passed run's findings to the support candidates; a line to print, or a failure."""
    from evaluation.support_review import export

    try:
        exported, replaced, skipped = export([run_id])
    except (Exception, SystemExit) as exc:  # export raises SystemExit on a damaged file
        return Outcome("EXPORT_FAILED", f"the export raised {type(exc).__name__}: {exc}")
    return (
        f"exported {exported} support-review candidates "
        f"({replaced} replaced, {len(skipped)} skipped)"
    )


@contextmanager
def finished_calls() -> Iterator[list[int]]:
    """Collect the provider-call count of every run the app finishes meanwhile."""
    calls: list[int] = []

    class Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.getMessage() == "assessment.finished":
                calls.append(int(getattr(record, "calls", -1)))

    logger = logging.getLogger("app.services.assessment")
    handler, level = Collect(logging.INFO), logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield calls
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)


def _redact(text: str, settings: Settings | None) -> str:
    """Nothing printed holds a key or the database password, should one appear."""
    if settings is None:
        return text
    from app.core.config import describe_database

    keys = (settings.groq_api_key, settings.anthropic_api_key)
    secrets = [k.get_secret_value() for k in keys if k is not None]
    password = settings.postgres_password.get_secret_value()
    # A password that is also part of the printed target (the default
    # "regdelta") would only garble the output.
    if password not in describe_database(settings.database_target()):
        secrets.append(password)
    for secret in secrets:
        if len(secret) >= 4:
            text = text.replace(secret, "***")
    return text


def report(outcome: Outcome, settings: Settings | None) -> int:
    if outcome.summary:
        print(_redact(json.dumps(outcome.summary, indent=2), settings))
    print(_redact(f"SMOKE {outcome.name}: {outcome.reason}", settings))
    return outcome.code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One bounded real-provider assessment.")
    parser.add_argument("--export", action="store_true", help="add findings to support review")
    args = parser.parse_args(argv)

    for name, value in LIMITS.items():
        os.environ[name] = value
    os.environ.setdefault("WARM_MODELS_ON_STARTUP", "false")
    # The run, its checks and the export use separate event loops.
    os.environ["DATABASE_POOL"] = "null"
    from app.core.config import get_settings

    get_settings.cache_clear()
    if reason := refusal():
        return report(Outcome("REFUSED", reason), None)
    settings = get_settings()
    fixture = preflight(settings.database_target(), settings.max_assessment_calls)
    if isinstance(fixture, str):
        return report(Outcome("REFUSED", fixture), settings)

    from fastapi.testclient import TestClient

    from app.main import create_app

    print(f"target {fixture.database}")
    print(f"provider {settings.llm_provider} / {settings.effective_model}; limits {LIMITS}")
    print(f"assessing {fixture.circular_number} ({len(fixture.obligation_ids)} obligations)")
    # TestClient runs the background assessment before the POST returns; as a
    # context manager it also runs the app's start-up and shutdown.
    with finished_calls() as calls, TestClient(create_app()) as client:
        outcome = run(client, fixture, settings, calls)
    if outcome.name == "PASSED" and args.export:
        exported = export_run(outcome.summary["run_id"])
        if isinstance(exported, Outcome):
            exported.summary = outcome.summary
            return report(exported, settings)
        print(exported)
    return report(outcome, settings)


if __name__ == "__main__":
    sys.exit(main())
