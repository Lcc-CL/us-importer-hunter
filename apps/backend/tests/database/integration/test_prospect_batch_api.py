"""D2a API persistence and refresh recovery on PostgreSQL."""

from collections.abc import AsyncIterator, Callable
from typing import cast
from uuid import UUID

from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    get_prospect_batch_workflow,
    get_uow_factory,
)
from app.core.config import Settings
from app.domain.clock import utcnow
from app.domain.repositories import ProspectBatchUnitOfWork
from app.domain.research import (
    ExtractorIdentity,
    ResearchPage,
    ResearchProfile,
    ResearchRun,
)
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
from app.workflows.prospect_batch import ProspectBatchWorkflow
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
        assert created.status_code == 201, created.text
        body = created.json()
        batch_id = body["batch_id"]
        results = await client.get(f"/api/v1/prospect-batches/{batch_id}/companies")
        assert results.status_code == 200, results.text
        item = results.json()["companies"][0]
        assert item["error_code"] is None, f"{item['error_code']}: {item['error_summary']}"
        assert body["status"] == "completed", item
        assert body["completed_count"] == 1
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
