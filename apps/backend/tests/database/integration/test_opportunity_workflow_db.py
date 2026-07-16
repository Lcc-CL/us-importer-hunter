"""Company → Opportunity end-to-end against real PostgreSQL:
ingestion event → deterministic scoring → persisted judgment."""

from uuid import UUID, uuid4

import pytest

from app.domain.events import CompanyFactsChanged, CompanyIngested
from app.domain.services import OpportunityScoringInput
from app.domain.values import (
    OpportunityAssessment,
)
from app.services.scoring import DeterministicOpportunityScoringService
from app.workflows.opportunity import (
    OpportunityApplicationWorkflow,
    OpportunityProcessingAction,
)
from tests.database.integration.conftest import UowFactory
from tests.database.integration.test_repositories import make_source, persist_company

USER_ID = uuid4()


@pytest.fixture
def workflow(uow_factory: UowFactory) -> OpportunityApplicationWorkflow:
    return OpportunityApplicationWorkflow(
        uow_factory=uow_factory, scoring_service=DeterministicOpportunityScoringService()
    )


def ingested(company_id: UUID) -> CompanyIngested:
    return CompanyIngested(company_id=company_id, ingestion_result="created", source="importyeti")


class TestEndToEnd:
    async def test_first_event_creates_persisted_opportunity(
        self, workflow: OpportunityApplicationWorkflow, uow_factory: UowFactory
    ) -> None:
        company = await persist_company(uow_factory)
        outcome = await workflow.handle(ingested(company.id), user_id=USER_ID)
        assert outcome.action is OpportunityProcessingAction.CREATED

        async with uow_factory() as uow:
            assert outcome.opportunity_id is not None
            stored = await uow.opportunities.get_by_id(outcome.opportunity_id)
        assert stored is not None
        assert len(stored.history) == 1
        latest = stored.history[0]
        assert latest.scoring_version == "mvp-deterministic-v1"
        assert latest.priority is not None  # new columns round-trip
        assert latest.assessed_by == "DeterministicOpportunityScoringService"
        assert stored.drain_events() == ()  # reload never revives old events

    async def test_replayed_event_does_not_duplicate(
        self, workflow: OpportunityApplicationWorkflow, uow_factory: UowFactory
    ) -> None:
        company = await persist_company(uow_factory)
        created = await workflow.handle(ingested(company.id), user_id=USER_ID)
        replay = await workflow.handle(ingested(company.id), user_id=USER_ID)

        assert replay.action is OpportunityProcessingAction.SKIPPED
        async with uow_factory() as uow:
            assert created.opportunity_id is not None
            stored = await uow.opportunities.get_by_id(created.opportunity_id)
            same = await uow.opportunities.get_for_company_and_user(company.id, USER_ID)
        assert stored is not None and len(stored.history) == 1
        assert same is not None and same.id == created.opportunity_id

    async def test_new_facts_append_without_touching_history(
        self, workflow: OpportunityApplicationWorkflow, uow_factory: UowFactory
    ) -> None:
        company = await persist_company(uow_factory)
        created = await workflow.handle(ingested(company.id), user_id=USER_ID)

        # facts change: a growth signal arrives
        async with uow_factory() as uow:
            loaded = await uow.companies.get_by_id(company.id)
            assert loaded is not None
            loaded.add_signal("import volume growing")
            await uow.companies.save(loaded)
            await uow.commit()

        changed = CompanyFactsChanged(
            company_id=company.id, changed_fields=("signals",), reason="growth signal observed"
        )
        outcome = await workflow.handle(changed, user_id=USER_ID)

        assert outcome.action is OpportunityProcessingAction.REASSESSED
        async with uow_factory() as uow:
            assert created.opportunity_id is not None
            stored = await uow.opportunities.get_by_id(created.opportunity_id)
        assert stored is not None
        assert len(stored.history) == 2
        first, second = stored.history
        assert first.scoring_version == "mvp-deterministic-v1"  # untouched
        assert second.new_score.value > first.new_score.value  # signals added points

    async def test_scorer_crash_rolls_back_everything(self, uow_factory: UowFactory) -> None:
        company = await persist_company(uow_factory)

        class ExplodingScorer:
            @property
            def scoring_version(self) -> str:
                return "boom-v1"

            async def assess(
                self, scoring_input: OpportunityScoringInput
            ) -> OpportunityAssessment:
                raise RuntimeError("boom")

        workflow = OpportunityApplicationWorkflow(
            uow_factory=uow_factory, scoring_service=ExplodingScorer()
        )
        with pytest.raises(RuntimeError, match="boom"):
            await workflow.handle(ingested(company.id), user_id=USER_ID)

        async with uow_factory() as uow:
            assert await uow.opportunities.get_for_company_and_user(company.id, USER_ID) is None


class TestChainedFromIngestion:
    async def test_ingestion_event_feeds_opportunity_workflow(
        self, workflow: OpportunityApplicationWorkflow, uow_factory: UowFactory
    ) -> None:
        """The full L7→L8 chain: discovery claim → company → judgment."""
        from app.domain.discovery import DiscoveryResult, RawCompanySnapshot
        from app.domain.events import CompanyDiscovered
        from app.workflows.company_ingestion import CompanyIngestionWorkflow

        ingestion = CompanyIngestionWorkflow(uow_factory=uow_factory)
        snapshot = RawCompanySnapshot(
            name_text="Great Lakes Auto Parts LLC",
            source=make_source(),
            website_text="glautoparts.com",
        )
        ingest_outcome = await ingestion.handle(
            CompanyDiscovered(run_id=uuid4(), result=DiscoveryResult(snapshot=snapshot))
        )
        assert ingest_outcome.event is not None

        outcome = await workflow.handle(ingest_outcome.event, user_id=USER_ID)
        assert outcome.action is OpportunityProcessingAction.CREATED
        assert outcome.score is not None and 0.0 <= outcome.score <= 100.0
