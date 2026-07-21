"""DecisionMakerSelectionWorkflow: rank, persist assessments, route."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.contact import (
    Contact,
    ContactChannel,
    ContactChannelType,
    Department,
    JobTitle,
    PersonName,
    SeniorityLevel,
)
from app.domain.exceptions import DuplicateOperation
from app.domain.values import SourceReference
from app.services.contact import DeterministicDecisionMakerSelectionService
from app.workflows.decision_maker import (
    DecisionMakerSelectionAction,
    DecisionMakerSelectionWorkflow,
)
from tests.workflows.test_contact_ingestion import COMPANY_ID, FakeContactRepository, FakeUnitOfWork

OPPORTUNITY_ID = uuid4()
SOURCE = SourceReference(
    source="importyeti", reference="https://r/1", retrieved_at=datetime(2026, 7, 1, tzinfo=UTC)
)


def seed_contact(
    repo: FakeContactRepository,
    name: str,
    title: str | None,
    department: Department,
    seniority: SeniorityLevel,
    *,
    email: str | None = None,
    verified: bool = False,
    invalid: bool = False,
) -> Contact:
    contact = Contact.create_for_company(
        COMPANY_ID, PersonName(name), JobTitle(title) if title else None
    )
    contact.classify_role(department, seniority)
    contact.add_source(SOURCE)
    if email:
        contact.add_channel(
            ContactChannel(
                channel_type=ContactChannelType.EMAIL,
                normalized_value=email,
                display_value=email,
                source_reference=SOURCE,
            )
        )
        if verified:
            contact.verify_channel(ContactChannelType.EMAIL, email)
    if invalid:
        contact.mark_invalid("left company")
    contact.drain_events()
    repo.items[contact.id] = contact
    return contact


@pytest.fixture
def repo() -> FakeContactRepository:
    return FakeContactRepository()


@pytest.fixture
def uow(repo: FakeContactRepository) -> FakeUnitOfWork:
    return FakeUnitOfWork(repo)


@pytest.fixture
def workflow(uow: FakeUnitOfWork) -> DecisionMakerSelectionWorkflow:
    return DecisionMakerSelectionWorkflow(
        uow_factory=lambda: uow,
        selection_service=DeterministicDecisionMakerSelectionService(),
    )


class TestSelection:
    async def test_selects_best_logistics_contact(
        self, workflow: DecisionMakerSelectionWorkflow, repo: FakeContactRepository
    ) -> None:
        best = seed_contact(
            repo, "Lena Logistics", "Logistics Director", Department.LOGISTICS,
            SeniorityLevel.DIRECTOR, email="l@x.com", verified=True,
        )
        seed_contact(
            repo, "Mark Marketing", "Marketing Manager", Department.SALES_MARKETING,
            SeniorityLevel.MANAGER, email="m@x.com",
        )
        outcome = await workflow.handle(company_id=COMPANY_ID, opportunity_id=OPPORTUNITY_ID)
        assert outcome.action is DecisionMakerSelectionAction.SELECTED
        assert outcome.selected_contact_id == best.id
        assert outcome.recommended_channel == "email"
        assert outcome.event is not None and outcome.event.contact_id == best.id
        assert len(outcome.ranked_candidates) == 2
        assert len(repo.fit_assessments) == 2  # persisted append-only

    async def test_invalid_contacts_excluded(
        self, workflow: DecisionMakerSelectionWorkflow, repo: FakeContactRepository
    ) -> None:
        seed_contact(
            repo, "Ivan Invalid", "Logistics Director", Department.LOGISTICS,
            SeniorityLevel.DIRECTOR, email="i@x.com", invalid=True,
        )
        outcome = await workflow.handle(company_id=COMPANY_ID, opportunity_id=OPPORTUNITY_ID)
        assert outcome.action is DecisionMakerSelectionAction.RESEARCH_MORE

    async def test_no_contacts_means_research_more(
        self, workflow: DecisionMakerSelectionWorkflow
    ) -> None:
        outcome = await workflow.handle(company_id=COMPANY_ID, opportunity_id=OPPORTUNITY_ID)
        assert outcome.action is DecisionMakerSelectionAction.RESEARCH_MORE
        assert outcome.event is None

    async def test_weak_candidates_route_to_review_or_research(
        self, workflow: DecisionMakerSelectionWorkflow, repo: FakeContactRepository
    ) -> None:
        seed_contact(
            repo, "Harry HR", "HR Manager", Department.HR, SeniorityLevel.MANAGER,
            email="h@x.com",
        )
        outcome = await workflow.handle(company_id=COMPANY_ID, opportunity_id=OPPORTUNITY_ID)
        assert outcome.action in (
            DecisionMakerSelectionAction.REVIEW,
            DecisionMakerSelectionAction.RESEARCH_MORE,
        )
        assert outcome.selected_contact_id is None

    async def test_duplicate_assessment_noted_not_crashing(
        self, workflow: DecisionMakerSelectionWorkflow, repo: FakeContactRepository
    ) -> None:
        seed_contact(
            repo, "Lena Logistics", "Logistics Director", Department.LOGISTICS,
            SeniorityLevel.DIRECTOR, email="l@x.com", verified=True,
        )

        async def raise_duplicate(assessment: object) -> None:
            raise DuplicateOperation("already recorded")

        repo.record_fit_assessment = raise_duplicate  # type: ignore[method-assign]
        outcome = await workflow.handle(company_id=COMPANY_ID, opportunity_id=OPPORTUNITY_ID)
        assert outcome.action is DecisionMakerSelectionAction.SELECTED
        assert any("already recorded" in reason for reason in outcome.reasons)

    async def test_commit_duplicate_does_not_expose_database_details(
        self,
        workflow: DecisionMakerSelectionWorkflow,
        repo: FakeContactRepository,
        uow: FakeUnitOfWork,
    ) -> None:
        seed_contact(
            repo, "Lena Logistics", "Logistics Director", Department.LOGISTICS,
            SeniorityLevel.DIRECTOR, email="l@x.com", verified=True,
        )
        uow.commit_error = DuplicateOperation(
            "asyncpg.exceptions.UniqueViolationError: secret_constraint"
        )

        outcome = await workflow.handle(company_id=COMPANY_ID, opportunity_id=OPPORTUNITY_ID)

        assert outcome.action is DecisionMakerSelectionAction.SELECTED
        assert any("concurrent duplicate" in reason for reason in outcome.reasons)
        assert "asyncpg" not in " ".join(outcome.reasons)
        assert "secret_constraint" not in " ".join(outcome.reasons)

    async def test_policy_version_in_outcome(
        self, workflow: DecisionMakerSelectionWorkflow, repo: FakeContactRepository
    ) -> None:
        seed_contact(
            repo, "Lena Logistics", "Logistics Director", Department.LOGISTICS,
            SeniorityLevel.DIRECTOR, email="l@x.com",
        )
        outcome = await workflow.handle(company_id=COMPANY_ID, opportunity_id=OPPORTUNITY_ID)
        assert outcome.policy_version == "mvp-decision-maker-policy-v2"
