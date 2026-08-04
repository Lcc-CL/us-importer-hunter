"""Migration lifecycle against a dedicated scratch database:
empty → upgrade head → downgrade base → upgrade head."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

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


async def _column_names(url: str, table_name: str) -> set[str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = :table_name"
                ),
                {"table_name": table_name},
            )
            return {row[0] for row in result}
    finally:
        await engine.dispose()


async def _insert_core_company(url: str, company_id: UUID) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO companies "
                    "(id, name, normalized_name, website, website_host, verified, created_at) "
                    "VALUES (:id, :name, :normalized_name, NULL, NULL, false, :created_at)"
                ),
                {
                    "id": company_id,
                    "name": "Migration Core Company",
                    "normalized_name": "migration core company",
                    "created_at": datetime(2026, 8, 1, tzinfo=UTC),
                },
            )
    finally:
        await engine.dispose()


async def _company_exists(url: str, company_id: UUID) -> bool:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            result = await connection.scalar(
                text("SELECT count(*) FROM companies WHERE id = :id"),
                {"id": company_id},
            )
            return int(result or 0) == 1
    finally:
        await engine.dispose()


EXPECTED_TABLES = {
    "import_sessions",
    "raw_import_rows",
    "import_resolutions",
    "company_external_identities",
    "company_resolution_profiles",
    "company_contacts",
    "import_entity_decisions",
    "import_processing_jobs",
    "prospect_routing_runs",
    "prospect_routes",
    "suppression_entries",
    "umail_export_batches",
    "umail_export_rows",
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
    "import_evidence_quality_assessments",
    "import_evidence_signal_promotions",
    "import_evidence_company_signals",
    "import_evidence_promotion_quality_assessments",
    "importer_evidence_aggregates",
    "importer_evidence_aggregate_shipments",
}


def test_upgrade_downgrade_upgrade(migration_db_url: str) -> None:
    run_alembic(["upgrade", "head"], MIGRATION_DB)
    tables = asyncio.run(_table_names(migration_db_url))
    assert EXPECTED_TABLES <= tables
    draft_columns = asyncio.run(_column_names(migration_db_url, "email_drafts"))
    assert {"approval_status", "approved_at", "approved_by_name"} <= draft_columns
    assert "status" not in draft_columns
    export_row_columns = asyncio.run(_column_names(migration_db_url, "umail_export_rows"))
    assert {
        "first_name",
        "last_name",
        "phone",
        "country",
        "route_reasons",
    } <= export_row_columns

    run_alembic(["downgrade", "base"], MIGRATION_DB)
    tables_after_downgrade = asyncio.run(_table_names(migration_db_url))
    assert EXPECTED_TABLES.isdisjoint(tables_after_downgrade)

    run_alembic(["upgrade", "head"], MIGRATION_DB)
    tables_again = asyncio.run(_table_names(migration_db_url))
    assert EXPECTED_TABLES <= tables_again
    draft_columns_again = asyncio.run(_column_names(migration_db_url, "email_drafts"))
    assert {"approval_status", "approved_at", "approved_by_name"} <= draft_columns_again
    export_row_columns_again = asyncio.run(
        _column_names(migration_db_url, "umail_export_rows")
    )
    assert {
        "first_name",
        "last_name",
        "phone",
        "country",
        "route_reasons",
    } <= export_row_columns_again


def test_d5a1_downgrade_preserves_existing_core_data(migration_db_url: str) -> None:
    company_id = UUID("00000000-0000-0000-0000-00000000d5a1")
    run_alembic(["upgrade", "head"], MIGRATION_DB)
    asyncio.run(_insert_core_company(migration_db_url, company_id))

    run_alembic(["downgrade", "d3a3b4c5d6e7"], MIGRATION_DB)
    tables = asyncio.run(_table_names(migration_db_url))
    assert "import_sessions" not in tables
    assert "raw_import_rows" not in tables
    assert asyncio.run(_company_exists(migration_db_url, company_id))

    run_alembic(["upgrade", "head"], MIGRATION_DB)
    assert asyncio.run(_company_exists(migration_db_url, company_id))
