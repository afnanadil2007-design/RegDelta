"""Stage 1 config validation tests: fail-fast, provider-conditional keys."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _base_env(**overrides: str) -> dict[str, str]:
    env = {
        "ANTHROPIC_API_KEY": "sk-test",
        "LLM_PROVIDER": "anthropic",
    }
    env.update(overrides)
    return env


def test_defaults_load_with_provider_key() -> None:
    s = Settings(_env_file=None, **_base_env())
    assert s.embedding_dim == 384
    assert s.rrf_k == 60
    assert s.rerank_top_k == 8
    assert s.sqlalchemy_url.startswith("postgresql+psycopg://")


def test_missing_selected_provider_key_fails_fast() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="")
    assert "ANTHROPIC_API_KEY" in str(exc.value)


def test_groq_selected_requires_only_groq_key() -> None:
    # Selecting groq must not demand the anthropic key.
    s = Settings(_env_file=None, LLM_PROVIDER="groq", GROQ_API_KEY="gsk-x")
    assert s.llm_provider == "groq"
    assert s.groq_base_url.startswith("https://api.groq.com")


def test_missing_groq_key_fails_fast() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, LLM_PROVIDER="groq", GROQ_API_KEY="")
    assert "GROQ_API_KEY" in str(exc.value)


def test_unsupported_provider_is_rejected() -> None:
    # openai/watsonx were removed because the gateway does not implement them.
    with pytest.raises(ValidationError):
        Settings(_env_file=None, LLM_PROVIDER="openai", OPENAI_API_KEY="sk-x")


def test_database_url_override_wins() -> None:
    url = "postgresql+psycopg://u:p@db:5432/x"
    s = Settings(_env_file=None, DATABASE_URL=url, **_base_env())
    assert s.sqlalchemy_url == url
