"""10,000-row D5a1 performance and boundary smoke test."""

import tempfile
import time
import tracemalloc
from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.api.deps import get_uow_factory
from app.core.config import Settings
from app.database.models.bulk_import import RawImportRowModel
from app.database.models.company import CompanyModel
from app.database.models.opportunity import OpportunityModel
from app.database.models.outreach import OutreachModel
from app.database.models.research import ResearchRunModel
from app.main import create_app
from tests.database.integration.conftest import UowFactory


async def make_client(uow_factory: UowFactory) -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(_env_file=None, app_env="development"))
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=60,
    ) as client:
        yield client


async def test_import_10000_rows_without_downstream_side_effects(
    uow_factory: UowFactory,
) -> None:
    with tempfile.NamedTemporaryFile(mode="w+b", suffix=".csv") as file:
        file.write(b"company,email,product\n")
        first_row = b"Company 0,buyer0@example.com,hardware\n"
        file.write(first_row)
        for index in range(1, 9_990):
            file.write(
                f"Company {index},buyer{index}@example.com,hardware\n".encode()
            )
        for _ in range(5):
            file.write(first_row)
        for index in range(5):
            file.write(f"Invalid {index}\n".encode())
        file.flush()
        file_size = file.tell()
        file.seek(0)

        tracemalloc.start()
        started = time.perf_counter()
        async for client in make_client(uow_factory):
            response = await client.post(
                "/api/v1/import-sessions",
                data={"source": "netease_performance_fixture"},
                files={"file": ("synthetic-10000.csv", file, "text/csv")},
            )
        elapsed = time.perf_counter() - started
        _current, peak_memory = tracemalloc.get_traced_memory()
        tracemalloc.stop()

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["total_rows"] == 10_000
    assert body["accepted_rows"] == 9_990
    assert body["duplicate_rows"] == 5
    assert body["invalid_rows"] == 5

    async with uow_factory() as uow:
        assert uow._session is not None  # noqa: SLF001 - integration boundary assertion
        raw_count = await uow._session.scalar(  # noqa: SLF001
            select(func.count()).select_from(RawImportRowModel)
        )
        downstream_counts = [
            await uow._session.scalar(select(func.count()).select_from(model))  # noqa: SLF001
            for model in (CompanyModel, OpportunityModel, ResearchRunModel, OutreachModel)
        ]
    assert raw_count == 10_000
    assert downstream_counts == [0, 0, 0, 0]
    print(
        "D5a1 performance:",
        {
            "file_size_bytes": file_size,
            "elapsed_seconds": round(elapsed, 3),
            "peak_memory_bytes": peak_memory,
            "accepted": body["accepted_rows"],
            "invalid": body["invalid_rows"],
            "duplicate": body["duplicate_rows"],
            "postgres_rows": raw_count,
        },
    )
