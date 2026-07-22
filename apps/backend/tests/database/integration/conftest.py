"""Integration test infrastructure: a real PostgreSQL test database.

- Session scope: (re)create `importer_hunter_test`, migrate it via a real
  `alembic upgrade head` subprocess (the migration itself is under test).
- Test scope: one outer transaction per test with savepoint-mode sessions,
  so UnitOfWork.commit() works normally while the outer rollback keeps
  tests isolated.

Skips cleanly when PostgreSQL is not reachable (e.g. Docker down).
"""

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings
from app.database.uow import SqlAlchemyUnitOfWork

BACKEND_ROOT = Path(__file__).resolve().parents[3]
TEST_DB = "importer_hunter_test"

UowFactory = Callable[[], SqlAlchemyUnitOfWork]


def _replace_db(url: str, db_name: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{db_name}"


async def _probe(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.connect():
            pass
    finally:
        await engine.dispose()


async def _run_sql_autocommit(url: str, statements: list[str]) -> None:
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            for statement in statements:
                await conn.execute(text(statement))
    finally:
        await engine.dispose()


def run_alembic(command: list[str], db_name: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", *command],
        cwd=BACKEND_ROOT,
        env={**os.environ, "POSTGRES_DB": db_name},
        check=True,
        capture_output=True,
        timeout=120,
    )


@pytest.fixture(scope="session")
def pg_settings() -> Settings:
    settings = Settings(_env_file=None)
    try:
        asyncio.run(_probe(settings.database_url))
    except Exception:  # noqa: BLE001 — any connection failure means "no PG here"
        pytest.skip("PostgreSQL is not reachable — start `docker compose up postgres`")
    return settings


@pytest.fixture(scope="session")
def test_db_url(pg_settings: Settings) -> str:
    admin_url = pg_settings.database_url
    asyncio.run(
        _run_sql_autocommit(
            admin_url,
            [
                f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)",
                f"CREATE DATABASE {TEST_DB}",
            ],
        )
    )
    run_alembic(["upgrade", "head"], TEST_DB)
    return _replace_db(admin_url, TEST_DB)


@pytest.fixture
async def engine(test_db_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(test_db_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def uow_factory(engine: AsyncEngine) -> AsyncIterator[UowFactory]:
    """UnitOfWork factory whose commits land in savepoints — the outer
    transaction is rolled back after each test."""
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session_factory = async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
            class_=AsyncSession,
        )

        def make() -> SqlAlchemyUnitOfWork:
            return SqlAlchemyUnitOfWork(session_factory)

        yield make
        await transaction.rollback()
