"""Application settings loaded from environment variables / .env files.

The repo-root .env is the single source of truth for local development;
real environment variables always take precedence (e.g. inside Docker).
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import PostgresDsn, RedisDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/backend/app/core/config.py -> repo root is four levels up
REPO_ROOT = Path(__file__).resolve().parents[4]


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
