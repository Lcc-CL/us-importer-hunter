"""D5b1 10,000-row PostgreSQL performance and N+1 smoke test."""

import hashlib
import tempfile
import time
import tracemalloc
from collections.abc import AsyncIterator
from datetime import timedelta

from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import get_uow_factory
from app.core.config import Settings
from app.database.models.company import CompanyModel
from app.database.models.contact import ContactModel
from app.database.models.import_resolution import (
    CompanyContactModel,
    ImportEntityDecisionModel,
)
from app.database.models.opportunity import OpportunityModel
from app.database.models.outreach import OutreachModel
from app.database.models.research import ResearchRunModel
from app.main import create_app
from app.workflows.import_resolution import (
    ImportEntityResolutionWorkflow,
    ImportProcessingJobCoordinator,
    ImportProcessingJobRunner,
)
from tests.database.integration.conftest import UowFactory

MAPPING = (
    '{"company_name":"company","external_company_id":"external_id",'
    '"website":"website","address":"address","company_type":"company_type",'
    '"contact_name":"contact","contact_email":"email","contact_title":"title"}'
)


class QueryCounter:
    def __init__(self) -> None:
        self.value = 0

    def increment(self, *_args: object, **_kwargs: object) -> None:
        self.value += 1


async def make_client(uow_factory: UowFactory) -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(_env_file=None, app_env="development"))
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=120,
    ) as client:
        yield client


def make_runner(uow_factory: UowFactory) -> ImportProcessingJobRunner:
    coordinator = ImportProcessingJobCoordinator(
        uow_factory,
        lease_ttl=timedelta(seconds=120),
        retry_delay=timedelta(0),
    )
    return ImportProcessingJobRunner(
        coordinator=coordinator,
        workflow=ImportEntityResolutionWorkflow(uow_factory),
    )


async def test_resolve_500_companies_5000_contacts_10000_rows(
    uow_factory: UowFactory,
) -> None:
    with tempfile.NamedTemporaryFile(mode="w+b", suffix=".csv") as file:
        file.write(
            b"company,external_id,website,address,company_type,contact,email,title\n"
        )
        for company_index in range(500):
            company_token = hashlib.sha256(
                f"company-{company_index}".encode()
            ).hexdigest()[:24]
            for contact_index in range(10):
                prefix = (
                    f"C{company_token},PERF-{company_index},"
                    f"importer-{company_index}.example,{company_index} Port Road TX,"
                    "importer,"
                )
                email = f"buyer-{contact_index}@importer-{company_index}.example"
                file.write(
                    f"{prefix}Buyer {contact_index},{email},Buyer\n".encode()
                )
                file.write(
                    f"{prefix}Buyer {contact_index},{email},Senior Buyer\n".encode()
                )
        file.flush()
        file_size = file.tell()
        file.seek(0)

        upload_response: Response | None = None
        async for client in make_client(uow_factory):
            upload_response = await client.post(
                "/api/v1/import-sessions",
                data={
                    "source": "netease_entity_resolution_performance",
                    "mapping": MAPPING,
                },
                files={"file": ("synthetic-resolution-10000.csv", file, "text/csv")},
            )
            assert upload_response.status_code == 201, upload_response.text
            session_id = str(upload_response.json()["session_id"])

            async with uow_factory() as uow:
                assert uow._session is not None  # noqa: SLF001
                bind = uow._session.bind  # noqa: SLF001
                assert isinstance(bind, AsyncConnection)
                sync_connection = bind.sync_connection

            query_count = QueryCounter()
            event.listen(sync_connection, "before_cursor_execute", query_count.increment)
            tracemalloc.start()
            started = time.perf_counter()
            try:
                submitted = await client.post(
                    f"/api/v1/import-sessions/{session_id}/resolve"
                )
                assert submitted.status_code == 202, submitted.text
                assert await make_runner(uow_factory).run_once(owner="performance-worker")
            finally:
                elapsed = time.perf_counter() - started
                _current, peak_memory = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                event.remove(
                    sync_connection, "before_cursor_execute", query_count.increment
                )

            result = await client.get(
                f"/api/v1/import-sessions/{session_id}/resolution"
            )
            assert result.status_code == 200, result.text
            body = result.json()

    assert upload_response is not None
    assert upload_response.json()["accepted_rows"] == 10_000
    assert body["processed_rows"] == 10_000
    assert body["companies_created"] == 500
    assert body["companies_reused"] == 9_500
    assert body["company_reviews_required"] == 0
    assert body["contacts_created"] == 5_000
    assert body["contacts_reused"] == 5_000
    assert body["company_contacts_created"] == 5_000
    assert body["failed_rows"] == 0

    async with uow_factory() as uow:
        assert uow._session is not None  # noqa: SLF001
        counts = {
            "companies": await uow._session.scalar(  # noqa: SLF001
                select(func.count()).select_from(CompanyModel)
            ),
            "contacts": await uow._session.scalar(  # noqa: SLF001
                select(func.count()).select_from(ContactModel)
            ),
            "company_contacts": await uow._session.scalar(  # noqa: SLF001
                select(func.count()).select_from(CompanyContactModel)
            ),
            "decisions": await uow._session.scalar(  # noqa: SLF001
                select(func.count()).select_from(ImportEntityDecisionModel)
            ),
        }
        downstream_counts = [
            await uow._session.scalar(select(func.count()).select_from(model))  # noqa: SLF001
            for model in (OpportunityModel, ResearchRunModel, OutreachModel)
        ]
    assert counts == {
        "companies": 500,
        "contacts": 5_000,
        "company_contacts": 5_000,
        "decisions": 20_000,
    }
    assert downstream_counts == [0, 0, 0]
    assert elapsed < 120
    assert peak_memory < 256 * 1024 * 1024
    assert query_count.value < 2_500
    print(
        "D5b1 performance:",
        {
            "file_size_bytes": file_size,
            "elapsed_seconds": round(elapsed, 3),
            "peak_memory_bytes": peak_memory,
            "sql_statements": query_count.value,
            **counts,
            "companies_reused": body["companies_reused"],
            "contacts_reused": body["contacts_reused"],
            "reviews_required": body["company_reviews_required"],
            "obvious_n_plus_one": query_count.value >= 2_500,
        },
    )
