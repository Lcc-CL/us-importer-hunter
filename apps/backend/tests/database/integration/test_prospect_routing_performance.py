"""D5c 500-company / 10,000-row PostgreSQL performance and N+1 smoke test."""

import hashlib
import re
import tempfile
import time
import tracemalloc
from collections import Counter
from collections.abc import AsyncIterator
from datetime import timedelta

from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import event, func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import get_uow_factory
from app.core.config import Settings
from app.database.models.import_resolution import ImportEntityDecisionModel
from app.database.models.opportunity import OpportunityModel
from app.database.models.outreach import OutreachModel
from app.database.models.prospect_batch import ProspectBatchModel
from app.database.models.prospect_routing import ProspectRouteModel
from app.database.models.research import ResearchRunModel
from app.main import create_app
from app.workflows.import_resolution import (
    ImportEntityResolutionWorkflow,
    ImportProcessingJobCoordinator,
    ImportProcessingJobRunner,
)
from app.workflows.prospect_routing import ProspectRoutingExecutionWorkflow
from tests.database.integration.conftest import UowFactory

MAPPING = (
    '{"company_name":"company","external_company_id":"external_id",'
    '"website":"website","address":"address","company_type":"company_type",'
    '"contact_name":"contact","contact_email":"email","contact_title":"title",'
    '"product_description":"product","hs_code":"hs","shipment_date":"date",'
    '"origin_country":"origin","pol":"pol","pod":"pod"}'
)


class QueryCounter:
    def __init__(self) -> None:
        self.value = 0
        self.by_operation: Counter[str] = Counter()

    def increment(
        self,
        _connection: object,
        _cursor: object,
        statement: str,
        *_args: object,
        **_kwargs: object,
    ) -> None:
        self.value += 1
        match = re.search(
            r"^(SELECT).*?\bFROM\s+([a-z_]+)|^(INSERT)\s+INTO\s+([a-z_]+)|"
            r"^(UPDATE)\s+([a-z_]+)|^(DELETE)\s+FROM\s+([a-z_]+)",
            statement,
            re.IGNORECASE | re.DOTALL,
        )
        if match is None:
            self.by_operation[statement.split(maxsplit=1)[0].upper()] += 1
            return
        operation = next(value for value in match.groups()[::2] if value is not None)
        table = next(value for value in match.groups()[1::2] if value is not None)
        self.by_operation[f"{operation.upper()} {table}"] += 1


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
        routing_workflow=ProspectRoutingExecutionWorkflow(uow_factory),
    )


async def test_route_500_companies_5000_contacts_10000_rows_with_conflicts(
    uow_factory: UowFactory,
) -> None:
    with tempfile.NamedTemporaryFile(mode="w+b", suffix=".csv") as file:
        file.write(
            b"company,external_id,website,address,company_type,contact,email,title,"
            b"product,hs,date,origin,pol,pod\n"
        )
        for company_index in range(500):
            company_token = hashlib.sha256(
                f"routing-company-{company_index}".encode()
            ).hexdigest()[:24]
            for contact_index in range(10):
                prefix = (
                    f"R{company_token},ROUTE-{company_index},"
                    f"routing-importer-{company_index}.example,"
                    f"{company_index} Port Road TX,importer,"
                )
                email = f"buyer-{contact_index}@routing-importer-{company_index}.example"
                month = contact_index % 10 + 1
                file.write(
                    (
                        f"{prefix}Buyer {contact_index},{email},Procurement Director,"
                        f"industrial hardware,8205.40,2026-{month:02d}-01,"
                        "China,Shanghai,Los Angeles\n"
                    ).encode()
                )
                file.write(
                    (
                        f"{prefix}Buyer {contact_index},{email},Senior Procurement Director,"
                        f"industrial hardware,8205.40,2026-{month:02d}-15,"
                        "China,Shanghai,Los Angeles\n"
                    ).encode()
                )
        file.flush()
        file_size = file.tell()
        file.seek(0)

        upload_response: Response | None = None
        async for client in make_client(uow_factory):
            upload_response = await client.post(
                "/api/v1/import-sessions",
                data={
                    "source": "netease_prospect_routing_performance",
                    "mapping": MAPPING,
                },
                files={"file": ("synthetic-routing-10000.csv", file, "text/csv")},
            )
            assert upload_response.status_code == 201, upload_response.text
            session_id = str(upload_response.json()["session_id"])
            submitted_resolution = await client.post(
                f"/api/v1/import-sessions/{session_id}/resolve"
            )
            assert submitted_resolution.status_code == 202
            runner = make_runner(uow_factory)
            assert await runner.run_once(owner="routing-performance-resolution")

            async with uow_factory() as uow:
                assert uow._session is not None  # noqa: SLF001
                blocked_decision_ids = list(
                    await uow._session.scalars(  # noqa: SLF001
                        select(ImportEntityDecisionModel.id)
                        .where(ImportEntityDecisionModel.entity_type == "company")
                        .distinct(ImportEntityDecisionModel.candidate_entity_id)
                        .order_by(ImportEntityDecisionModel.candidate_entity_id)
                        .limit(50)
                    )
                )
                await uow._session.execute(  # noqa: SLF001
                    update(ImportEntityDecisionModel)
                    .where(ImportEntityDecisionModel.id.in_(blocked_decision_ids))
                    .values(
                        decision="review_required",
                        review_status="pending",
                        reason_codes=["synthetic_performance_conflict"],
                    )
                )
                bind = uow._session.bind  # noqa: SLF001
                assert isinstance(bind, AsyncConnection)
                sync_connection = bind.sync_connection
                await uow.commit()

            query_count = QueryCounter()
            event.listen(sync_connection, "before_cursor_execute", query_count.increment)
            tracemalloc.start()
            started = time.perf_counter()
            try:
                submitted = await client.post(
                    f"/api/v1/import-sessions/{session_id}/routing-runs",
                    json={
                        "criteria": {
                            "target_product_keywords": ["hardware"],
                            "target_hs_codes": ["8205"],
                            "preferred_origin_countries": ["China"],
                            "preferred_pol": ["Shanghai"],
                            "preferred_pod": ["Los Angeles"],
                        },
                        "campaign_name": "D5c performance",
                    },
                )
                assert submitted.status_code == 202, submitted.text
                routing_run_id = str(submitted.json()["routing_run_id"])
                assert await runner.run_once(owner="routing-performance-worker")
            finally:
                elapsed = time.perf_counter() - started
                _current, peak_memory = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                event.remove(
                    sync_connection,
                    "before_cursor_execute",
                    query_count.increment,
                )

            result = await client.get(
                f"/api/v1/prospect-routing-runs/{routing_run_id}"
            )
            assert result.status_code == 200
            body = result.json()

    assert upload_response is not None
    assert upload_response.json()["accepted_rows"] == 10_000
    assert body["total_companies"] == 500
    assert body["routed_companies"] == 450
    assert body["blocked_companies"] == 50
    assert body["tier_a_count"] == 450
    assert body["tier_b_count"] == 0
    assert body["tier_c_count"] == 0
    assert body["tier_d_count"] == 0

    async with uow_factory() as uow:
        assert uow._session is not None  # noqa: SLF001
        route_count = await uow._session.scalar(  # noqa: SLF001
            select(func.count()).select_from(ProspectRouteModel)
        )
        downstream_counts = [
            await uow._session.scalar(select(func.count()).select_from(model))  # noqa: SLF001
            for model in (
                OpportunityModel,
                ResearchRunModel,
                OutreachModel,
                ProspectBatchModel,
            )
        ]
    assert route_count == 500
    assert downstream_counts == [0, 0, 0, 0]
    print(
        "D5c performance:",
        {
            "file_size_bytes": file_size,
            "elapsed_seconds": round(elapsed, 3),
            "peak_memory_bytes": peak_memory,
            "sql_statements": query_count.value,
            "sql_by_operation": dict(query_count.by_operation),
            "tier_a": body["tier_a_count"],
            "tier_b": body["tier_b_count"],
            "tier_c": body["tier_c_count"],
            "tier_d": body["tier_d_count"],
            "blocked": body["blocked_companies"],
            "obvious_n_plus_one": query_count.value >= 100,
        },
    )
    assert elapsed < 60
    assert peak_memory < 256 * 1024 * 1024
    assert query_count.value < 100
