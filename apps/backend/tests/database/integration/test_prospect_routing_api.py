"""D5c PostgreSQL API, invalidation, review and batch-boundary integration."""

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import cast
from uuid import UUID

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.api.deps import get_uow_factory
from app.core.config import Settings
from app.database.models.opportunity import OpportunityModel
from app.database.models.outreach import OutreachModel
from app.database.models.prospect_batch import ProspectBatchJobModel, ProspectBatchModel
from app.database.models.research import ResearchRunModel
from app.domain.clock import utcnow
from app.domain.import_resolution import ImportJobType, ImportProcessingJob
from app.domain.prospect_routing import ProspectRoutingCriteria, ProspectRoutingRun
from app.main import create_app
from app.services.prospect_routing import DEFAULT_WEIGHTS
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


async def make_client(uow_factory: UowFactory) -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(_env_file=None, app_env="development"))
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
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


def company_rows(
    *,
    name: str,
    external_id: str,
    website: str,
    address: str,
    contact: str,
    email: str,
    title: str,
) -> list[str]:
    dates = (
        "2026-07-01",
        "2026-07-15",
        "2026-06-01",
        "2026-06-15",
        "2026-05-01",
        "2026-05-15",
        "2026-04-01",
        "2026-04-15",
        "2026-03-01",
        "2026-03-15",
        "2026-02-01",
        "2026-02-15",
    )
    rows: list[str] = []
    for position, shipment_date in enumerate(dates):
        contact_values = (contact, email, title) if position == 0 else ("", "", "")
        rows.append(
            ",".join(
                (
                    name,
                    external_id,
                    website,
                    address,
                    "importer",
                    *contact_values,
                    "industrial hardware tools",
                    "8205.40",
                    shipment_date,
                    "China",
                    "Shanghai",
                    "Los Angeles",
                )
            )
        )
    return rows


async def upload(client: AsyncClient) -> str:
    rows = [
        *company_rows(
            name="D5C Atlas Hardware",
            external_id="D5C-ATLAS",
            website="d5c-atlas.example",
            address="100 Main St Austin TX",
            contact="Maria Chen",
            email="maria@d5c-atlas.example",
            title="Director of Logistics",
        ),
        *company_rows(
            name="D5C Beta Tools",
            external_id="D5C-BETA",
            website="d5c-beta.example",
            address="200 Market St Seattle WA",
            contact="Pat Lee",
            email="pat@d5c-beta.example",
            title="Procurement Director",
        ),
        (
            "D5C Unrelated Furniture,,d5c-atlas.example,900 Ocean Dr Miami FL,warehouse,"
            "Taylor Kim,taylor@unrelated.example,Operations Manager,upholstered furniture,"
            "9401,2026-07-20,Vietnam,Ho Chi Minh,Long Beach"
        ),
    ]
    response = await client.post(
        "/api/v1/import-sessions",
        data={"source": "netease_foreign_trade", "mapping": MAPPING},
        files={
            "file": (
                "d5c-routing.csv",
                (
                    "company,external_id,website,address,company_type,contact,email,title,"
                    "product,hs,date,origin,pol,pod\n" + "\n".join(rows)
                ).encode(),
                "text/csv",
            )
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["session_id"])


async def test_routing_recalculation_review_and_batch_do_not_start_deep_processing(
    uow_factory: UowFactory,
) -> None:
    runner = make_runner(uow_factory)
    payload = {
        "criteria": {
            "target_product_keywords": ["hardware"],
            "target_hs_codes": ["8205"],
            "preferred_origin_countries": ["China"],
            "preferred_pol": ["Shanghai"],
            "preferred_pod": ["Los Angeles"],
        },
        "campaign_name": "D5c hardware",
    }
    async for client in make_client(uow_factory):
        missing_target = await client.post(
            "/api/v1/import-sessions/00000000-0000-0000-0000-000000000000/routing-runs",
            json={"criteria": {}},
        )
        assert missing_target.status_code == 422
        assert missing_target.json()["code"] == "ROUTING_TARGET_REQUIRED"

        too_many_companies = await client.post(
            "/api/v1/prospect-routing-runs/00000000-0000-0000-0000-000000000000/"
            "prospect-batches",
            json={
                "company_ids": [
                    f"00000000-0000-0000-0000-{position:012d}"
                    for position in range(1, 7)
                ]
            },
        )
        assert too_many_companies.status_code == 422

        session_id = await upload(client)
        submitted_resolution = await client.post(
            f"/api/v1/import-sessions/{session_id}/resolve"
        )
        assert submitted_resolution.status_code == 202
        assert await runner.run_once(owner="d5c-resolution-worker") is True

        submitted = await client.post(
            f"/api/v1/import-sessions/{session_id}/routing-runs",
            json=payload,
        )
        assert submitted.status_code == 202, submitted.text
        first_submission = submitted.json()
        routing_run_id = str(first_submission["routing_run_id"])
        assert first_submission["reused"] is False
        assert await runner.run_once(owner="d5c-routing-worker-1") is True

        first_run = await client.get(
            f"/api/v1/prospect-routing-runs/{routing_run_id}"
        )
        assert first_run.status_code == 200
        assert first_run.json()["status"] == "partial_completed"
        assert first_run.json()["blocked_companies"] == 1
        assert first_run.json()["routed_companies"] == 1

        routes_response = await client.get(
            f"/api/v1/prospect-routing-runs/{routing_run_id}/routes",
            params={"limit": 20},
        )
        assert routes_response.status_code == 200
        routes = cast(list[dict[str, object]], routes_response.json()["routes"])
        assert len(routes) == 2
        blocked = next(route for route in routes if route["review_status"] == "blocked")
        beta = next(route for route in routes if route["review_status"] != "blocked")
        assert beta["recommended_tier"] == "A"
        assert "UNRESOLVED_COMPANY_CONFLICT_BLOCKED" in cast(
            list[str], blocked["reason_codes"]
        )

        repeated = await client.post(
            f"/api/v1/import-sessions/{session_id}/routing-runs",
            json=payload,
        )
        assert repeated.status_code == 202
        assert repeated.json()["routing_run_id"] == routing_run_id
        assert repeated.json()["reused"] is True

        unconfirmed_batch = await client.post(
            f"/api/v1/prospect-routing-runs/{routing_run_id}/prospect-batches",
            json={"company_ids": [beta["company_id"]]},
        )
        assert unconfirmed_batch.status_code == 409

        decisions_response = await client.get(
            f"/api/v1/import-sessions/{session_id}/entity-decisions",
            params={"entity_type": "company", "review_status": "pending", "limit": 20},
        )
        pending = decisions_response.json()["decisions"]
        assert len(pending) == 1
        reviewed = await client.post(
            f"/api/v1/import-entity-decisions/{pending[0]['decision_id']}/review",
            json={"action": "merge", "reviewed_by": "d5c-reviewer"},
        )
        assert reviewed.status_code == 200

        recalculated = await client.post(
            f"/api/v1/import-sessions/{session_id}/routing-runs",
            json=payload,
        )
        assert recalculated.status_code == 202
        assert recalculated.json()["routing_run_id"] == routing_run_id
        assert recalculated.json()["recalculated"] is True
        assert await runner.run_once(owner="d5c-routing-worker-2") is True

        refreshed_run = await client.get(
            f"/api/v1/prospect-routing-runs/{routing_run_id}"
        )
        assert refreshed_run.json()["status"] == "completed"
        assert refreshed_run.json()["blocked_companies"] == 0
        assert refreshed_run.json()["execution_generation"] == 2

        refreshed_routes = await client.get(
            f"/api/v1/prospect-routing-runs/{routing_run_id}/routes",
            params={"tier": "A", "has_contact": True, "limit": 20},
        )
        a_routes = cast(list[dict[str, object]], refreshed_routes.json()["routes"])
        assert len(a_routes) >= 1
        selected = a_routes[0]
        confirmed = await client.post(
            f"/api/v1/prospect-routes/{selected['route_id']}/review",
            json={"action": "confirm", "reviewed_by": "d5c-reviewer"},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["review_status"] == "confirmed"
        confirmed_again = await client.post(
            f"/api/v1/prospect-routes/{selected['route_id']}/review",
            json={"action": "confirm", "reviewed_by": "d5c-reviewer"},
        )
        assert confirmed_again.status_code == 200
        conflicting_review = await client.post(
            f"/api/v1/prospect-routes/{selected['route_id']}/review",
            json={"action": "confirm", "reviewed_by": "another-reviewer"},
        )
        assert conflicting_review.status_code == 409

        batch = await client.post(
            f"/api/v1/prospect-routing-runs/{routing_run_id}/prospect-batches",
            json={"company_ids": [selected["company_id"]]},
        )
        assert batch.status_code == 201, batch.text
        batch_payload = batch.json()
        assert batch_payload["processing_started"] is False
        assert batch_payload["reused"] is False
        repeated_batch = await client.post(
            f"/api/v1/prospect-routing-runs/{routing_run_id}/prospect-batches",
            json={"company_ids": [selected["company_id"]]},
        )
        assert repeated_batch.status_code == 201
        assert repeated_batch.json()["batch_id"] == batch_payload["batch_id"]
        assert repeated_batch.json()["reused"] is True

    async with uow_factory() as uow:
        assert uow._session is not None  # noqa: SLF001 - integration boundary assertion
        batch_count = await uow._session.scalar(  # noqa: SLF001
            select(func.count()).select_from(ProspectBatchModel)
        )
        prospect_job_count = await uow._session.scalar(  # noqa: SLF001
            select(func.count()).select_from(ProspectBatchJobModel)
        )
        opportunity_count = await uow._session.scalar(  # noqa: SLF001
            select(func.count()).select_from(OpportunityModel)
        )
        research_count = await uow._session.scalar(  # noqa: SLF001
            select(func.count()).select_from(ResearchRunModel)
        )
        outreach_count = await uow._session.scalar(  # noqa: SLF001
            select(func.count()).select_from(OutreachModel)
        )
        assert batch_count == 1
        assert prospect_job_count == 0
        assert opportunity_count == 0
        assert research_count == 0
        assert outreach_count == 0


async def test_routing_job_stale_recovery_and_retry_exhaustion(
    uow_factory: UowFactory,
) -> None:
    async for client in make_client(uow_factory):
        session_id = UUID(await upload(client))

    run = ProspectRoutingRun.create(
        import_session_id=session_id,
        rules_version="d5c-deterministic-routing-v1",
        configuration_hash="a" * 64,
        entity_state_hash="b" * 64,
        criteria=ProspectRoutingCriteria(
            target_product_keywords=("hardware",),
            target_hs_codes=(),
            preferred_origin_countries=(),
            preferred_pol=(),
            preferred_pod=(),
            campaign_name=None,
            notes=None,
        ),
        weights_snapshot=DEFAULT_WEIGHTS,
    )
    stale_at = utcnow() - timedelta(minutes=5)
    job = ImportProcessingJob.create(
        import_session_id=session_id,
        job_type=ImportJobType.PROSPECT_ROUTING,
        routing_run_id=run.id,
        business_key=f"prospect-routing:{run.id}:1",
        max_attempts=2,
        now=stale_at,
    )
    job = job.lease(owner="lost-worker", lease_ttl=timedelta(seconds=1), now=stale_at)
    job = job.start(owner="lost-worker", now=stale_at)
    run.start()
    async with uow_factory() as uow:
        await uow.prospect_routing.add_run(run)
        await uow.flush()
        await uow.import_processing_jobs.add(job)
        await uow.commit()

    coordinator = ImportProcessingJobCoordinator(
        uow_factory,
        lease_ttl=timedelta(seconds=120),
        retry_delay=timedelta(0),
    )
    recovered = await coordinator.recover_stale()
    assert len(recovered) == 1
    assert recovered[0].status.value == "pending"

    leased = await coordinator.claim(owner="replacement-worker")
    assert leased is not None
    running = await coordinator.start(leased.id, owner="replacement-worker")
    failed = await coordinator.record_failure(
        running.id,
        owner="replacement-worker",
        error_code="ROUTING_TEST_FAILURE",
        error_summary="synthetic failure",
    )
    assert failed.status.value == "failed"
    async with uow_factory() as uow:
        persisted_run = await uow.prospect_routing.get_run(run.id)
        assert persisted_run is not None
        assert persisted_run.status.value == "failed"
