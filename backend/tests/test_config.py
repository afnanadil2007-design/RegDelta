"""Configuration: provider readiness, secret handling, and validated knobs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import DETERMINISTIC_MODEL, Settings


def _settings(**overrides: object) -> Settings:
    # _env_file=None isolates the test from a developer's .env.
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_deterministic_provider_is_ready_without_any_key() -> None:
    settings = _settings(llm_provider="deterministic")
    assert settings.provider_readiness() == (True, None)
    assert settings.effective_model == DETERMINISTIC_MODEL


@pytest.mark.parametrize(
    ("provider", "variable"), [("groq", "GROQ_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY")]
)
def test_missing_key_is_reported_not_raised(provider: str, variable: str) -> None:
    """The app still starts; assessments report the missing variable by name."""
    settings = _settings(llm_provider=provider, groq_api_key=None, anthropic_api_key=None)
    ready, reason = settings.provider_readiness()
    assert ready is False
    assert reason is not None and variable in reason


def test_blank_key_counts_as_missing() -> None:
    ready, _ = _settings(llm_provider="groq", groq_api_key="   ").provider_readiness()
    assert ready is False


def test_key_for_the_selected_provider_is_enough() -> None:
    settings = _settings(llm_provider="groq", groq_api_key="gsk-test-placeholder")
    assert settings.provider_readiness() == (True, None)
    assert settings.effective_model == settings.llm_model


def test_keys_never_appear_in_reprs() -> None:
    settings = _settings(llm_provider="groq", groq_api_key="gsk-should-not-leak")
    assert "gsk-should-not-leak" not in repr(settings)
    assert "gsk-should-not-leak" not in str(settings.model_dump())


def test_unsupported_provider_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _settings(llm_provider="openai")


@pytest.mark.parametrize(
    "overrides",
    [
        {"relevance_threshold": 1.5},
        {"llm_max_concurrency": 0},
        {"max_assessment_calls": 0},
        {"retrieve_top_n": 0},
    ],
)
def test_out_of_range_limits_fail_at_startup(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        _settings(**overrides)


def test_api_binds_to_loopback_by_default() -> None:
    """No auth plus metered model calls: never listen on every interface by default."""
    assert _settings().api_host == "127.0.0.1"


def test_database_url_override_wins() -> None:
    url = "postgresql+psycopg://u:p@db.example:5432/x_test"
    assert _settings(database_url=url).sqlalchemy_url == url
