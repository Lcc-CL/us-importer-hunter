"""Application settings loaded from environment variables / .env files.

The repo-root .env is the single source of truth for local development;
real environment variables always take precedence (e.g. inside Docker).
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, PostgresDsn, RedisDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_repo_root() -> Path:
    """Walk upward to the monorepo root; fall back to the working directory.

    Inside containers the backend is copied without its monorepo parents,
    so no marker is found — configuration then comes from real environment
    variables (and a ./.env if present).
    """
    for parent in Path(__file__).resolve().parents:
        if (parent / "docker-compose.yml").exists() or (parent / ".git").exists():
            return parent
    return Path.cwd()


REPO_ROOT = _find_repo_root()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "us-importer-hunter"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    backend_cors_origins: list[str] = ["http://localhost:3000"]

    # PostgreSQL. Managed platforms (Zeabur) hand out one DATABASE_URL; when
    # set it wins over the individual POSTGRES_* fields below.
    database_url_env: str = Field(
        "", validation_alias=AliasChoices("DATABASE_URL", "database_url_env")
    )
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "app"
    postgres_password: str = "change-me"
    postgres_db: str = "importer_hunter"

    # Redis. REDIS_URL, when set, wins over the individual fields.
    redis_url_env: str = Field(
        "", validation_alias=AliasChoices("REDIS_URL", "redis_url_env")
    )
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # AI
    email_generator_provider: Literal["fake", "openai"] = "fake"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    #: Optional OpenAI-compatible endpoint. Empty means the SDK default.
    openai_base_url: str = ""

    # DeepSeek (official API) — used when research_extractor_provider=deepseek.
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-pro"

    # Research extraction (v0.2 phase 5, ADR-0027). Fake stays the default so
    # no code path reaches a paid provider without an explicit opt-in.
    research_extractor_provider: Literal["fake", "openai", "deepseek"] = "fake"
    #: Empty falls back to openai_model — never a literal in the extractor.
    research_model: str = ""
    research_prompt_version: str = "website-research-v1"
    research_extractor_timeout_seconds: float = 30.0
    #: Total prompt budget across pages, split by page_ranker order.
    #: Measured, not estimated: 24k → 18k cut a quarter of the characters sent
    #: with no loss of validated claims, while 13k cost 13% of them. See
    #: docs/validation/v0.2-real-company-evaluation.md §token.
    research_extractor_max_input_chars: int = 18_000

    # Website research (v0.2, ADR-0026). Limits are configuration, never
    # literals in the fetch loop.
    research_max_pages: int = 5
    research_max_page_bytes: int = 2 * 1024 * 1024
    research_max_decompressed_bytes: int = 8 * 1024 * 1024
    research_max_page_chars: int = 40_000
    research_request_timeout_seconds: float = 10.0
    research_total_budget_seconds: float = 45.0
    research_max_redirects: int = 3
    research_request_delay_seconds: float = 0.5
    research_user_agent: str = (
        "USImporterHunterBot/0.2 (+https://github.com/Lcc-CL/us-importer-hunter)"
    )

    # Lightweight PostgreSQL prospect runner (D3a). One worker claims one job.
    prospect_worker_poll_seconds: float = 1.0
    prospect_job_lease_ttl_seconds: int = 120
    prospect_job_retry_delay_seconds: int = 5
    prospect_job_max_attempts: int = 3

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        override = self.database_url_env.strip()
        if override:
            # Platform URLs say postgresql://; the async engine needs asyncpg.
            if override.startswith("postgresql://"):
                return override.replace("postgresql://", "postgresql+asyncpg://", 1)
            if override.startswith("postgres://"):
                return override.replace("postgres://", "postgresql+asyncpg://", 1)
            return override
        return str(
            PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=self.postgres_user,
                password=self.postgres_password,
                host=self.postgres_host,
                port=self.postgres_port,
                path=self.postgres_db,
            )
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resolved_research_model(self) -> str:
        """RESEARCH_MODEL, or OPENAI_MODEL when it is unset.

        Resolution lives here rather than in the extractor so that no model
        name is ever hard-coded next to the provider call.
        """
        return self.research_model.strip() or self.openai_model.strip()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def redis_url(self) -> str:
        override = self.redis_url_env.strip()
        if override:
            return override
        return str(
            RedisDsn.build(
                scheme="redis",
                host=self.redis_host,
                port=self.redis_port,
                path=str(self.redis_db),
            )
        )


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor, used as a FastAPI dependency."""
    return Settings()
