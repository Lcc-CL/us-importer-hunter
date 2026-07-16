"""ContactIngestionWorkflow: candidate → create / merge / possible-match / reject."""

from datetime import UTC, datetime
from types import TracebackType
from uuid import UUID, uuid4

import pytest

from app.domain.contact import (
    Contact,
    ContactMatchKind,
    DecisionMakerFitAssessment,
    RawContactSnapshot,
)
from app.domain.events import ContactCandidateDiscovered
from app.domain.repositories import (
    CompanyRepository,
    ContactRepository,
    OpportunityRepository,
    OutreachRepository,
    TaskRepository,
)
from app.domain.values import SourceReference
from app.workflows.contact_ingestion import ContactIngestionAction, ContactIngestionWorkflow

COMPANY_ID = uuid4()
SOURCE = SourceReference(
    source="importyeti", reference="https://r/1", retrieved_at=datetime(2026, 7, 1, tzinfo=UTC)
)


class FakeContactRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Contact] = {}
        self.fit_assessments: list[DecisionMakerFitAssessment] = []

    async def get_by_id(self, contact_id: UUID) -> Contact | None:
        return self.items.get(contact_id)

    async def add(self, contact: Contact) -> None:
        self.items[contact.id] = contact

    async def save(self, contact: Contact) -> None:
        self.items[contact.id] = contact

    async def list_for_company(self, company_id: UUID) -> list[Contact]:
        return [c for c in self.items.values() if c.company_id == company_id]

    async def find_by_email(self, company_id: UUID, normalized_email: str) -> Contact | None:
        for contact in await self.list_for_company(company_id):
            for channel in contact.usable_channels:
                if channel.normalized_value == normalized_email:
                    return contact
        return None

    async def find_by_linkedin_url(
        self, company_id: UUID, normalized_url: str
    ) -> Contact | None:
        for contact in await self.list_for_company(company_id):
            for channel in contact.usable_channels:
                if channel.normalized_value == normalized_url:
                    return contact
        return None

    async def record_fit_assessment(self, assessment: DecisionMakerFitAssessment) -> None:
        self.fit_assessments.append(assessment)


class FakeUnitOfWork:
    companies: CompanyRepository
    opportunities: OpportunityRepository
    outreaches: OutreachRepository
    contacts: ContactRepository
    tasks: TaskRepository

    def __init__(self, contacts: FakeContactRepository) -> None:
        self.contacts = contacts
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


def make_event(
    name: str = "Maria Chen",
    title: str | None = "Director of Supply Chain",
    email: str | None = "maria@phg.com",
    linkedin: str | None = None,
    reference: str = "https://r/1",
) -> ContactCandidateDiscovered:
    return ContactCandidateDiscovered(
        candidate=RawContactSnapshot(
            company_id=COMPANY_ID,
            raw_name=name,
            raw_title=title,
            raw_email=email,
            raw_linkedin_url=linkedin,
            source_reference=SourceReference(
                source="importyeti",
                reference=reference,
                retrieved_at=datetime(2026, 7, 1, tzinfo=UTC),
            ),
        )
    )


@pytest.fixture
def repo() -> FakeContactRepository:
    return FakeContactRepository()


@pytest.fixture
def uow(repo: FakeContactRepository) -> FakeUnitOfWork:
    return FakeUnitOfWork(repo)


@pytest.fixture
def workflow(uow: FakeUnitOfWork) -> ContactIngestionWorkflow:
    return ContactIngestionWorkflow(uow_factory=lambda: uow)


class TestCreation:
    async def test_new_candidate_creates_contact(
        self, workflow: ContactIngestionWorkflow, repo: FakeContactRepository, uow: FakeUnitOfWork
    ) -> None:
        outcome = await workflow.handle(make_event())
        assert outcome.action is ContactIngestionAction.CREATED
        assert outcome.contact_id is not None
        contact = repo.items[outcome.contact_id]
        assert contact.name.value == "Maria Chen"
        assert contact.usable_channels
        assert contact.sources
        assert uow.committed == 1
        assert outcome.emitted_events_count >= 2  # created + channel added + role classified
        assert contact.pending_events == ()  # drained after commit


class TestDeduplication:
    async def test_same_email_strong_match_merges(
        self, workflow: ContactIngestionWorkflow, repo: FakeContactRepository
    ) -> None:
        first = await workflow.handle(make_event())
        second = await workflow.handle(
            make_event(name="M. Chen", title=None, reference="https://r/2")
        )
        assert second.action is ContactIngestionAction.MERGED
        assert second.contact_id == first.contact_id
        assert len(repo.items) == 1
        contact = repo.items[first.contact_id]  # type: ignore[index]
        assert len(contact.sources) == 2

    async def test_same_linkedin_strong_match(
        self, workflow: ContactIngestionWorkflow, repo: FakeContactRepository
    ) -> None:
        first = await workflow.handle(
            make_event(email=None, linkedin="linkedin.com/in/mariachen")
        )
        second = await workflow.handle(
            make_event(
                name="Maria C.", title=None, email=None,
                linkedin="www.linkedin.com/in/MariaChen", reference="https://r/2",
            )
        )
        assert second.action is ContactIngestionAction.MERGED
        assert second.contact_id == first.contact_id

    async def test_same_name_and_title_medium_match(
        self, workflow: ContactIngestionWorkflow, repo: FakeContactRepository
    ) -> None:
        await workflow.handle(make_event(email=None))
        outcome = await workflow.handle(
            make_event(name="MARIA  CHEN", email="new@phg.com", reference="https://r/2")
        )
        assert outcome.action is ContactIngestionAction.MERGED
        assert len(repo.items) == 1

    async def test_same_name_conflicting_channels_is_possible_match(
        self, workflow: ContactIngestionWorkflow, repo: FakeContactRepository, uow: FakeUnitOfWork
    ) -> None:
        await workflow.handle(make_event())
        commits_before = uow.committed
        outcome = await workflow.handle(
            make_event(title="Warehouse Supervisor", email="other.maria@elsewhere.com")
        )
        assert outcome.action is ContactIngestionAction.POSSIBLE_MATCH
        assert len(repo.items) == 1  # nothing written
        assert uow.committed == commits_before  # no transaction committed
        assert any("not merging automatically" in note for note in outcome.notes)


class TestRejectionAndOrdering:
    async def test_unusable_name_rejected(
        self, workflow: ContactIngestionWorkflow, repo: FakeContactRepository
    ) -> None:
        outcome = await workflow.handle(make_event(name="###"))
        assert outcome.action is ContactIngestionAction.REJECTED
        assert repo.items == {}

    async def test_commit_failure_keeps_pending_events(
        self, workflow: ContactIngestionWorkflow, repo: FakeContactRepository, uow: FakeUnitOfWork
    ) -> None:
        uow.commit_error = RuntimeError("connection lost")
        with pytest.raises(RuntimeError):
            await workflow.handle(make_event())
        contact = next(iter(repo.items.values()))
        assert len(contact.pending_events) >= 2  # events survived the failed commit

    async def test_dropped_channel_note_preserved(
        self, workflow: ContactIngestionWorkflow
    ) -> None:
        outcome = await workflow.handle(make_event(email="not-an-email"))
        assert outcome.action is ContactIngestionAction.CREATED
        assert any("email dropped" in note for note in outcome.notes)


class TestMatchContract:
    def test_match_kinds_require_contact_id(self) -> None:
        from app.domain.contact import ContactMatch
        from app.domain.exceptions import DomainError

        with pytest.raises(DomainError):
            ContactMatch(kind=ContactMatchKind.MATCHED, matched_contact_id=None, reason="x")
