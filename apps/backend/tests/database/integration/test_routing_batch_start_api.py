"""D5d1 routing-source batch start, provenance and provider safety on PostgreSQL."""

import asyncio
import dataclasses
import hashlib
from collections import Counter
from collections.abc import AsyncIterator, Callable
from time import perf_counter
from typing import cast
from uuid import UUID

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.deps import get_prospect_batch_workflow, get_uow_factory
from app.core.config import Settings
from app.database.models.company import CompanyModel
from app.database.models.discovery_task import DiscoveryTaskModel
from app.database.models.import_resolution import ImportEntityDecisionModel
from app.database.models.opportunity import OpportunityModel
from app.database.models.outreach import EmailDraftModel, OutcomeModel, OutreachModel
from app.database.models.prospect_batch import ProspectBatchJobModel, ProspectBatchModel
from app.database.models.prospect_routing import ProspectRouteModel
from app.database.session import create_session_factory
from app.database.uow import SqlAlchemyUnitOfWork
from app.domain.clock import utcnow
from app.domain.repositories import ProspectBatchUnitOfWork
from app.domain.research import ResearchRun
from app.domain.services import OpportunityScoringInput
from app.domain.values import OpportunityAssessment, SourceReference
from app.main import create_app
from app.services.contact import DeterministicDecisionMakerSelectionService
from app.services.contact_discovery import ContactSelection
from app.services.contact_discovery_runner import ContactDiscoveryRunOutcome
from app.services.email import FakeEmailDraftGenerator
from app.services.scoring import DeterministicOpportunityScoringService
from app.workflows.contact_ingestion import ContactIngestionWorkflow
from app.workflows.decision_maker import DecisionMakerSelectionWorkflow
from app.workflows.email import EmailDraftGenerationWorkflow
from app.workflows.opportunity import OpportunityApplicationWorkflow
from app.workflows.prospect_batch import ProspectBatchWorkflow
from app.workflows.research import ResearchOutcome, ResearchRequest
from tests.database.integration.conftest import UowFactory
from tests.database.integration.test_prospect_batch_api import (
    PersistedClaimResearch,
    PersistedZeroClaimResearch,
    StaticNamedContactDiscovery,
    batch_workflow,
    batch_workflow_with_claim,
    create_discovery_company,
    run_pending_job,
)
from tests.database.integration.test_prospect_routing_api import make_runner

FITNESS_MAPPING = (
    '{"company_name":"company","external_company_id":"external_id",'
    '"website":"website","address":"address","company_type":"company_type",'
    '"country":"country","contact_name":"contact","contact_email":"email",'
    '"contact_title":"title","product_description":"product","hs_code":"hs",'
    '"shipment_date":"date","origin_country":"origin","pol":"pol","pod":"pod",'
    '"amount":"amount","last_import_at":"last_import"}'
)
FITNESS_HEADER = (
    "company,external_id,website,address,company_type,country,contact,email,title,"
    "product,hs,date,origin,pol,pod,amount,last_import"
)


def fitness_company_rows(
    *,
    name: str,
    external_id: str,
    website: str,
    address: str,
    contact: str,
    email: str,
    title: str,
) -> list[str]:
    # A-tier under real-routing-v1.1: fitness target + US importer country +
    # China shipment origin + import value + recency + usable contact.
    return [
        (
            f"{name},{external_id},{website},{address},importer,United States,"
            f"{contact},{email},{title},fitness equipment,950691,2026-07-01,"
            "China,Shanghai,Los Angeles,118000,2026-07-01"
        )
    ]


async def make_client(
    uow_factory: UowFactory,
    workflow: ProspectBatchWorkflow,
    *,
    settings: Settings | None = None,
) -> AsyncIterator[AsyncClient]:
    app = create_app(
        settings or Settings(_env_file=None, app_env="development")
    )
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    app.dependency_overrides[get_prospect_batch_workflow] = lambda: workflow
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


async def create_confirmed_routing_batch(
    client: AsyncClient,
    uow_factory: UowFactory,
    *,
    names: tuple[str, ...],
) -> tuple[str, str, tuple[str, ...]]:
    rows: list[str] = []
    for index, name in enumerate(names, start=1):
        identity = hashlib.sha256(name.encode()).hexdigest()[:12]
        rows.extend(
            fitness_company_rows(
                name=name,
                external_id=f"D5D1-{identity}",
                website=f"d5d1-{identity}.example",
                address=f"{100 + index} D5d1 Way City{index} CA",
                contact=f"Routing Buyer {index}",
                email=f"buyer{index}@d5d1-{identity}.example",
                title="Director of Procurement",
            )
        )
    uploaded = await client.post(
        "/api/v1/import-sessions",
        data={"source": "d5d1_routing_start", "mapping": FITNESS_MAPPING},
        files={
            "file": (
                "d5d1-routing.csv",
                (
                    f"{FITNESS_HEADER}\n" + "\n".join(rows)
                ).encode(),
                "text/csv",
            )
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    session_id = str(uploaded.json()["session_id"])
    runner = make_runner(uow_factory)
    resolved = await client.post(f"/api/v1/import-sessions/{session_id}/resolve")
    assert resolved.status_code == 202, resolved.text
    assert await runner.run_once(owner="d5d1-resolution") is True
    routed = await client.post(
        f"/api/v1/import-sessions/{session_id}/routing-runs",
        json={
            "criteria": {
                "target_product_keywords": ["fitness", "gym equipment"],
                "target_hs_codes": ["9506", "950691"],
                "preferred_origin_countries": ["China"],
                "preferred_pol": ["Shanghai"],
                "preferred_pod": ["Los Angeles"],
            },
            "campaign_name": "D5d1 routing start",
        },
    )
    assert routed.status_code == 202, routed.text
    routing_run_id = str(routed.json()["routing_run_id"])
    assert await runner.run_once(owner="d5d1-routing") is True
    route_page = await client.get(
        f"/api/v1/prospect-routing-runs/{routing_run_id}/routes",
        params={"limit": 20},
    )
    assert route_page.status_code == 200, route_page.text
    routes = cast(list[dict[str, object]], route_page.json()["routes"])
    assert len(routes) == len(names)
    company_id_by_name: dict[str, str] = {}
    for route in routes:
        assert route["recommended_tier"] == "A"
        reviewed = await client.post(
            f"/api/v1/prospect-routes/{route['route_id']}/review",
            json={
                "action": "confirm",
                "reviewed_by": "D5d1 Integration Reviewer",
            },
        )
        assert reviewed.status_code == 200, reviewed.text
        company_id_by_name[str(route["company_name"])] = str(route["company_id"])
    company_ids = [company_id_by_name[name] for name in names]
    created = await client.post(
        f"/api/v1/prospect-routing-runs/{routing_run_id}/prospect-batches",
        json={"company_ids": company_ids},
    )
    assert created.status_code == 201, created.text
    return str(created.json()["batch_id"]), routing_run_id, tuple(company_ids)


async def add_qualified_company_signals(
    uow_factory: UowFactory,
    company_id: UUID,
) -> None:
    async with uow_factory() as uow:
        company = await uow.companies.get_by_id(company_id)
        assert company is not None
        company.add_source(
            SourceReference(
                source="import_evidence",
                reference=f"D5D1-{company_id}",
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


class ScenarioResearch:
    def __init__(self, uow_factory: UowFactory) -> None:
        self._uow_factory = uow_factory
        self._claim = PersistedClaimResearch(uow_factory)
        self._zero = PersistedZeroClaimResearch(uow_factory)
        self.calls: Counter[str] = Counter()

    async def handle(self, request: ResearchRequest) -> ResearchOutcome:
        assert request.company_id is not None
        async with self._uow_factory() as uow:
            company = await uow.companies.get_by_id(request.company_id)
        assert company is not None
        company_name = company.name.value
        self.calls[company_name] += 1
        if "Retry" in company_name and self.calls[company_name] == 1:
            raise RuntimeError("synthetic retryable research failure")
        if "Claim" in company_name:
            return await self._claim.handle(request)
        return await self._zero.handle(request)


class ScenarioContactDiscovery:
    def __init__(self) -> None:
        self._default = StaticNamedContactDiscovery()

    async def discover(self, run: ResearchRun) -> ContactDiscoveryRunOutcome:
        if "No Contact" in run.company_name:
            return ContactDiscoveryRunOutcome(
                selection=ContactSelection(primary=None, alternatives=()),
                pages_scanned=1,
                pages_failed=0,
            )
        return await self._default.discover(run)


class ScenarioScoringService:
    def __init__(self) -> None:
        self._default = DeterministicOpportunityScoringService()

    @property
    def scoring_version(self) -> str:
        return self._default.scoring_version

    async def assess(
        self,
        scoring_input: OpportunityScoringInput,
    ) -> OpportunityAssessment:
        if "Insufficient" in scoring_input.company_name:
            scoring_input = dataclasses.replace(scoring_input, signals=())
        return await self._default.assess(scoring_input)


def scenario_batch_workflow(
    uow_factory: UowFactory,
) -> tuple[ProspectBatchWorkflow, ScenarioResearch]:
    research = ScenarioResearch(uow_factory)
    workflow = ProspectBatchWorkflow(
        uow_factory=cast(
            Callable[[], ProspectBatchUnitOfWork],
            uow_factory,
        ),
        research=research,
        opportunity=OpportunityApplicationWorkflow(
            uow_factory,
            ScenarioScoringService(),
        ),
        contact_discovery=ScenarioContactDiscovery(),
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
    return workflow, research


async def test_routing_batch_start_is_explicit_idempotent_and_resumable(
    uow_factory: UowFactory,
) -> None:
    workflow, research = batch_workflow_with_claim(uow_factory)
    async for client in make_client(uow_factory, workflow):
        batch_id, routing_run_id, company_ids = await create_confirmed_routing_batch(
            client,
            uow_factory,
            names=("D5d1 Resumable Hardware",),
        )
        company_id = company_ids[0]
        async with uow_factory() as uow:
            assert uow._session is not None  # noqa: SLF001
            discovery_count_before = await uow._session.scalar(  # noqa: SLF001
                select(func.count()).select_from(DiscoveryTaskModel)
            )
        rejected = await client.post(
            f"/api/v1/prospect-batches/{batch_id}/start",
            json={"confirmation": False, "provider_mode": "configured"},
        )
        assert rejected.status_code == 422, rejected.text
        assert rejected.json()["code"] == "ROUTING_BATCH_CONFIRMATION_REQUIRED"

        started_at = perf_counter()
        started = await client.post(
            f"/api/v1/prospect-batches/{batch_id}/start",
            json={
                "confirmation": True,
                "provider_mode": "configured",
                "note": "approved for deterministic integration processing",
                "sender": {
                    "name": "Alex Morgan",
                    "company": "Harbor Bridge Logistics",
                    "value_proposition": "We simplify Asia-to-US freight.",
                },
            },
        )
        elapsed = perf_counter() - started_at
        assert started.status_code == 202, started.text
        assert elapsed < 1.0
        assert started.json()["processing_started"] is True
        assert started.json()["reused"] is False
        assert research.calls == 0

        repeated = await client.post(
            f"/api/v1/prospect-batches/{batch_id}/start",
            json={"confirmation": True, "provider_mode": "configured"},
        )
        assert repeated.status_code == 202, repeated.text
        assert repeated.json()["reused"] is True
        assert repeated.json()["job_id"] == started.json()["job_id"]

        async with uow_factory() as uow:
            assert uow._session is not None  # noqa: SLF001
            job_count = await uow._session.scalar(  # noqa: SLF001
                select(func.count()).select_from(ProspectBatchJobModel).where(
                    ProspectBatchJobModel.batch_id == UUID(batch_id)
                )
            )
            discovery_count = await uow._session.scalar(  # noqa: SLF001
                select(func.count()).select_from(DiscoveryTaskModel)
            )
            batch_model = await uow._session.get(  # noqa: SLF001
                ProspectBatchModel, UUID(batch_id)
            )
            assert batch_model is not None
            assert batch_model.routing_execution_generation is not None
            batch_discovery_task_id = batch_model.discovery_task_id
            batch_routing_run_id = batch_model.routing_run_id
            batch_routing_generation = batch_model.routing_execution_generation
            route_count = await uow._session.scalar(  # noqa: SLF001
                select(func.count()).select_from(ProspectRouteModel).where(
                    ProspectRouteModel.routing_run_id == UUID(routing_run_id),
                    ProspectRouteModel.execution_generation
                    == batch_routing_generation,
                    ProspectRouteModel.company_id == UUID(company_id),
                )
            )
            decision_count = await uow._session.scalar(  # noqa: SLF001
                select(func.count()).select_from(ImportEntityDecisionModel).where(
                    ImportEntityDecisionModel.candidate_entity_id == UUID(company_id)
                )
            )
        assert job_count == 1
        assert discovery_count == discovery_count_before
        assert batch_discovery_task_id is None
        assert batch_routing_run_id == UUID(routing_run_id)
        assert batch_routing_generation == 1
        assert route_count == 1
        assert decision_count and decision_count > 0

        await add_qualified_company_signals(uow_factory, UUID(company_id))
        await run_pending_job(uow_factory, workflow)
        awaiting = await client.get(
            f"/api/v1/prospect-batches/{batch_id}/companies"
        )
        item = awaiting.json()["companies"][0]
        assert item["current_stage"] == "awaiting_evidence_review"
        assert item["blocking_claim_count"] == 1
        assert item["opportunity_id"] is None

        premature = await client.post(
            f"/api/v1/prospect-batches/{batch_id}/companies/{company_id}/resume",
            json={"sender": None},
        )
        assert premature.status_code == 409, premature.text
        assert premature.json()["code"] == "EVIDENCE_REVIEW_INCOMPLETE"

        confirmed = await client.post(
            f"/api/v1/research/runs/{item['research_id']}/confirm",
            json={
                "reviewer_name": "D5d1 Evidence Reviewer",
                "decisions": [{"claim_position": 0, "decision": "accepted"}],
            },
        )
        assert confirmed.status_code == 200, confirmed.text
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
        await run_pending_job(uow_factory, workflow)
        completed = await client.get(
            f"/api/v1/prospect-batches/{batch_id}/companies"
        )
        completed_item = completed.json()["companies"][0]
        assert completed_item["current_stage"] == "completed"
        assert completed_item["draft_status"] == "generated"
        assert completed_item["resume_count"] == 1
        assert research.calls == 1

        async with uow_factory() as uow:
            assert uow._session is not None  # noqa: SLF001
            opportunity_count = await uow._session.scalar(  # noqa: SLF001
                select(func.count()).select_from(OpportunityModel).where(
                    OpportunityModel.company_id == UUID(company_id)
                )
            )
            draft = await uow._session.scalar(  # noqa: SLF001
                select(EmailDraftModel).join(
                    OutreachModel,
                    OutreachModel.id == EmailDraftModel.outreach_id,
                ).join(
                    OpportunityModel,
                    OpportunityModel.id == OutreachModel.opportunity_id,
                ).where(OpportunityModel.company_id == UUID(company_id))
            )
            outreach = await uow._session.scalar(  # noqa: SLF001
                select(OutreachModel)
                .join(
                    OpportunityModel,
                    OpportunityModel.id == OutreachModel.opportunity_id,
                )
                .where(OpportunityModel.company_id == UUID(company_id))
            )
            outcome_count = await uow._session.scalar(  # noqa: SLF001
                select(func.count())
                .select_from(OutcomeModel)
                .join(
                    OutreachModel,
                    OutreachModel.id == OutcomeModel.outreach_id,
                )
                .join(
                    OpportunityModel,
                    OpportunityModel.id == OutreachModel.opportunity_id,
                )
                .where(OpportunityModel.company_id == UUID(company_id))
            )
            draft_approval_status = draft.approval_status if draft else None
            outreach_sent_version = outreach.sent_version if outreach else None
        assert opportunity_count == 1
        assert draft_approval_status == "generated"
        assert outreach is not None and outreach_sent_version is None
        assert outcome_count == 0


async def test_routing_batch_start_provider_guards_fail_closed(
    uow_factory: UowFactory,
) -> None:
    workflow = batch_workflow(uow_factory)
    async for client in make_client(uow_factory, workflow):
        batch_id, _, _ = await create_confirmed_routing_batch(
            client,
            uow_factory,
            names=("D5d1 Provider Guard Hardware",),
        )

    missing_key = Settings(
        _env_file=None,
        app_env="development",
        research_extractor_provider="openai",
        email_generator_provider="fake",
        openai_api_key="",
    )
    async for client in make_client(
        uow_factory,
        workflow,
        settings=missing_key,
    ):
        unavailable = await client.post(
            f"/api/v1/prospect-batches/{batch_id}/start",
            json={"confirmation": True, "provider_mode": "configured"},
        )
        assert unavailable.status_code == 503, unavailable.text
        assert unavailable.json()["code"] == "provider_unavailable"

    production_fake = Settings(
        _env_file=None,
        app_env="production",
        research_extractor_provider="fake",
        email_generator_provider="fake",
    )
    async for client in make_client(
        uow_factory,
        workflow,
        settings=production_fake,
    ):
        forbidden = await client.post(
            f"/api/v1/prospect-batches/{batch_id}/start",
            json={"confirmation": True, "provider_mode": "configured"},
        )
        assert forbidden.status_code == 503, forbidden.text

    production_deepseek = Settings(
        _env_file=None,
        app_env="production",
        research_extractor_provider="deepseek",
        deepseek_api_key="sk-test-not-real",
        deepseek_model="deepseek-v4-pro",
        deepseek_base_url="https://api.deepseek.com",
        email_generator_provider="deepseek",
    )
    async for client in make_client(
        uow_factory,
        workflow,
        settings=production_deepseek,
    ):
        allowed = await client.post(
            f"/api/v1/prospect-batches/{batch_id}/start",
            json={"confirmation": True, "provider_mode": "configured"},
        )
        assert allowed.status_code == 202, allowed.text

    async with uow_factory() as uow:
        assert uow._session is not None  # noqa: SLF001
        job_count = await uow._session.scalar(  # noqa: SLF001
            select(func.count()).select_from(ProspectBatchJobModel).where(
                ProspectBatchJobModel.batch_id == UUID(batch_id)
            )
        )
    assert job_count == 1


async def test_five_company_routing_smoke_preserves_human_gates_and_recovers_retry(
    uow_factory: UowFactory,
) -> None:
    workflow, research = scenario_batch_workflow(uow_factory)
    names = (
        "Atlas Claim Hardware",
        "Meridian Insufficient Fasteners",
        "Harbor No Contact Tools",
        "Cedar Draft Industrial",
        "Tundra Retry Hardware",
    )
    async for client in make_client(uow_factory, workflow):
        batch_id, _, company_ids = await create_confirmed_routing_batch(
            client,
            uow_factory,
            names=names,
        )
        company_id_by_name = dict(zip(names, company_ids, strict=True))
        for name in (
            names[0],
            names[2],
            names[3],
            names[4],
        ):
            await add_qualified_company_signals(
                uow_factory,
                UUID(company_id_by_name[name]),
            )

        started = await client.post(
            f"/api/v1/prospect-batches/{batch_id}/start",
            json={
                "confirmation": True,
                "provider_mode": "configured",
                "sender": {
                    "name": "Alex Morgan",
                    "company": "Harbor Bridge Logistics",
                    "value_proposition": "We simplify Asia-to-US freight.",
                },
            },
        )
        assert started.status_code == 202, started.text
        await run_pending_job(uow_factory, workflow)
        first_results = await client.get(
            f"/api/v1/prospect-batches/{batch_id}/companies"
        )
        first_by_name = {
            item["company_name"]: item
            for item in first_results.json()["companies"]
        }
        assert len(first_by_name) == 5
        assert first_by_name[names[0]]["current_stage"] == (
            "awaiting_evidence_review"
        )
        assert first_by_name[names[0]]["opportunity_id"] is None
        assert first_by_name[names[1]]["status"] == "needs_review"
        assert first_by_name[names[1]]["draft_id"] is None
        assert first_by_name[names[2]]["error_code"] == "CONTACT_NOT_FOUND"
        assert first_by_name[names[2]]["selected_contact_id"] is None
        assert first_by_name[names[2]]["draft_id"] is None
        assert first_by_name[names[3]]["current_stage"] == "completed", (
            f"{first_by_name[names[3]]['error_code']}: "
            f"{first_by_name[names[3]]['error_summary']}"
        )
        assert first_by_name[names[3]]["draft_status"] == "generated"
        assert first_by_name[names[4]]["error_code"] == "RESEARCH_FAILED"
        assert first_by_name[names[4]]["status"] == "failed"

        claim_company_id = company_id_by_name[names[0]]
        blockers = await client.get(
            f"/api/v1/prospect-batches/{batch_id}/companies/{claim_company_id}/blockers"
        )
        assert blockers.status_code == 200, blockers.text
        assert blockers.json()["pending_claim_count"] == 1
        assert blockers.json()["claims"][0]["status"] == "pending"

        retry_company_id = company_id_by_name[names[4]]
        retried = await client.post(
            f"/api/v1/prospect-batches/{batch_id}/companies/{retry_company_id}/retry",
            json={
                "sender": {
                    "name": "Alex Morgan",
                    "company": "Harbor Bridge Logistics",
                    "value_proposition": "We simplify Asia-to-US freight.",
                }
            },
        )
        assert retried.status_code == 202, retried.text
        await run_pending_job(uow_factory, workflow)

        claim_item = first_by_name[names[0]]
        confirmed = await client.post(
            f"/api/v1/research/runs/{claim_item['research_id']}/confirm",
            json={
                "reviewer_name": "D5d1 Smoke Reviewer",
                "decisions": [{"claim_position": 0, "decision": "accepted"}],
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        resumed = await client.post(
            f"/api/v1/prospect-batches/{batch_id}/companies/{claim_company_id}/resume",
            json={
                "sender": {
                    "name": "Alex Morgan",
                    "company": "Harbor Bridge Logistics",
                    "value_proposition": "We simplify Asia-to-US freight.",
                }
            },
        )
        assert resumed.status_code == 202, resumed.text
        await run_pending_job(uow_factory, workflow)

        final_results = await client.get(
            f"/api/v1/prospect-batches/{batch_id}/companies"
        )
        final_by_name = {
            item["company_name"]: item
            for item in final_results.json()["companies"]
        }
        assert final_by_name[names[0]]["current_stage"] == "completed"
        assert final_by_name[names[4]]["current_stage"] == "completed"
        assert final_by_name[names[4]]["draft_status"] == "generated"
        assert research.calls[names[0]] == 1
        assert research.calls[names[4]] == 2

        saved_batch = await client.get(f"/api/v1/prospect-batches/{batch_id}")
        assert saved_batch.json()["completed_count"] == 3
        assert saved_batch.json()["needs_review_count"] == 2
        assert saved_batch.json()["failed_count"] == 0

    async with uow_factory() as uow:
        assert uow._session is not None  # noqa: SLF001
        smoke_company_ids = tuple(UUID(company_id) for company_id in company_ids)
        company_count = await uow._session.scalar(  # noqa: SLF001
            select(func.count()).select_from(CompanyModel).where(
                CompanyModel.id.in_(smoke_company_ids)
            )
        )
        drafts = list(
            await uow._session.scalars(  # noqa: SLF001
                select(EmailDraftModel)
                .join(
                    OutreachModel,
                    OutreachModel.id == EmailDraftModel.outreach_id,
                )
                .join(
                    OpportunityModel,
                    OpportunityModel.id == OutreachModel.opportunity_id,
                )
                .where(OpportunityModel.company_id.in_(smoke_company_ids))
                .order_by(
                    EmailDraftModel.outreach_id,
                    EmailDraftModel.version,
                )
            )
        )
        outreaches = list(
            await uow._session.scalars(  # noqa: SLF001
                select(OutreachModel)
                .join(
                    OpportunityModel,
                    OpportunityModel.id == OutreachModel.opportunity_id,
                )
                .where(OpportunityModel.company_id.in_(smoke_company_ids))
                .order_by(OutreachModel.id)
            )
        )
        outcome_count = await uow._session.scalar(  # noqa: SLF001
            select(func.count())
            .select_from(OutcomeModel)
            .join(
                OutreachModel,
                OutreachModel.id == OutcomeModel.outreach_id,
            )
            .join(
                OpportunityModel,
                OpportunityModel.id == OutreachModel.opportunity_id,
            )
            .where(OpportunityModel.company_id.in_(smoke_company_ids))
        )
        draft_statuses = [draft.approval_status for draft in drafts]
        sent_versions = [outreach.sent_version for outreach in outreaches]
    assert company_count == 5
    assert draft_statuses == ["generated", "generated", "generated"]
    assert sent_versions == [None, None, None]
    assert outcome_count == 0


async def test_routing_batch_concurrent_start_creates_one_job_and_discovery_stays_compatible(
    engine: AsyncEngine,
) -> None:
    session_factory = create_session_factory(engine)

    def direct_uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    uow_factory = direct_uow_factory
    workflow = batch_workflow(uow_factory)
    async for client in make_client(uow_factory, workflow):
        batch_id, _, _ = await create_confirmed_routing_batch(
            client,
            uow_factory,
            names=("D5d1 Concurrent Hardware",),
        )
        path = f"/api/v1/prospect-batches/{batch_id}/start"
        first, second = await asyncio.gather(
            client.post(
                path,
                json={"confirmation": True, "provider_mode": "configured"},
            ),
            client.post(
                path,
                json={"confirmation": True, "provider_mode": "configured"},
            ),
        )
        assert first.status_code == 202, first.text
        assert second.status_code == 202, second.text
        assert first.json()["job_id"] == second.json()["job_id"]
        assert sorted((first.json()["reused"], second.json()["reused"])) == [
            False,
            True,
        ]

        task_id, company_id = await create_discovery_company(
            client,
            name="D5d1 Discovery Regression",
            website="https://d5d1-discovery.example",
        )
        discovery_started = await client.post(
            f"/api/v1/discovery-tasks/{task_id}/batch-process",
            json={"company_ids": [company_id]},
        )
        assert discovery_started.status_code == 202, discovery_started.text
        wrong_endpoint = await client.post(
            f"/api/v1/prospect-batches/{discovery_started.json()['batch_id']}/start",
            json={"confirmation": True, "provider_mode": "configured"},
        )
        assert wrong_endpoint.status_code == 409, wrong_endpoint.text

    async with uow_factory() as uow:
        assert uow._session is not None  # noqa: SLF001
        routing_job_count = await uow._session.scalar(  # noqa: SLF001
            select(func.count()).select_from(ProspectBatchJobModel).where(
                ProspectBatchJobModel.batch_id == UUID(batch_id)
            )
        )
    assert routing_job_count == 1


async def test_routing_batch_start_revalidates_reviewed_effective_a_routes(
    uow_factory: UowFactory,
) -> None:
    workflow = batch_workflow(uow_factory)
    async for client in make_client(uow_factory, workflow):
        batch_id, routing_run_id, company_ids = await create_confirmed_routing_batch(
            client,
            uow_factory,
            names=("D5d1 Route Guard Hardware",),
        )
        company_id = UUID(company_ids[0])
        async with uow_factory() as uow:
            assert uow._session is not None  # noqa: SLF001
            route_id = await uow._session.scalar(  # noqa: SLF001
                select(ProspectRouteModel.id).where(
                    ProspectRouteModel.routing_run_id == UUID(routing_run_id),
                    ProspectRouteModel.company_id == company_id,
                )
            )
            assert route_id is not None
            await uow._session.execute(  # noqa: SLF001
                update(ProspectRouteModel)
                .where(ProspectRouteModel.id == route_id)
                .values(
                    review_status="suggested",
                    override_reason=None,
                    reviewed_by=None,
                    reviewed_at=None,
                )
            )
            await uow.commit()

        unconfirmed = await client.post(
            f"/api/v1/prospect-batches/{batch_id}/start",
            json={"confirmation": True, "provider_mode": "configured"},
        )
        assert unconfirmed.status_code == 409, unconfirmed.text

        async with uow_factory() as uow:
            assert uow._session is not None  # noqa: SLF001
            await uow._session.execute(  # noqa: SLF001
                update(ProspectRouteModel)
                .where(ProspectRouteModel.id == route_id)
                .values(
                    effective_tier="B",
                    review_status="overridden",
                    override_reason="integration non-A guard",
                    reviewed_by="D5d1 Integration Reviewer",
                    reviewed_at=utcnow(),
                )
            )
            await uow.commit()

        non_a = await client.post(
            f"/api/v1/prospect-batches/{batch_id}/start",
            json={"confirmation": True, "provider_mode": "configured"},
        )
        assert non_a.status_code == 409, non_a.text

        async with uow_factory() as uow:
            assert uow._session is not None  # noqa: SLF001
            await uow._session.execute(  # noqa: SLF001
                update(ProspectRouteModel)
                .where(ProspectRouteModel.id == route_id)
                .values(
                    recommended_tier=None,
                    effective_tier=None,
                    review_status="blocked",
                    override_reason=None,
                    reviewed_by=None,
                    reviewed_at=None,
                )
            )
            await uow.commit()

        blocked = await client.post(
            f"/api/v1/prospect-batches/{batch_id}/start",
            json={"confirmation": True, "provider_mode": "configured"},
        )
        assert blocked.status_code == 409, blocked.text

    async with uow_factory() as uow:
        assert uow._session is not None  # noqa: SLF001
        job_count = await uow._session.scalar(  # noqa: SLF001
            select(func.count()).select_from(ProspectBatchJobModel).where(
                ProspectBatchJobModel.batch_id == UUID(batch_id)
            )
        )
    assert job_count == 0
