"""Platform URL overrides (Zeabur): DATABASE_URL / REDIS_URL win when set."""

from app.core.config import Settings


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


class TestDatabaseUrlOverride:
    def test_platform_url_wins_and_gets_the_asyncpg_scheme(self) -> None:
        settings = _settings(DATABASE_URL="postgresql://u:p@db.internal:5432/app")
        assert settings.database_url == "postgresql+asyncpg://u:p@db.internal:5432/app"

    def test_legacy_postgres_scheme_is_upgraded(self) -> None:
        settings = _settings(DATABASE_URL="postgres://u:p@db.internal:5432/app")
        assert settings.database_url == "postgresql+asyncpg://u:p@db.internal:5432/app"

    def test_unset_url_falls_back_to_discrete_fields(self) -> None:
        settings = _settings(postgres_host="pg", postgres_db="importer_hunter")
        assert settings.database_url.startswith("postgresql+asyncpg://")
        assert "pg" in settings.database_url


class TestRedisUrlOverride:
    def test_platform_url_wins(self) -> None:
        settings = _settings(REDIS_URL="redis://cache.internal:6379/0")
        assert settings.redis_url == "redis://cache.internal:6379/0"

    def test_unset_url_falls_back_to_discrete_fields(self) -> None:
        settings = _settings(redis_host="cache")
        assert settings.redis_url.startswith("redis://cache")
