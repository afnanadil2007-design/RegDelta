"""The real-provider smoke run starts only when every precondition is explicit.

No test here makes, or could make, a provider call: each case stops at a
refusal before the app is built.
"""

from __future__ import annotations

import pytest

from evaluation import provider_smoke


@pytest.mark.parametrize(
    ("env", "reason"),
    [
        ({}, "REGDELTA_ALLOW_PAID_CALLS=1"),
        ({"REGDELTA_ALLOW_PAID_CALLS": "1", "POSTGRES_DB": ""}, "name the database explicitly"),
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
    assert provider_smoke.main([]) == 2
    out = capsys.readouterr().out
    assert out.startswith("REFUSED:") and reason in out
