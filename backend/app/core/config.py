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

from pydantic import Field, SecretStr, ValidationError, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

from app.core.model_sources import APPROVED, Role, unapproved

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

# The server's own databases: the administrative connection uses "postgres",
# and none of them may be RegDelta's application database.
ADMIN_DATABASE = "postgres"
_SERVER_DATABASES = frozenset({ADMIN_DATABASE, "template0", "template1"})


class DatabaseConfigError(RuntimeError):
    """The database settings do not name one usable database.

    Messages name variables and never include a password or DATABASE_URL.
    """


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
    # The only database settings; see database_target().
    postgres_user: str = "regdelta"
    postgres_password: SecretStr = SecretStr("regdelta")
    postgres_db: str = "regdelta"
    postgres_host: str = "localhost"
    postgres_port: int = Field(5432, ge=1, le=65535)
    # Read only so that a value left in the environment is refused, not used.
    database_url: SecretStr | None = None
    # "null" opens a fresh connection per checkout instead of pooling. Needed
    # when one process drives several event loops (the test suite does), since
    # an async connection must not be reused across loops.
    database_pool: Literal["queue", "null"] = "queue"

    # --- Embeddings / reranker ---
    # Pinned to the Hugging Face commits every evaluation was measured with, so
    # a fresh download (a new container, CI) loads the same weights, and a
    # later upstream revision is never picked up unreviewed. Only these are
    # accepted (app.core.model_sources says why).
    embedding_model: str = APPROVED["embedding"][0]
    embedding_model_revision: str = APPROVED["embedding"][1]
    embedding_dim: int = 384
    reranker_model: str = APPROVED["reranker"][0]
    reranker_model_revision: str = APPROVED["reranker"][1]

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

    @field_validator("embedding_model_revision", "reranker_model_revision")
    @classmethod
    def _approved_model(cls, revision: str, info: ValidationInfo) -> str:
        role: Role = "embedding" if info.field_name == "embedding_model_revision" else "reranker"
        model = info.data.get(f"{role}_model")
        if model is not None and (reason := unapproved(role, model, revision)):
            raise ValueError(reason)
        return revision

    def database_target(self) -> URL:
        """The one database the app, migrations, checks and tools connect to.

        Built from the POSTGRES_* settings with ``URL.create``, so reserved
        characters in a user or password keep their meaning; no URL string is
        parsed or assembled. A non-empty DATABASE_URL is refused, not
        preferred: when it was preferred, the safety checks (which read
        POSTGRES_*) and the migrations could reach different databases.
        Raises DatabaseConfigError before any connection is made.
        """
        if self.database_url is not None and self.database_url.get_secret_value().strip():
            raise DatabaseConfigError(
                "DATABASE_URL is set (value not shown) but is not supported: RegDelta reads "
                "its database only from POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, "
                "POSTGRES_PASSWORD and POSTGRES_DB. Unset DATABASE_URL."
            )
        for variable, value in (
            ("POSTGRES_HOST", self.postgres_host),
            ("POSTGRES_USER", self.postgres_user),
            ("POSTGRES_DB", self.postgres_db),
        ):
            if not value.strip():
                raise DatabaseConfigError(f"{variable} is empty.")
        if self.postgres_db in _SERVER_DATABASES:
            raise DatabaseConfigError(
                f"POSTGRES_DB={self.postgres_db} is one of the server's own databases; "
                "name a database for RegDelta."
            )
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value() or None,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
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


def describe_database(url: URL) -> str:
    """``user@host:port/name``: how every tool names its database; no password."""
    return f"{url.username}@{url.host}:{url.port}/{url.database}"


def psycopg_args(url: URL, database: str | None = None) -> dict[str, object]:
    """``psycopg.connect`` keywords for ``url``, or for another database on its server."""
    args = url.translate_connect_args(username="user", database="dbname")
    if database is not None:
        args["dbname"] = database
    return args


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
