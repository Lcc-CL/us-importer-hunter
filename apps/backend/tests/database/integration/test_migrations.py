"""Migration lifecycle against a dedicated scratch database:
empty → upgrade head → downgrade base → upgrade head."""

import asyncio
from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from tests.database.integration.conftest import (
    _replace_db,
    _run_sql_autocommit,
    run_alembic,
)

MIGRATION_DB = "importer_hunter_migration_test"


@pytest.fixture(scope="module")
def migration_db_url(pg_settings: Settings) -> Iterator[str]:
    admin_url = pg_settings.database_url
    asyncio.run(
        _run_sql_autocommit(
            admin_url,
            [
                f"DROP DATABASE IF EXISTS {MIGRATION_DB} WITH (FORCE)",
                f"CREATE DATABASE {MIGRATION_DB}",
            ],
        )
    )
    yield _replace_db(admin_url, MIGRATION_DB)
    asyncio.run(_run_sql_autocommit(admin_url, [f"DROP DATABASE {MIGRATION_DB} WITH (FORCE)"]))


async def _table_names(url: str) -> set[str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
            return {row[0] for row in result}
    finally:
        await engine.dispose()


EXPECTED_TABLES = {
    "companies",
    "company_aliases",
    "company_sources",
    "company_signals",
    "contacts",
    "opportunities",
    "opportunity_assessments",
    "opportunity_evidence",
    "outreaches",
    "email_drafts",
    "outcomes",
    "tasks",
    "task_attempts",
}


def test_upgrade_downgrade_upgrade(migration_db_url: str) -> None:
    run_alembic(["upgrade", "head"], MIGRATION_DB)
    tables = asyncio.run(_table_names(migration_db_url))
    assert EXPECTED_TABLES <= tables

    run_alembic(["downgrade", "base"], MIGRATION_DB)
    tables_after_downgrade = asyncio.run(_table_names(migration_db_url))
    assert EXPECTED_TABLES.isdisjoint(tables_after_downgrade)

    run_alembic(["upgrade", "head"], MIGRATION_DB)
    tables_again = asyncio.run(_table_names(migration_db_url))
    assert EXPECTED_TABLES <= tables_again
