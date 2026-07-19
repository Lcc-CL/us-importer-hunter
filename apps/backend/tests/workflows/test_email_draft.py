"""EmailDraftGenerationWorkflow: the MVP chain's last hop, fakes only."""

from datetime import UTC, datetime
from types import TracebackType
from uuid import UUID, uuid4

import pytest

from app.domain.company import Company
from app.domain.contact import (
    Contact,
    ContactChannel,
    ContactChannelType,
    DecisionMakerFitAssessment,
    JobTitle,
    PersonName,
)
from app.domain.exceptions import DuplicateOperation
from app.domain.opportunity import Opportunity
from app.domain.outreach import EmailDraftStatus, Outreach
from app.domain.repositories import (
    CompanyRepository,
    ContactRepository,
    OpportunityRepository,
    OutreachRepository,
    ResearchRunRepository,
    TaskRepository,
)
from app.domain.services import EmailGenerationContext, GeneratedEmail, SenderProfile
from app.domain.values import (
    CompanyName,
    Confidence,
    DataCompleteness,
    DimensionAssessment,
    DimensionStatus,
    Evidence,
    OpportunityAssessment,
    OpportunityScore,
    Priority,
    QualificationDecision,
    ScoreBreakdown,
    ScoringDimension,
    SourceReference,
    WebsiteUrl,
)
from app.services.email import FakeEmailDraftGenerator
from app.workflows.email import EmailDraftAction, EmailDraftGenerationWorkflow

USER_ID = uuid4()
SENDER = SenderProfile(
    name="Alex Liu",
    company="Eastbridge Freight",
    value_proposition="We run weekly FCL consolidations from Shanghai to LA.",
)
SOURCE = SourceReference(
    source="importyeti", reference="https://r/1", retrieved_at=datetime(2026, 7, 1, tzinfo=UTC)
)


def make_assessment(
    decision: QualificationDecision = QualificationDecision.QUALIFIED,
    reasons: tuple[str, ...] = ("import-related signal present",),
) -> OpportunityAssessment:
    breakdown = ScoreBreakdown.from_dimensions(
        (
            DimensionAssessment(
                dimension=ScoringDimension.IMPORT_ACTIVITY,
                weight=100.0,
                status=DimensionStatus.UNKNOWN,
                earned_score=0.0,
                reasons=("fake",),
            ),
        )
    )
    return OpportunityAssessment(
        new_score=OpportunityScore(78.0),
        confidence=Confidence(0.7),
        data_completeness=DataCompleteness(0.6),
        qualification_decision=decision,
        score_breakdown=breakdown,
        reasons=reasons,
        evidence=(Evidence(claim="importyeti recorded shipments", sources=(SOURCE,)),),
        priority=Priority.HIGH,
        recommended_action="prepare_outreach",
        assessed_by="Fake",
        scoring_version="fake-v1",
        policy_version="fake-policy-v1",
    )


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

    async def get_by_id(self, opportunity_id: UUID) -> Opportunity | None:
        return self.items.get(opportunity_id)

    async def add(self, opportunity: Opportunity) -> None:
        self.items[opportunity.id] = opportunity

    async def save(self, opportunity: Opportunity) -> None:
        self.items[opportunity.id] = opportunity

    async def get_for_company_and_user(
        self, company_id: UUID, user_id: UUID
    ) -> Opportunity | None:
        return None


class FakeContactRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Contact] = {}

    async def get_by_id(self, contact_id: UUID) -> Contact | None:
        return self.items.get(contact_id)

    async def add(self, contact: Contact) -> None:
        self.items[contact.id] = contact

    async def save(self, contact: Contact) -> None:
        self.items[contact.id] = contact

    async def list_for_company(self, company_id: UUID) -> list[Contact]:
        return [c for c in self.items.values() if c.company_id == company_id]

    async def find_by_email(self, company_id: UUID, normalized_email: str) -> Contact | None:
        return None

    async def find_by_linkedin_url(
        self, company_id: UUID, normalized_url: str
    ) -> Contact | None:
        return None

    async def record_fit_assessment(self, assessment: object) -> None:
        pass

    async def list_fit_assessments_for_company(
        self, company_id: UUID
    ) -> list[DecisionMakerFitAssessment]:
        return []


class FakeOutreachRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Outreach] = {}

    async def get_by_id(self, outreach_id: UUID) -> Outreach | None:
        return self.items.get(outreach_id)

    async def add(self, outreach: Outreach) -> None:
        self.items[outreach.id] = outreach

    async def save(self, outreach: Outreach) -> None:
        self.items[outreach.id] = outreach

    async def list_for_opportunity(self, opportunity_id: UUID) -> list[Outreach]:
        return [o for o in self.items.values() if o.opportunity_id == opportunity_id]


class FakeUnitOfWork:
    companies: CompanyRepository
    opportunities: OpportunityRepository
    outreaches: OutreachRepository
    contacts: ContactRepository
    tasks: TaskRepository
    research_runs: ResearchRunRepository

    def __init__(
        self,
        companies: FakeCompanyRepository,
        opportunities: FakeOpportunityRepository,
        contacts: FakeContactRepository,
        outreaches: FakeOutreachRepository,
    ) -> None:
        self.companies = companies
        self.opportunities = opportunities
        self.contacts = contacts
        self.outreaches = outreaches
        self.committed = 0
        self.commit_error: Exception | None = None

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


class ExplodingGenerator:
    provider_name = "boom"
    model_name = "boom-v1"

    async def generate(self, context: EmailGenerationContext) -> GeneratedEmail:
        raise RuntimeError("provider exploded")


@pytest.fixture
def repos() -> tuple[
    FakeCompanyRepository, FakeOpportunityRepository, FakeContactRepository, FakeOutreachRepository
]:
    return (
        FakeCompanyRepository(),
        FakeOpportunityRepository(),
        FakeContactRepository(),
        FakeOutreachRepository(),
    )


@pytest.fixture
def uow(
    repos: tuple[
        FakeCompanyRepository,
        FakeOpportunityRepository,
        FakeContactRepository,
        FakeOutreachRepository,
    ],
) -> FakeUnitOfWork:
    return FakeUnitOfWork(*repos)


@pytest.fixture
def workflow(uow: FakeUnitOfWork) -> EmailDraftGenerationWorkflow:
    return EmailDraftGenerationWorkflow(
        uow_factory=lambda: uow, generator=FakeEmailDraftGenerator()
    )


async def seed_qualified(
    uow: FakeUnitOfWork,
    decision: QualificationDecision = QualificationDecision.QUALIFIED,
    contact_active: bool = True,
) -> tuple[Opportunity, Contact]:
    company = Company.create(CompanyName("Pacific Home Goods Inc."), WebsiteUrl("https://phg.com"))
    company.drain_events()
    await uow.companies.add(company)

    opportunity = Opportunity.create_for_company(company.id, USER_ID)
    opportunity.apply_assessment(make_assessment(decision))
    opportunity.drain_events()
    await uow.opportunities.add(opportunity)

    contact = Contact.create_for_company(
        company.id, PersonName("Maria Chen"), JobTitle("Director of Supply Chain")
    )
    contact.add_channel(
        ContactChannel(
            channel_type=ContactChannelType.EMAIL,
            normalized_value="maria@phg.com",
            display_value="maria@phg.com",
            source_reference=SOURCE,
        )
    )
    if contact_active:
        contact.activate()
    contact.drain_events()
    await uow.contacts.add(contact)
    return opportunity, contact


class TestGeneration:
    async def test_qualified_opportunity_generates_draft(
        self, workflow: EmailDraftGenerationWorkflow, uow: FakeUnitOfWork
    ) -> None:
        opportunity, contact = await seed_qualified(uow)
        outcome = await workflow.handle(
            opportunity_id=opportunity.id, contact_id=contact.id, sender=SENDER
        )
        assert outcome.action is EmailDraftAction.GENERATED
        assert outcome.draft_version == 1
        assert outcome.subject and "Pacific Home Goods" in outcome.subject
        assert uow.committed == 1
        outreach = next(iter(uow.outreaches.items.values()))  # type: ignore[attr-defined]
        draft = outreach.drafts[0]
        assert draft.status is EmailDraftStatus.GENERATED  # human review pending
        assert draft.provider == "fake"
        assert len(draft.context_fingerprint) == 64
        assert outreach.pending_events == ()  # drained after commit

    async def test_new_context_creates_new_version(
        self, workflow: EmailDraftGenerationWorkflow, uow: FakeUnitOfWork
    ) -> None:
        opportunity, contact = await seed_qualified(uow)
        first = await workflow.handle(
            opportunity_id=opportunity.id, contact_id=contact.id, sender=SENDER
        )
        # facts change → new assessment → new context fingerprint
        opportunity.apply_assessment(
            make_assessment(reasons=("growth signal observed", "import signal present"))
        )
        opportunity.drain_events()
        second = await workflow.handle(
            opportunity_id=opportunity.id, contact_id=contact.id, sender=SENDER
        )
        assert first.action is second.action is EmailDraftAction.GENERATED
        assert second.outreach_id == first.outreach_id  # same conversation
        assert second.draft_version == 2  # appended, never overwritten
        outreach = uow.outreaches.items[second.outreach_id]  # type: ignore[attr-defined]
        assert [d.version for d in outreach.drafts] == [1, 2]


class TestSkipAndReject:
    async def test_same_context_skipped(
        self, workflow: EmailDraftGenerationWorkflow, uow: FakeUnitOfWork
    ) -> None:
        opportunity, contact = await seed_qualified(uow)
        await workflow.handle(
            opportunity_id=opportunity.id, contact_id=contact.id, sender=SENDER
        )
        replay = await workflow.handle(
            opportunity_id=opportunity.id, contact_id=contact.id, sender=SENDER
        )
        assert replay.action is EmailDraftAction.SKIPPED
        assert uow.committed == 1  # replay never committed
        outreach = next(iter(uow.outreaches.items.values()))  # type: ignore[attr-defined]
        assert len(outreach.drafts) == 1

    async def test_non_qualified_rejected(
        self, workflow: EmailDraftGenerationWorkflow, uow: FakeUnitOfWork
    ) -> None:
        opportunity, contact = await seed_qualified(
            uow, decision=QualificationDecision.REVIEW
        )
        outcome = await workflow.handle(
            opportunity_id=opportunity.id, contact_id=contact.id, sender=SENDER
        )
        assert outcome.action is EmailDraftAction.REJECTED
        assert "only QUALIFIED" in outcome.notes[0]
        assert uow.committed == 0

    async def test_inactive_contact_rejected(
        self, workflow: EmailDraftGenerationWorkflow, uow: FakeUnitOfWork
    ) -> None:
        opportunity, contact = await seed_qualified(uow, contact_active=False)
        outcome = await workflow.handle(
            opportunity_id=opportunity.id, contact_id=contact.id, sender=SENDER
        )
        assert outcome.action is EmailDraftAction.REJECTED
        assert "ACTIVE contacts only" in outcome.notes[0]

    async def test_unknown_opportunity_rejected(
        self, workflow: EmailDraftGenerationWorkflow
    ) -> None:
        outcome = await workflow.handle(
            opportunity_id=uuid4(), contact_id=uuid4(), sender=SENDER
        )
        assert outcome.action is EmailDraftAction.REJECTED


class TestFailureSemantics:
    async def test_provider_failure_rolls_back(self, uow: FakeUnitOfWork) -> None:
        opportunity, contact = await seed_qualified(uow)
        workflow = EmailDraftGenerationWorkflow(
            uow_factory=lambda: uow, generator=ExplodingGenerator()
        )
        with pytest.raises(RuntimeError, match="provider exploded"):
            await workflow.handle(
                opportunity_id=opportunity.id, contact_id=contact.id, sender=SENDER
            )
        assert uow.committed == 0
        assert uow.outreaches.items == {}  # type: ignore[attr-defined]

    async def test_commit_failure_keeps_pending_events(
        self, workflow: EmailDraftGenerationWorkflow, uow: FakeUnitOfWork
    ) -> None:
        opportunity, contact = await seed_qualified(uow)
        uow.commit_error = RuntimeError("connection lost mid-commit")
        with pytest.raises(RuntimeError, match="connection lost"):
            await workflow.handle(
                opportunity_id=opportunity.id, contact_id=contact.id, sender=SENDER
            )
        outreach = next(iter(uow.outreaches.items.values()))  # type: ignore[attr-defined]
        assert len(outreach.pending_events) >= 1  # EmailDraftGenerated survived

    async def test_commit_duplicate_does_not_expose_database_details(
        self, workflow: EmailDraftGenerationWorkflow, uow: FakeUnitOfWork
    ) -> None:
        opportunity, contact = await seed_qualified(uow)
        uow.commit_error = DuplicateOperation(
            "asyncpg.exceptions.UniqueViolationError: secret_constraint"
        )

        outcome = await workflow.handle(
            opportunity_id=opportunity.id, contact_id=contact.id, sender=SENDER
        )

        assert outcome.action is EmailDraftAction.SKIPPED
        assert "concurrent duplicate" in outcome.notes[0]
        assert "asyncpg" not in outcome.notes[0]
        assert "secret_constraint" not in outcome.notes[0]
