"""OpportunityApplicationWorkflow unit tests — fakes only, no database.

The workflow orchestrates; the fake scorer proves it never computes a
score itself and can be swapped freely (replaceable strategy).
"""

from datetime import UTC, datetime
from types import TracebackType
from uuid import UUID, uuid4

import pytest

from app.domain.company import Company
from app.domain.events import CompanyFactsChanged, CompanyIngested
from app.domain.exceptions import DuplicateOperation
from app.domain.opportunity import Opportunity
from app.domain.repositories import (
    CompanyRepository,
    ContactRepository,
    OpportunityRepository,
    OutreachRepository,
    ResearchRunRepository,
    TaskRepository,
)
from app.domain.services import OpportunityScoringInput
from app.domain.values import (
    CompanyName,
    Confidence,
    DataCompleteness,
    DimensionAssessment,
    DimensionStatus,
    OpportunityAssessment,
    OpportunityScore,
    Priority,
    QualificationDecision,
    ScoreBreakdown,
    ScoringDimension,
    SourceReference,
    WebsiteUrl,
)
from app.workflows.opportunity import (
    OpportunityApplicationWorkflow,
    OpportunityProcessingAction,
)

USER_ID = uuid4()


class FakeCompanyRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Company] = {}

    async def get_by_id(self, company_id: UUID) -> Company | None:
        return self.items.get(company_id)

    async def add(self, company: Company) -> None:
        self.items[company.id] = company

    async def save(self, company: Company) -> None:
        self.items[company.id] = company

    async def exists(self, company_id: UUID) -> bool:
        return company_id in self.items

    async def find_by_normalized_name(self, name: CompanyName) -> Company | None:
        return None

    async def find_by_website_host(self, host: str) -> Company | None:
        return None


class FakeOpportunityRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Opportunity] = {}
        self.added: list[UUID] = []
        self.saved: list[UUID] = []

    async def get_by_id(self, opportunity_id: UUID) -> Opportunity | None:
        return self.items.get(opportunity_id)

    async def add(self, opportunity: Opportunity) -> None:
        self.items[opportunity.id] = opportunity
        self.added.append(opportunity.id)

    async def save(self, opportunity: Opportunity) -> None:
        self.items[opportunity.id] = opportunity
        self.saved.append(opportunity.id)

    async def get_for_company_and_user(
        self, company_id: UUID, user_id: UUID
    ) -> Opportunity | None:
        matches = [
            o
            for o in self.items.values()
            if o.company_id == company_id and o.user_id == user_id
        ]
        return matches[0] if matches else None


class FakeUnitOfWork:
    companies: CompanyRepository
    opportunities: OpportunityRepository
    outreaches: OutreachRepository
    contacts: ContactRepository
    tasks: TaskRepository
    research_runs: ResearchRunRepository

    def __init__(
        self, companies: FakeCompanyRepository, opportunities: FakeOpportunityRepository
    ) -> None:
        self.companies = companies
        self.opportunities = opportunities
        self.committed = 0
        self.commit_error: Exception | None = None  # raised once, then cleared

    async def __aenter__(self) -> "FakeUnitOfWork":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        if self.commit_error is not None:
            error, self.commit_error = self.commit_error, None
            raise error
        self.committed += 1

    async def rollback(self) -> None:
        pass


def make_fake_assessment(score: float = 75.0) -> OpportunityAssessment:
    breakdown = ScoreBreakdown.from_dimensions(
        (
            DimensionAssessment(
                dimension=ScoringDimension.IMPORT_ACTIVITY,
                weight=100.0,
                status=DimensionStatus.UNKNOWN,
                earned_score=0.0,
                reasons=("fake breakdown",),
            ),
        )
    )
    return OpportunityAssessment(
        new_score=OpportunityScore(score),
        confidence=Confidence(0.8),
        data_completeness=DataCompleteness(0.6),
        qualification_decision=QualificationDecision.REVIEW,
        score_breakdown=breakdown,
        reasons=(f"fake rule fired at {score:g}",),
        priority=Priority.HIGH,
        recommended_action="human_review",
        assessed_by="FakeScoringService",
        scoring_version="fake-v1",
        policy_version="fake-policy-v1",
    )


class FakeScoringService:
    """Swappable strategy stand-in: fixed assessment, or a crash."""

    def __init__(
        self, assessment: OpportunityAssessment | None = None, error: Exception | None = None
    ) -> None:
        self._assessment = assessment or make_fake_assessment()
        self._error = error
        self.calls: list[OpportunityScoringInput] = []

    @property
    def scoring_version(self) -> str:
        return "fake-v1"

    async def assess(self, scoring_input: OpportunityScoringInput) -> OpportunityAssessment:
        self.calls.append(scoring_input)
        if self._error is not None:
            raise self._error
        return self._assessment


def make_company(*, with_source: bool = True) -> Company:
    company = Company.create(CompanyName("Pacific Home Goods Inc."), WebsiteUrl("https://phg.com"))
    if with_source:
        company.add_source(
            SourceReference(
                source="importyeti",
                reference="https://ref/1",
                retrieved_at=datetime(2026, 7, 1, tzinfo=UTC),
            )
        )
    company.drain_events()
    return company


def ingested(company_id: UUID) -> CompanyIngested:
    return CompanyIngested(company_id=company_id, ingestion_result="created", source="importyeti")


@pytest.fixture
def companies() -> FakeCompanyRepository:
    return FakeCompanyRepository()


@pytest.fixture
def opportunities() -> FakeOpportunityRepository:
    return FakeOpportunityRepository()


@pytest.fixture
def uow(
    companies: FakeCompanyRepository, opportunities: FakeOpportunityRepository
) -> FakeUnitOfWork:
    return FakeUnitOfWork(companies, opportunities)


@pytest.fixture
def scorer() -> FakeScoringService:
    return FakeScoringService()


@pytest.fixture
def workflow(uow: FakeUnitOfWork, scorer: FakeScoringService) -> OpportunityApplicationWorkflow:
    return OpportunityApplicationWorkflow(uow_factory=lambda: uow, scoring_service=scorer)


class TestCreation:
    async def test_new_company_creates_opportunity(
        self,
        workflow: OpportunityApplicationWorkflow,
        companies: FakeCompanyRepository,
        opportunities: FakeOpportunityRepository,
        uow: FakeUnitOfWork,
    ) -> None:
        company = make_company()
        await companies.add(company)

        outcome = await workflow.handle(ingested(company.id), user_id=USER_ID)

        assert outcome.action is OpportunityProcessingAction.CREATED
        assert outcome.opportunity_id is not None
        assert outcome.score == 75.0
        assert outcome.confidence == 0.8
        assert outcome.qualification_decision == "review"
        assert outcome.data_completeness == 0.6
        assert outcome.recommended_action == "human_review"
        assert outcome.scoring_version == "fake-v1"
        assert outcome.policy_version == "fake-policy-v1"
        assert outcome.emitted_events_count == 2  # OpportunityCreated + AssessmentApplied
        assert uow.committed == 1
        stored = opportunities.items[outcome.opportunity_id]
        assert len(stored.history) == 1
        assert stored.priority is Priority.HIGH

    async def test_facts_changed_event_also_accepted(
        self, workflow: OpportunityApplicationWorkflow, companies: FakeCompanyRepository
    ) -> None:
        company = make_company()
        await companies.add(company)
        event = CompanyFactsChanged(
            company_id=company.id, changed_fields=("signals",), reason="new signal observed"
        )
        outcome = await workflow.handle(event, user_id=USER_ID)
        assert outcome.action is OpportunityProcessingAction.CREATED


class TestReassessment:
    async def test_existing_opportunity_gets_appended_assessment(
        self,
        companies: FakeCompanyRepository,
        opportunities: FakeOpportunityRepository,
        uow: FakeUnitOfWork,
    ) -> None:
        company = make_company()
        await companies.add(company)
        first_scorer = FakeScoringService(make_fake_assessment(60.0))
        second_scorer = FakeScoringService(make_fake_assessment(85.0))

        first = OpportunityApplicationWorkflow(lambda: uow, first_scorer)
        second = OpportunityApplicationWorkflow(lambda: uow, second_scorer)
        created = await first.handle(ingested(company.id), user_id=USER_ID)
        reassessed = await second.handle(ingested(company.id), user_id=USER_ID)

        assert reassessed.action is OpportunityProcessingAction.REASSESSED
        assert reassessed.opportunity_id == created.opportunity_id
        assert len(opportunities.items) == 1
        stored = opportunities.items[created.opportunity_id]  # type: ignore[index]
        assert [a.new_score.value for a in stored.history] == [60.0, 85.0]
        assert reassessed.emitted_events_count == 1  # only AssessmentApplied

    async def test_duplicate_event_is_idempotent(
        self,
        workflow: OpportunityApplicationWorkflow,
        companies: FakeCompanyRepository,
        opportunities: FakeOpportunityRepository,
        uow: FakeUnitOfWork,
    ) -> None:
        company = make_company()
        await companies.add(company)

        created = await workflow.handle(ingested(company.id), user_id=USER_ID)
        replay = await workflow.handle(ingested(company.id), user_id=USER_ID)

        assert replay.action is OpportunityProcessingAction.SKIPPED
        assert replay.emitted_events_count == 0
        assert len(opportunities.items) == 1
        stored = opportunities.items[created.opportunity_id]  # type: ignore[index]
        assert len(stored.history) == 1  # no duplicate assessment
        assert uow.committed == 1  # replay never committed


class TestNonConditions:
    async def test_unknown_company_rejected(
        self, workflow: OpportunityApplicationWorkflow, uow: FakeUnitOfWork
    ) -> None:
        outcome = await workflow.handle(ingested(uuid4()), user_id=USER_ID)
        assert outcome.action is OpportunityProcessingAction.REJECTED
        assert uow.committed == 0

    async def test_company_without_sources_skipped(
        self, workflow: OpportunityApplicationWorkflow, companies: FakeCompanyRepository
    ) -> None:
        company = make_company(with_source=False)
        await companies.add(company)
        outcome = await workflow.handle(ingested(company.id), user_id=USER_ID)
        assert outcome.action is OpportunityProcessingAction.SKIPPED
        assert "no source references" in outcome.notes[0]

    async def test_incomplete_assessment_rejected(
        self, companies: FakeCompanyRepository, uow: FakeUnitOfWork
    ) -> None:
        company = make_company()
        await companies.add(company)
        incomplete = OpportunityAssessment(
            new_score=OpportunityScore(50.0),
            confidence=Confidence(0.5),
            reasons=("something",),
            scoring_version="fake-v1",
            # priority / recommended_action / assessed_by missing
        )
        workflow = OpportunityApplicationWorkflow(lambda: uow, FakeScoringService(incomplete))
        outcome = await workflow.handle(ingested(company.id), user_id=USER_ID)
        assert outcome.action is OpportunityProcessingAction.REJECTED
        assert "incomplete assessment" in outcome.notes[0]
        assert uow.committed == 0

    async def test_closed_opportunity_skipped_not_mutated(
        self,
        workflow: OpportunityApplicationWorkflow,
        companies: FakeCompanyRepository,
        opportunities: FakeOpportunityRepository,
        uow: FakeUnitOfWork,
    ) -> None:
        company = make_company()
        await companies.add(company)
        closed = Opportunity.create_for_company(company.id, USER_ID)
        closed.disqualify("bad fit")
        closed.drain_events()
        await opportunities.add(closed)

        outcome = await workflow.handle(ingested(company.id), user_id=USER_ID)

        assert outcome.action is OpportunityProcessingAction.SKIPPED
        assert "does not reopen" in outcome.notes[0]
        assert closed.history == ()
        assert uow.committed == 0

    async def test_scorer_crash_propagates_without_commit(
        self, companies: FakeCompanyRepository, uow: FakeUnitOfWork
    ) -> None:
        company = make_company()
        await companies.add(company)
        workflow = OpportunityApplicationWorkflow(
            lambda: uow, FakeScoringService(error=RuntimeError("scorer exploded"))
        )
        with pytest.raises(RuntimeError, match="scorer exploded"):
            await workflow.handle(ingested(company.id), user_id=USER_ID)
        assert uow.committed == 0  # UoW exits uncommitted → rollback semantics


class TestCommitEventOrdering:
    """L9 follow-up: peek before commit, drain only after success."""

    async def test_commit_failure_keeps_pending_events(
        self,
        workflow: OpportunityApplicationWorkflow,
        companies: FakeCompanyRepository,
        opportunities: FakeOpportunityRepository,
        uow: FakeUnitOfWork,
    ) -> None:
        company = make_company()
        await companies.add(company)
        uow.commit_error = RuntimeError("connection lost mid-commit")

        with pytest.raises(RuntimeError, match="connection lost"):
            await workflow.handle(ingested(company.id), user_id=USER_ID)

        stored = next(iter(opportunities.items.values()))
        assert len(stored.pending_events) == 2  # events survived the failed commit
        assert uow.committed == 0

    async def test_retry_after_failure_publishes_exactly_once(
        self,
        workflow: OpportunityApplicationWorkflow,
        companies: FakeCompanyRepository,
        opportunities: FakeOpportunityRepository,
        uow: FakeUnitOfWork,
    ) -> None:
        company = make_company()
        await companies.add(company)
        uow.commit_error = RuntimeError("transient")
        with pytest.raises(RuntimeError):
            await workflow.handle(ingested(company.id), user_id=USER_ID)

        # retry: fake repo still holds the same aggregate → REASSESSED path
        # is skipped by fingerprint, so replay the event fresh
        opportunities.items.clear()
        outcome = await workflow.handle(ingested(company.id), user_id=USER_ID)
        assert outcome.emitted_events_count == 2  # published exactly once
        stored = opportunities.items[outcome.opportunity_id]  # type: ignore[index]
        assert stored.pending_events == ()  # drained after successful commit

    async def test_db_duplicate_on_commit_becomes_skipped(
        self,
        workflow: OpportunityApplicationWorkflow,
        companies: FakeCompanyRepository,
        opportunities: FakeOpportunityRepository,
        uow: FakeUnitOfWork,
    ) -> None:
        """Unique (opportunity_id, fingerprint) race → SKIPPED, not a crash."""
        company = make_company()
        await companies.add(company)
        uow.commit_error = DuplicateOperation("uq_assessments_fingerprint")

        outcome = await workflow.handle(ingested(company.id), user_id=USER_ID)

        assert outcome.action is OpportunityProcessingAction.SKIPPED
        assert "concurrent duplicate" in outcome.notes[0]
        assert "uq_assessments_fingerprint" not in outcome.notes[0]
        assert outcome.emitted_events_count == 0
        stored = next(iter(opportunities.items.values()))
        assert len(stored.pending_events) == 2  # never drained → never published


class TestEventHygiene:
    async def test_pending_events_drained_exactly_once(
        self,
        workflow: OpportunityApplicationWorkflow,
        companies: FakeCompanyRepository,
        opportunities: FakeOpportunityRepository,
    ) -> None:
        company = make_company()
        await companies.add(company)
        outcome = await workflow.handle(ingested(company.id), user_id=USER_ID)
        stored = opportunities.items[outcome.opportunity_id]  # type: ignore[index]
        assert stored.drain_events() == ()  # workflow already drained them

    async def test_workflow_never_computes_scores_itself(
        self,
        workflow: OpportunityApplicationWorkflow,
        companies: FakeCompanyRepository,
        scorer: FakeScoringService,
    ) -> None:
        company = make_company()
        await companies.add(company)
        outcome = await workflow.handle(ingested(company.id), user_id=USER_ID)
        # the score is exactly what the injected strategy returned
        assert len(scorer.calls) == 1
        assert outcome.score == 75.0
        assert scorer.calls[0].company_id == company.id
        assert scorer.calls[0].sources == company.sources
