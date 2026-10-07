"""D2a API persistence and refresh recovery on PostgreSQL."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import timedelta
from typing import cast
from uuid import UUID

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.deps import (
    get_prospect_batch_workflow,
    get_uow_factory,
)
from app.core.config import Settings
from app.database.models.company import CompanyModel
from app.database.models.task import TaskModel
from app.database.session import create_session_factory
from app.database.uow import SqlAlchemyUnitOfWork
from app.domain.clock import utcnow
from app.domain.prospect_batch import ProspectBatch
from app.domain.repositories import ProspectBatchUnitOfWork
from app.domain.research import (
    ExtractorIdentity,
    ResearchClaim,
    ResearchPage,
    ResearchProfile,
    ResearchRun,
)
from app.domain.services import SenderProfile
from app.domain.values import SourceReference
from app.main import create_app
from app.services.contact import DeterministicDecisionMakerSelectionService
from app.services.contact_discovery import (
    ContactSelection,
    DiscoveredContact,
    DiscoverySourceType,
    RankedContact,
)
from app.services.contact_discovery_runner import ContactDiscoveryRunOutcome
from app.services.email import FakeEmailDraftGenerator
from app.services.scoring import DeterministicOpportunityScoringService
from app.workflows.contact_ingestion import ContactIngestionWorkflow
from app.workflows.decision_maker import DecisionMakerSelectionWorkflow
from app.workflows.email import EmailDraftGenerationWorkflow
from app.workflows.opportunity import OpportunityApplicationWorkflow
from app.workflows.prospect_batch import (
    CreateProspectBatchCommand,
    ProspectBatchWorkflow,
    ProspectJobCoordinator,
    ProspectJobRunner,
)
from app.workflows.research import ResearchAction, ResearchOutcome, ResearchRequest
from tests.database.integration.conftest import UowFactory


class PersistedZeroClaimResearch:
    def __init__(self, uow_factory: UowFactory) -> None:
        self._uow_factory = uow_factory

    async def handle(self, request: ResearchRequest) -> ResearchOutcome:
        assert request.company_id is not None
        async with self._uow_factory() as uow:
            company = await uow.companies.get_by_id(request.company_id)
        assert company is not None and company.website is not None
        run = ResearchRun.start(
            company.name.value,
            company.website.value,
            company_id=company.id,
            output_language=request.output_language,
        )
        run.mark_running()
        run.record_page(
            ResearchPage(
                position=0,
                url=company.website.value,
                final_url=company.website.value,
                http_status=200,
                content_type="text/html",
                fetched_at=utcnow(),
                content_chars=120,
            )
        )
        run.record_extraction(
            profile=ResearchProfile(),
            extractor=ExtractorIdentity(
                provider="fake",
                model="integration-zero-claim",
                prompt_version="integration-v1",
            ),
            proposed_count=0,
        )
        run.complete()
        async with self._uow_factory() as uow:
            await uow.research_runs.add(run)
            await uow.commit()
        return ResearchOutcome(
            action=ResearchAction.COMPLETED,
            company_id=company.id,
            research_id=run.id,
            status=run.status,
            pages_fetched=1,
        )


class PersistedClaimResearch(PersistedZeroClaimResearch):
    def __init__(self, uow_factory: UowFactory) -> None:
        super().__init__(uow_factory)
        self.calls = 0

    async def handle(self, request: ResearchRequest) -> ResearchOutcome:
        assert request.company_id is not None
        self.calls += 1
        async with self._uow_factory() as uow:
            company = await uow.companies.get_by_id(request.company_id)
        assert company is not None and company.website is not None
        run = ResearchRun.start(
            company.name.value,
            company.website.value,
            company_id=company.id,
            output_language=request.output_language,
        )
        run.mark_running()
        run.record_page(
            ResearchPage(
                position=0,
                url=company.website.value,
                final_url=company.website.value,
                http_status=200,
                content_type="text/html",
                fetched_at=utcnow(),
                content_chars=120,
            )
        )
        run.record_extraction(
            profile=ResearchProfile(),
            extractor=ExtractorIdentity(
                provider="fake",
                model="integration-one-claim",
                prompt_version="integration-v1",
            ),
            proposed_count=1,
        )
        run.record_claim(
            ResearchClaim(
                position=0,
                kind="shipping_fit",
                detail="Website confirms ocean FCL container freight",
                evidence_snippet="ocean FCL container freight",
                source_page_position=0,
                confidence=0.9,
            )
        )
        run.complete()
        async with self._uow_factory() as uow:
            await uow.research_runs.add(run)
            await uow.commit()
        return ResearchOutcome(
            action=ResearchAction.COMPLETED,
            company_id=company.id,
            research_id=run.id,
            status=run.status,
            pages_fetched=1,
            claims_extracted=1,
            claims_validated=1,
        )


class StaticNamedContactDiscovery:
    async def discover(self, run: ResearchRun) -> ContactDiscoveryRunOutcome:
        contact = DiscoveredContact(
            name="Maria Chen",
            title="Director of Supply Chain",
            email="maria@integration.example",
            phone="",
            source_url=run.website,
            source_type=DiscoverySourceType.NAMED,
            evidence_snippet="Maria Chen, Director of Supply Chain maria@integration.example",
            confidence=0.9,
        )
        return ContactDiscoveryRunOutcome(
            selection=ContactSelection(
                primary=RankedContact(
                    contact=contact,
                    score=0.9,
                    reasons=("integration fixture",),
                ),
                alternatives=(),
            ),
            pages_scanned=1,
            pages_failed=0,
        )


class ExplodingProspectBatchWorkflow(ProspectBatchWorkflow):
    def __init__(self) -> None:
        pass

    async def execute(
        self,
        batch_id: UUID,
        *,
        sender: SenderProfile | None,
        heartbeat: Callable[[], Awaitable[None]] | None = None,
    ) -> ProspectBatch:
        if heartbeat is not None:
            await heartbeat()
        raise RuntimeError("synthetic worker failure")


def batch_workflow(uow_factory: UowFactory) -> ProspectBatchWorkflow:
    return ProspectBatchWorkflow(
        uow_factory=cast(
            Callable[[], ProspectBatchUnitOfWork],
            uow_factory,
        ),
        research=PersistedZeroClaimResearch(uow_factory),
        opportunity=OpportunityApplicationWorkflow(
            uow_factory,
            DeterministicOpportunityScoringService(),
        ),
        contact_discovery=StaticNamedContactDiscovery(),
        contact_ingestion=ContactIngestionWorkflow(uow_factory),
        decision_maker=DecisionMakerSelectionWorkflow(
            uow_factory,
            DeterministicDecisionMakerSelectionService(),
        ),
        email_draft=EmailDraftGenerationWorkflow(
            uow_factory,
            FakeEmailDraftGenerator(),
        ),
    )


def batch_workflow_with_claim(
    uow_factory: UowFactory,
) -> tuple[ProspectBatchWorkflow, PersistedClaimResearch]:
    research = PersistedClaimResearch(uow_factory)
    return (
        ProspectBatchWorkflow(
            uow_factory=cast(
                Callable[[], ProspectBatchUnitOfWork],
                uow_factory,
            ),
            research=research,
            opportunity=OpportunityApplicationWorkflow(
                uow_factory,
                DeterministicOpportunityScoringService(),
            ),
            contact_discovery=StaticNamedContactDiscovery(),
            contact_ingestion=ContactIngestionWorkflow(uow_factory),
            decision_maker=DecisionMakerSelectionWorkflow(
                uow_factory,
                DeterministicDecisionMakerSelectionService(),
            ),
            email_draft=EmailDraftGenerationWorkflow(
                uow_factory,
                FakeEmailDraftGenerator(),
            ),
        ),
        research,
    )


async def make_client(
    uow_factory: UowFactory,
    workflow: ProspectBatchWorkflow,
) -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(_env_file=None, app_env="development"))
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    app.dependency_overrides[get_prospect_batch_workflow] = lambda: workflow
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def run_pending_job(
    uow_factory: UowFactory,
    workflow: ProspectBatchWorkflow,
) -> None:
    coordinator = ProspectJobCoordinator(
        cast(Callable[[], ProspectBatchUnitOfWork], uow_factory),
        lease_ttl=timedelta(seconds=120),
        retry_delay=timedelta(seconds=0),
    )
    runner = ProspectJobRunner(coordinator=coordinator, batch_workflow=workflow)
    assert await runner.run_once(owner="integration-worker") is True


async def create_discovery_company(
    client: AsyncClient,
    *,
    name: str,
    website: str,
) -> tuple[str, str]:
    csv_content = (
        b"company_name,source_url,website,region,import_evidence\n"
        + f"{name},https://evidence.example/job,{website},US,BOL-JOB\n".encode()
    )
    discovery = await client.post(
        "/api/v1/discovery-tasks/manual-csv",
        data={"prompt": "帮我找 1 家北美五金进口商"},
        files={"file": ("job.csv", csv_content, "text/csv")},
    )
    assert discovery.status_code == 201, discovery.text
    task_id = discovery.json()["task_id"]
    companies = await client.get(f"/api/v1/discovery-tasks/{task_id}/companies")
    return task_id, companies.json()["companies"][0]["company_id"]


async def test_batch_api_persists_completed_results_and_refreshes(
    uow_factory: UowFactory,
) -> None:
    workflow = batch_workflow(uow_factory)
    csv_content = (
        b"company_name,source_url,website,region,import_evidence\n"
        b"Atlas Hardware,https://evidence.example/atlas,https://atlas.example,US,BOL-1\n"
    )

    batch_id: str | None = None
    company_id: str | None = None
    async for client in make_client(uow_factory, workflow):
        discovery = await client.post(
            "/api/v1/discovery-tasks/manual-csv",
            data={"prompt": "帮我找 1 家北美五金进口商"},
            files={"file": ("atlas.csv", csv_content, "text/csv")},
        )
        assert discovery.status_code == 201, discovery.text
        task_id = discovery.json()["task_id"]
        companies = await client.get(f"/api/v1/discovery-tasks/{task_id}/companies")
        company_id = companies.json()["companies"][0]["company_id"]

        outside = await client.post(
            f"/api/v1/discovery-tasks/{task_id}/batch-process",
            json={"company_ids": ["aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa"]},
        )
        assert outside.status_code == 422, outside.text
        assert outside.json()["code"] == "BATCH_COMPANY_OUTSIDE_TASK"

        async with uow_factory() as uow:
            company = await uow.companies.get_by_id(UUID(company_id))
            assert company is not None
            company.add_source(
                SourceReference(
                    source="import_evidence",
                    reference="BOL-INTEGRATION-1",
                    retrieved_at=utcnow(),
                )
            )
            for signal in (
                "import_activity: customs shipments recorded",
                "china_dependency: China origin observed",
                "shipping_fit: ocean FCL container freight",
                "cargo_value_potential: high value cargo",
                "company_scale: warehouse and employees",
                "growth_signal: growing import activity",
                "logistics_complexity: multi-origin distribution centers",
            ):
                company.add_signal(signal)
            await uow.companies.save(company)
            await uow.commit()

        created = await client.post(
            f"/api/v1/discovery-tasks/{task_id}/batch-process",
            json={
                "company_ids": [company_id],
                "limit": 5,
                "sender": {
                    "name": "Alex Morgan",
                    "company": "Harbor Bridge Logistics",
                    "value_proposition": "We simplify Asia-to-US freight.",
                },
            },
        )
        assert created.status_code == 202, created.text
        body = created.json()
        batch_id = body["batch_id"]
        assert body["status"] == "pending"
        assert body["reused"] is False
        execution = await client.get(f"/api/v1/prospect-batches/{batch_id}/execution")
        assert execution.json()["status"] == "pending"

        await run_pending_job(uow_factory, workflow)
        saved_batch = await client.get(f"/api/v1/prospect-batches/{batch_id}")
        results = await client.get(f"/api/v1/prospect-batches/{batch_id}/companies")
        assert results.status_code == 200, results.text
        item = results.json()["companies"][0]
        assert item["error_code"] is None, f"{item['error_code']}: {item['error_summary']}"
        assert saved_batch.json()["status"] == "completed", item
        assert saved_batch.json()["completed_count"] == 1
        assert item["company_id"] == company_id
        assert item["current_stage"] == "completed"
        assert item["research_id"] is not None
        assert item["opportunity_id"] is not None
        assert item["selected_contact_id"] is not None
        assert item["draft_id"] is not None
        assert item["draft_status"] == "generated"

    assert batch_id is not None and company_id is not None
    async for refreshed in make_client(uow_factory, workflow):
        batch = await refreshed.get(f"/api/v1/prospect-batches/{batch_id}")
        assert batch.status_code == 200, batch.text
        assert batch.json()["status"] == "completed"

        results = await refreshed.get(f"/api/v1/prospect-batches/{batch_id}/companies")
        assert results.status_code == 200, results.text
        assert results.json()["companies"][0]["company_id"] == company_id
        execution = await refreshed.get(f"/api/v1/prospect-batches/{batch_id}/execution")
        assert execution.json()["status"] == "completed"


async def test_evidence_review_resume_persists_and_does_not_rerun_research(
    uow_factory: UowFactory,
) -> None:
    workflow, research = batch_workflow_with_claim(uow_factory)
    csv_content = (
        b"company_name,source_url,website,region,import_evidence\n"
        b"Resume Hardware,https://evidence.example/resume,https://resume.example,US,BOL-2\n"
    )

    async for client in make_client(uow_factory, workflow):
        discovery = await client.post(
            "/api/v1/discovery-tasks/manual-csv",
            data={"prompt": "帮我找 1 家北美五金进口商"},
            files={"file": ("resume.csv", csv_content, "text/csv")},
        )
        assert discovery.status_code == 201, discovery.text
        task_id = discovery.json()["task_id"]
        companies = await client.get(f"/api/v1/discovery-tasks/{task_id}/companies")
        company_id = companies.json()["companies"][0]["company_id"]

        async with uow_factory() as uow:
            company = await uow.companies.get_by_id(UUID(company_id))
            assert company is not None
            company.add_source(
                SourceReference(
                    source="import_evidence",
                    reference="BOL-INTEGRATION-2",
                    retrieved_at=utcnow(),
                )
            )
            for signal in (
                "import_activity: customs shipments recorded",
                "china_dependency: China origin observed",
                "cargo_value_potential: high value cargo",
                "company_scale: warehouse and employees",
                "growth_signal: growing import activity",
                "logistics_complexity: multi-origin distribution centers",
            ):
                company.add_signal(signal)
            await uow.companies.save(company)
            await uow.commit()

        created = await client.post(
            f"/api/v1/discovery-tasks/{task_id}/batch-process",
            json={
                "company_ids": [company_id],
                "sender": {
                    "name": "Alex Morgan",
                    "company": "Harbor Bridge Logistics",
                    "value_proposition": "We simplify Asia-to-US freight.",
                },
            },
        )
        assert created.status_code == 202, created.text
        batch_id = created.json()["batch_id"]
        await run_pending_job(uow_factory, workflow)
        before = await client.get(f"/api/v1/prospect-batches/{batch_id}/companies")
        item = before.json()["companies"][0]
        research_id = item["research_id"]
        assert item["current_stage"] == "awaiting_evidence_review"
        assert item["blocking_claim_count"] == 1

        blockers = await client.get(
            f"/api/v1/prospect-batches/{batch_id}/companies/{company_id}/blockers"
        )
        assert blockers.status_code == 200, blockers.text
        assert blockers.json()["pending_claim_count"] == 1
        assert blockers.json()["claims"][0]["status"] == "pending"

        premature = await client.post(
            f"/api/v1/prospect-batches/{batch_id}/companies/{company_id}/resume",
            json={"sender": None},
        )
        assert premature.status_code == 409, premature.text
        assert premature.json()["code"] == "EVIDENCE_REVIEW_INCOMPLETE"
        assert premature.json()["pending_claim_count"] == 1

        confirmed = await client.post(
            f"/api/v1/research/runs/{research_id}/confirm",
            json={
                "reviewer_name": "Integration Reviewer",
                "decisions": [{"claim_position": 0, "decision": "accepted"}],
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["summary"]["accepted"] == 1

        reviewed = await client.get(
            f"/api/v1/prospect-batches/{batch_id}/companies/{company_id}/blockers"
        )
        assert reviewed.json()["pending_claim_count"] == 0
        assert reviewed.json()["claims"][0]["status"] == "accepted"

        resumed = await client.post(
            f"/api/v1/prospect-batches/{batch_id}/companies/{company_id}/resume",
            json={
                "sender": {
                    "name": "Alex Morgan",
                    "company": "Harbor Bridge Logistics",
                    "value_proposition": "We simplify Asia-to-US freight.",
                }
            },
        )
        assert resumed.status_code == 202, resumed.text
        assert resumed.json()["status"] == "pending"
        await run_pending_job(uow_factory, workflow)
        saved_batch = await client.get(f"/api/v1/prospect-batches/{batch_id}")
        assert saved_batch.json()["completed_count"] == 1
        assert saved_batch.json()["needs_review_count"] == 0
        after = await client.get(f"/api/v1/prospect-batches/{batch_id}/companies")
        completed = after.json()["companies"][0]
        assert completed["current_stage"] == "completed"
        assert completed["resume_count"] == 1
        assert completed["resumed_from_stage"] == "awaiting_evidence_review"
        assert completed["resumed_at"] is not None
        assert completed["draft_status"] == "generated"
        assert research.calls == 1

        duplicate = await client.post(
            f"/api/v1/prospect-batches/{batch_id}/companies/{company_id}/resume",
            json={"sender": None},
        )
        assert duplicate.status_code == 409, duplicate.text
        assert research.calls == 1


async def test_create_returns_202_is_idempotent_and_does_not_run_research(
    uow_factory: UowFactory,
) -> None:
    workflow, research = batch_workflow_with_claim(uow_factory)
    async for client in make_client(uow_factory, workflow):
        task_id, company_id = await create_discovery_company(
            client,
            name="Idempotent Hardware",
            website="https://idempotent.example",
        )
        path = f"/api/v1/discovery-tasks/{task_id}/batch-process"
        payload = {"company_ids": [company_id]}
        first = await client.post(path, json=payload, headers={"Idempotency-Key": "same-click"})
        second = await client.post(path, json=payload, headers={"Idempotency-Key": "same-click"})
        equivalent = await client.post(
            path,
            json=payload,
            headers={"Idempotency-Key": "different-click"},
        )

        assert first.status_code == 202, first.text
        assert second.status_code == 202, second.text
        assert equivalent.status_code == 202, equivalent.text
        assert first.json()["reused"] is False
        assert second.json()["reused"] is True
        assert equivalent.json()["reused"] is True
        assert first.json()["batch_id"] == second.json()["batch_id"]
        assert first.json()["job_id"] == equivalent.json()["job_id"]
        assert research.calls == 0
        companies = await client.get(
            f"/api/v1/prospect-batches/{first.json()['batch_id']}/companies"
        )
        assert companies.json()["companies"][0]["research_id"] is None


async def test_historical_batch_without_job_returns_null_execution(
    uow_factory: UowFactory,
) -> None:
    workflow = batch_workflow(uow_factory)
    async for client in make_client(uow_factory, workflow):
        task_id, company_id = await create_discovery_company(
            client,
            name="Historical Hardware",
            website="https://historical.example",
        )
        batch = await workflow.create(
            UUID(task_id),
            CreateProspectBatchCommand(company_ids=(UUID(company_id),)),
        )

        execution = await client.get(f"/api/v1/prospect-batches/{batch.id}/execution")
        assert execution.status_code == 200, execution.text
        assert execution.json() is None


async def test_unhandled_worker_error_retries_then_fails_with_structured_error(
    uow_factory: UowFactory,
) -> None:
    workflow = batch_workflow(uow_factory)
    async for client in make_client(uow_factory, workflow):
        task_id, company_id = await create_discovery_company(
            client,
            name="Worker Failure Hardware",
            website="https://worker-failure.example",
        )
        created = await client.post(
            f"/api/v1/discovery-tasks/{task_id}/batch-process",
            json={"company_ids": [company_id]},
        )
        assert created.status_code == 202, created.text
        batch_id = created.json()["batch_id"]

        coordinator = ProspectJobCoordinator(
            cast(Callable[[], ProspectBatchUnitOfWork], uow_factory),
            lease_ttl=timedelta(seconds=120),
            retry_delay=timedelta(0),
        )
        runner = ProspectJobRunner(
            coordinator=coordinator,
            batch_workflow=ExplodingProspectBatchWorkflow(),
        )

        assert await runner.run_once(owner="failing-worker-1") is True
        retrying = await client.get(f"/api/v1/prospect-batches/{batch_id}/execution")
        assert retrying.json()["status"] == "pending"
        assert retrying.json()["attempt_count"] == 1
        assert retrying.json()["last_error_code"] == "UNHANDLED_RUNTIMEERROR"
        assert retrying.json()["last_error_summary"] == "RuntimeError"

        assert await runner.run_once(owner="failing-worker-2") is True
        assert await runner.run_once(owner="failing-worker-3") is True
        failed = await client.get(f"/api/v1/prospect-batches/{batch_id}/execution")
        assert failed.json()["status"] == "failed"
        assert failed.json()["attempt_count"] == 3
        companies = await client.get(f"/api/v1/prospect-batches/{batch_id}/companies")
        assert companies.json()["companies"][0]["status"] == "failed"


async def test_two_workers_claim_once_and_expired_leases_recover_or_fail(
    uow_factory: UowFactory,
) -> None:
    workflow = batch_workflow(uow_factory)
    async for client in make_client(uow_factory, workflow):
        task_id, company_id = await create_discovery_company(
            client,
            name="Lease Hardware",
            website="https://lease.example",
        )
        created = await client.post(
            f"/api/v1/discovery-tasks/{task_id}/batch-process",
            json={"company_ids": [company_id]},
        )
        batch_id = created.json()["batch_id"]
        coordinator = ProspectJobCoordinator(
            cast(Callable[[], ProspectBatchUnitOfWork], uow_factory),
            lease_ttl=timedelta(milliseconds=1),
            retry_delay=timedelta(0),
        )

        first = await coordinator.claim(owner="worker-a")
        assert first is not None
        assert await coordinator.claim(owner="worker-b") is None
        await coordinator.start(first.id, owner="worker-a")

        for attempt in range(1, 4):
            await asyncio.sleep(0.01)
            recovered = await coordinator.recover_stale()
            assert len(recovered) == 1
            current = recovered[0]
            assert current.recovery_count == attempt
            if attempt < 3:
                assert current.status.value == "pending"
                leased = await coordinator.claim(owner=f"worker-{attempt + 1}")
                assert leased is not None
                await coordinator.start(leased.id, owner=f"worker-{attempt + 1}")
            else:
                assert current.status.value == "failed"

        execution = await client.get(f"/api/v1/prospect-batches/{batch_id}/execution")
        assert execution.json()["status"] == "failed"
        batch = await client.get(f"/api/v1/prospect-batches/{batch_id}")
        assert batch.json()["running_count"] == 0
        companies = await client.get(f"/api/v1/prospect-batches/{batch_id}/companies")
        assert companies.json()["companies"][0]["status"] == "failed"


async def test_stale_job_does_not_restart_awaiting_evidence_review(
    uow_factory: UowFactory,
) -> None:
    workflow, research = batch_workflow_with_claim(uow_factory)
    async for client in make_client(uow_factory, workflow):
        task_id, company_id = await create_discovery_company(
            client,
            name="Review Lease Hardware",
            website="https://review-lease.example",
        )
        created = await client.post(
            f"/api/v1/discovery-tasks/{task_id}/batch-process",
            json={"company_ids": [company_id]},
        )
        batch_id = created.json()["batch_id"]
        coordinator = ProspectJobCoordinator(
            cast(Callable[[], ProspectBatchUnitOfWork], uow_factory),
            lease_ttl=timedelta(milliseconds=1),
            retry_delay=timedelta(0),
        )
        leased = await coordinator.claim(owner="crashed-worker")
        assert leased is not None
        running = await coordinator.start(leased.id, owner="crashed-worker")
        await workflow.execute(running.batch_id, sender=None)
        assert research.calls == 1

        await asyncio.sleep(0.01)
        recovered = await coordinator.recover_stale()
        assert recovered[0].status.value == "completed"
        assert recovered[0].recovery_count == 1
        companies = await client.get(f"/api/v1/prospect-batches/{batch_id}/companies")
        item = companies.json()["companies"][0]
        assert item["current_stage"] == "awaiting_evidence_review"
        assert item["status"] == "needs_review"
        assert research.calls == 1


async def test_postgres_skip_locked_allows_only_one_concurrent_worker_claim(
    engine: AsyncEngine,
) -> None:
    session_factory = create_session_factory(engine)

    def direct_uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    typed_factory = direct_uow_factory
    workflow = batch_workflow(typed_factory)
    async for client in make_client(typed_factory, workflow):
        task_id, company_id = await create_discovery_company(
            client,
            name="Concurrent Claim Hardware",
            website="https://concurrent-claim.example",
        )
        created = await client.post(
            f"/api/v1/discovery-tasks/{task_id}/batch-process",
            json={"company_ids": [company_id]},
        )
        assert created.status_code == 202, created.text

    coordinator_a = ProspectJobCoordinator(
        cast(Callable[[], ProspectBatchUnitOfWork], typed_factory),
        lease_ttl=timedelta(seconds=120),
        retry_delay=timedelta(0),
    )
    coordinator_b = ProspectJobCoordinator(
        cast(Callable[[], ProspectBatchUnitOfWork], typed_factory),
        lease_ttl=timedelta(seconds=120),
        retry_delay=timedelta(0),
    )
    claims = await asyncio.gather(
        coordinator_a.claim(owner="concurrent-a"),
        coordinator_b.claim(owner="concurrent-b"),
    )
    assert sum(job is not None for job in claims) == 1

    # This concurrency test deliberately uses independent committed sessions
    # instead of the per-test savepoint fixture. Remove only its own fixture
    # records so later integration tests still start from an isolated database.
    async with engine.begin() as connection:
        await connection.execute(delete(TaskModel).where(TaskModel.id == UUID(task_id)))
        await connection.execute(
            delete(CompanyModel).where(CompanyModel.id == UUID(company_id))
        )
