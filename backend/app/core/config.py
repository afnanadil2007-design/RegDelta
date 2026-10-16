"""Application configuration.

Every environment variable is declared and validated here; a malformed value
fails at startup with a message naming it. A *missing provider key* is not a
startup error: browsing, search, and point-in-time queries need no key, so the
app starts and reports the assessment provider as unavailable instead (see
``provider_readiness``).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

# "deterministic" is a rule-based stand-in behind the same gateway interface:
# no network, no key, no cost, same output for the same input. It exists for
# the synthetic demo and the test suite, and is labelled as such in the UI.
Provider = Literal["deterministic", "groq", "anthropic"]

# Recorded as the run's model when the deterministic provider is selected.
DETERMINISTIC_MODEL = "regdelta-rules-v1"

# There is one .env, at the repo root. Commands run from either the root or
# backend/ (`make migrate` does `cd backend`), so both locations are searched.
# Later entries win, so a backend-local override is still possible.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILES = (_REPO_ROOT / ".env", Path(".env"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---
    env: Literal["development", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Loopback by default: the API has no authentication and can spend money on
    # model calls, so it is a local tool. The container sets 0.0.0.0 itself.
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    # --- Database ---
    postgres_user: str = "regdelta"
    postgres_password: str = "regdelta"
    postgres_db: str = "regdelta"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    database_url: str | None = None
    # "null" opens a fresh connection per checkout instead of pooling. Needed
    # when one process drives several event loops (the test suite does), since
    # an async connection must not be reused across loops.
    database_pool: Literal["queue", "null"] = "queue"

    # --- Embeddings / reranker ---
    # Pinned to the Hugging Face commits every evaluation was measured with, so
    # a fresh download (a new container, CI) loads the same weights, and a
    # later upstream revision is never picked up unreviewed.
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_model_revision: str = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
    embedding_dim: int = 384
    reranker_model: str = "BAAI/bge-reranker-base"
    reranker_model_revision: str = "2cfc18c9415c912f9d8155881c133215df768a70"

    # --- Retrieval pipeline ---
    # Load the embedding + reranker models once at API startup (in the
    # background) rather than lazily inside the first search/assessment, where
    # the multi-second CPU load would look like a frozen request.
    warm_models_on_startup: bool = True
    rrf_k: int = Field(60, ge=1)
    retrieve_top_n: int = Field(50, ge=1, le=500)
    rerank_top_k: int = Field(8, ge=1, le=100)
    # Applied to the cross-encoder's sigmoid output. Not a calibrated
    # probability: it was chosen on the synthetic corpus (docs/evaluation.md).
    relevance_threshold: float = Field(0.35, ge=0.0, le=1.0)

    # --- LLM gateway ---
    llm_provider: Provider = "deterministic"
    # Model ids must match the selected provider; the defaults are Groq's.
    llm_model: str = "openai/gpt-oss-20b"
    vision_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    # "low" keeps reasoning-token use small so the structured JSON verdict fits
    # inside llm_max_tokens (and the free-tier budget).
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    # Caps reasoning + response tokens per call. Providers reserve this amount
    # against rate limits; Groq's free tier allows ~8000 tokens/minute.
    llm_max_tokens: int = Field(1024, ge=16)
    # Total attempts per call, including the first, on transient errors.
    llm_max_retries: int = Field(3, ge=1, le=10)
    llm_request_timeout_seconds: float = Field(120.0, gt=0)
    # Concurrent provider calls per process. The graph fans out per obligation;
    # this keeps a free-tier rate limit from turning into a wall of retries.
    llm_max_concurrency: int = Field(2, ge=1, le=32)
    anthropic_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    # OpenAI-compatible endpoint; overridable only for testing against a proxy.
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # --- Agent hard limits (per assessment) ---
    max_verification_retries: int = Field(2, ge=0, le=5)
    max_assessment_tokens: int = Field(200_000, ge=1)
    # Provider calls one assessment may make. Checked before every call, so a
    # large circular cannot fan out into an unbounded bill.
    max_assessment_calls: int = Field(300, ge=1)
    assessment_timeout_seconds: int = Field(600, ge=1)

    # --- Ingestion ---
    scrape_delay_seconds: float = Field(2.0, ge=0)
    text_quality_threshold: float = Field(0.15, ge=0.0, le=1.0)
    vision_dpi: int = Field(200, ge=50, le=600)

    @property
    def sqlalchemy_url(self) -> str:
        """Async SQLAlchemy URL, assembled from parts unless overridden."""
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def effective_model(self) -> str:
        """The model recorded on runs produced with the current settings."""
        if self.llm_provider == "deterministic":
            return DETERMINISTIC_MODEL
        return self.llm_model

    def provider_readiness(self) -> tuple[bool, str | None]:
        """Whether assessments can run, and if not, a reason naming the fix."""
        key_for: dict[Provider, tuple[str, SecretStr | None]] = {
            "groq": ("GROQ_API_KEY", self.groq_api_key),
            "anthropic": ("ANTHROPIC_API_KEY", self.anthropic_api_key),
        }
        if self.llm_provider == "deterministic":
            return True, None
        variable, key = key_for[self.llm_provider]
        if key is None or not key.get_secret_value().strip():
            return False, (
                f"LLM_PROVIDER={self.llm_provider} needs {variable}, which is not set. "
                "Set it in .env, or use LLM_PROVIDER=deterministic for the offline demo."
            )
        return True, None


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor. Raises a clear error if validation fails."""
    try:
        return Settings()
    except ValidationError as exc:  # pragma: no cover - exercised via tests
        # Re-raise with a concise pointer; pydantic already names the fields.
        raise RuntimeError(
            f"Invalid RegDelta configuration — fix the variables below in .env:\n{exc}"
        ) from exc
