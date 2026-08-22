"""Application configuration.

Every environment variable is declared and validated here. A missing or
malformed required value raises at import/startup time with a message naming
the offending variable, so the process fails fast rather than deep in a request.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["anthropic", "groq"]

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
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    # --- Database ---
    postgres_user: str = "regdelta"
    postgres_password: str = "regdelta"
    postgres_db: str = "regdelta"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    database_url: str | None = None

    # --- Embeddings / reranker ---
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    reranker_model: str = "BAAI/bge-reranker-base"

    # --- Retrieval pipeline ---
    # Load the embedding + reranker models once at API startup (in the
    # background) rather than lazily inside the first search/assessment, where
    # the multi-second CPU load would look like a frozen request. Disabled in
    # tests so the suite does not pay the load.
    warm_models_on_startup: bool = True
    rrf_k: int = 60
    retrieve_top_n: int = 50
    rerank_top_k: int = 8
    relevance_threshold: float = 0.35

    # --- LLM gateway ---
    # Groq is the default so a fresh clone reaches a working assessment on the
    # provider's free tier; Anthropic stays available by setting LLM_PROVIDER.
    # The model strings must match the selected provider — the defaults below
    # are Groq model ids; an Anthropic run overrides LLM_MODEL/VISION_MODEL.
    llm_provider: Provider = "groq"
    llm_model: str = "openai/gpt-oss-20b"
    # Vision is the ingestion fallback for low-quality PDF pages. The default is
    # a Groq multimodal model; Anthropic runs override it (e.g. claude-opus-5).
    vision_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    # "low" keeps reasoning-token use small so the structured JSON verdict fits
    # inside llm_max_tokens (and the free-tier budget); raise it if you give the
    # model a larger token cap.
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    # Caps reasoning + response tokens per call. Providers reserve this whole
    # amount against rate limits, so it is kept small: a structured verdict needs
    # only a few hundred tokens, and Groq's free tier allows just 8000 tokens/min
    # — a large cap here would blow that budget on the first concurrent call.
    # Anthropic users with a higher budget can raise it in .env.
    llm_max_tokens: int = 1024
    llm_max_retries: int = 3
    # Per-request HTTP timeout for provider calls. Generous because concurrent
    # CPU reranking can delay the connection handshake.
    llm_request_timeout_seconds: float = 120.0
    anthropic_api_key: str | None = None
    groq_api_key: str | None = None
    # OpenAI-compatible endpoint; overridable only for testing against a proxy.
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # --- Agent hard limits ---
    max_verification_retries: int = 2
    max_assessment_tokens: int = 200_000
    assessment_timeout_seconds: int = 600

    # --- Ingestion ---
    scrape_delay_seconds: float = 2.0
    text_quality_threshold: float = 0.15
    vision_dpi: int = 200

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

    @model_validator(mode="after")
    def _require_key_for_selected_provider(self) -> Settings:
        """The gateway needs credentials only for the *selected* provider.

        We validate conditionally so a Groq run does not demand an Anthropic key
        (or vice versa). The message names the exact variable.
        """
        required: dict[Provider, list[str]] = {
            "anthropic": ["anthropic_api_key"],
            "groq": ["groq_api_key"],
        }
        missing = [name for name in required[self.llm_provider] if not getattr(self, name)]
        if missing:
            names = ", ".join(m.upper() for m in missing)
            raise ValueError(
                f"LLM_PROVIDER={self.llm_provider!r} requires {names} to be set. "
                f"Set it in .env (see .env.example)."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor. Raises a clear error if validation fails."""
    try:
        return Settings()
    except ValidationError as exc:  # pragma: no cover - exercised via tests
        # Re-raise with a concise pointer; pydantic already names the fields.
        raise RuntimeError(
            "Invalid RegDelta configuration — fix the variables below in .env:\n"
            f"{exc}"
        ) from exc
