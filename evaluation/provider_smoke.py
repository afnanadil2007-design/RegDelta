"""One bounded assessment with a real model provider: the smoke check for G02.

    REGDELTA_ALLOW_PAID_CALLS=1 LLM_PROVIDER=groq POSTGRES_DB=regdelta_smoke \\
        python -m evaluation.provider_smoke [--export]

Every automated test uses the deterministic provider. This is the one check
that a real provider works end to end, and it can spend money, so it runs
only when asked for explicitly:

* ``REGDELTA_ALLOW_PAID_CALLS=1`` must be set, the provider must not be
  ``deterministic``, its key must be present (it is never printed), and
  ``POSTGRES_DB`` must be named explicitly (a seeded synthetic database; the
  run is written there);
* the run is capped harder than the defaults: 12 provider calls, 20,000
  tokens, 300 s, one call at a time, 1,024 tokens per answer;
* it assesses the synthetic circular with the fewest obligations against the
  synthetic manual.

It prints the run id, status, provider and model, calls, tokens, the cost
estimate (or why it is unknown) and the quote status of each finding.
``--export`` adds the findings to the semantic-support candidates, where
they are grouped as real-model output. Exit 1 if the run fails.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

LIMITS = {
    "MAX_ASSESSMENT_CALLS": "12",
    "MAX_ASSESSMENT_TOKENS": "20000",
    "ASSESSMENT_TIMEOUT_SECONDS": "300",
    "LLM_MAX_CONCURRENCY": "1",
    "LLM_MAX_TOKENS": "1024",
}


def refusal() -> str | None:
    """Why the smoke run must not start, or None."""
    from app.core.config import get_settings

    if os.environ.get("REGDELTA_ALLOW_PAID_CALLS") != "1":
        return "set REGDELTA_ALLOW_PAID_CALLS=1 to allow calls that may be billed"
    if not os.environ.get("POSTGRES_DB"):
        return "name the database explicitly with POSTGRES_DB (a seeded synthetic one)"
    settings = get_settings()
    if settings.llm_provider == "deterministic":
        return "LLM_PROVIDER is deterministic; set groq or anthropic for a real-provider run"
    ready, reason = settings.provider_readiness()
    return None if ready else reason


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One bounded real-provider assessment.")
    parser.add_argument("--export", action="store_true", help="add findings to support review")
    args = parser.parse_args(argv)

    for name, value in LIMITS.items():
        os.environ[name] = value
    os.environ.setdefault("WARM_MODELS_ON_STARTUP", "false")
    if reason := refusal():
        print(f"REFUSED: {reason}")
        return 2

    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, text

    from app.core.config import get_settings
    from app.main import create_app

    settings = get_settings()
    # psycopg 3 serves synchronous engines from the same URL.
    with create_engine(settings.sqlalchemy_url).connect() as connection:
        row = connection.execute(
            text(
                "SELECT c.id, c.circular_number, count(o.id) FROM circulars c "
                "JOIN obligations o ON o.circular_id = c.id "
                "WHERE c.source_url LIKE 'synthetic://%' GROUP BY c.id "
                "ORDER BY count(o.id), c.id LIMIT 1"
            )
        ).one_or_none()
        pack = connection.execute(
            text("SELECT id FROM policy_packs WHERE is_synthetic ORDER BY id LIMIT 1")
        ).scalar_one_or_none()
    if row is None or pack is None:
        print(f"REFUSED: {settings.postgres_db} has no seeded synthetic circular and manual")
        return 2

    print(f"provider {settings.llm_provider} / {settings.effective_model}; limits {LIMITS}")
    print(f"assessing {row[1]} ({row[2]} obligations) in {settings.postgres_db}")
    client = TestClient(create_app())
    # TestClient runs the background assessment before the POST returns.
    started = client.post("/api/assessments", json={"circular_id": row[0], "policy_pack_id": pack})
    if started.status_code != 202:
        print(f"not started: HTTP {started.status_code} {started.text[:300]}")
        return 1
    run_id = started.json()["run_id"]
    run = client.get(f"/api/assessments/{run_id}").json()
    summary = {
        "run_id": run_id,
        "status": run["status"],
        "status_detail": run.get("status_detail"),
        "provider": run["provider"],
        "usage": run["usage"],
        "failed_tasks": run["failed_tasks"],
        "findings_by_quote_status": dict(Counter(f["quote_status"] for f in run["findings"])),
        "memo_first_line": (run.get("memo") or "").splitlines()[:1],
    }
    print(json.dumps(summary, indent=2))
    if args.export and run["status"] != "FAILED":
        from evaluation.support_review import export

        exported, _replaced, skipped = export([run_id])
        print(f"exported {exported} support-review candidates ({len(skipped)} skipped)")
    return 1 if run["status"] == "FAILED" else 0


if __name__ == "__main__":
    sys.exit(main())
