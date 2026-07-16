"""Application settings loaded from environment variables / .env files.

The repo-root .env is the single source of truth for local development;
real environment variables always take precedence (e.g. inside Docker).
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import PostgresDsn, RedisDsn, computed_field
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

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "app"
    postgres_password: str = "change-me"
    postgres_db: str = "importer_hunter"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # AI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
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
    def redis_url(self) -> str:
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
