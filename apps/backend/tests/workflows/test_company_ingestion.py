"""Company ingestion workflow: claim → create / merge / reject.

Pure unit tests — in-memory fakes implement the domain repository and
UnitOfWork protocols; no database, no event bus, no data sources.
"""

from datetime import UTC, datetime
from types import TracebackType
from uuid import UUID, uuid4

import pytest

from app.domain.company import Company
from app.domain.discovery import DiscoveryResult, RawCompanySnapshot, Signal
from app.domain.events import CompanyDiscovered
from app.domain.repositories import (
    CompanyRepository,
    ContactRepository,
    OpportunityRepository,
    OutreachRepository,
    ResearchRunRepository,
    TaskRepository,
)
from app.domain.values import CompanyName, SourceReference, WebsiteUrl
from app.workflows.company_ingestion import CompanyIngestionWorkflow, IngestionStatus


class FakeCompanyRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Company] = {}
        self.saved: list[UUID] = []

    async def get_by_id(self, company_id: UUID) -> Company | None:
        return self.items.get(company_id)

    async def add(self, company: Company) -> None:
        self.items[company.id] = company

    async def save(self, company: Company) -> None:
        self.items[company.id] = company
        self.saved.append(company.id)

    async def exists(self, company_id: UUID) -> bool:
        return company_id in self.items

    async def find_by_normalized_name(self, name: CompanyName) -> Company | None:
        for company in self.items.values():
            if company.name.normalized == name.normalized:
                return company
        return None

    async def find_by_website_host(self, host: str) -> Company | None:
        for company in self.items.values():
            if company.website is not None and company.website.host == host.lower():
                return company
        return None


class FakeUnitOfWork:
    # declared to satisfy the UnitOfWork protocol; this workflow only
    # touches companies, so the other repositories are never assigned
    companies: CompanyRepository
    opportunities: OpportunityRepository
    outreaches: OutreachRepository
    contacts: ContactRepository
    tasks: TaskRepository
    research_runs: ResearchRunRepository

    def __init__(self, companies: FakeCompanyRepository) -> None:
        self.companies = companies
        self.committed = 0
        self.rolled_back = 0

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
        self.committed += 1

    async def rollback(self) -> None:
        self.rolled_back += 1


def make_event(
    name_text: str = "Pacific Home Goods Inc",
    website_text: str | None = "pacifichomegoods.com",
    signals: tuple[Signal, ...] = (),
    reference: str = "https://example.com/company/phg",
) -> CompanyDiscovered:
    snapshot = RawCompanySnapshot(
        name_text=name_text,
        source=SourceReference(
            source="importyeti",
            reference=reference,
            retrieved_at=datetime(2026, 7, 1, tzinfo=UTC),
        ),
        website_text=website_text,
    )
    return CompanyDiscovered(
        run_id=uuid4(), result=DiscoveryResult(snapshot=snapshot, signals=signals)
    )


@pytest.fixture
def repo() -> FakeCompanyRepository:
    return FakeCompanyRepository()


@pytest.fixture
def uow(repo: FakeCompanyRepository) -> FakeUnitOfWork:
    return FakeUnitOfWork(repo)


@pytest.fixture
def workflow(uow: FakeUnitOfWork) -> CompanyIngestionWorkflow:
    return CompanyIngestionWorkflow(uow_factory=lambda: uow)


class TestCreation:
    async def test_new_claim_creates_company(
        self, workflow: CompanyIngestionWorkflow, repo: FakeCompanyRepository, uow: FakeUnitOfWork
    ) -> None:
        outcome = await workflow.handle(make_event())
        assert outcome.status is IngestionStatus.CREATED
        assert outcome.company_id is not None
        company = repo.items[outcome.company_id]
        assert company.name == CompanyName("Pacific Home Goods Inc")
        assert company.website == WebsiteUrl("https://pacifichomegoods.com")
        assert len(company.sources) == 1
        assert uow.committed == 1

    async def test_signals_recorded_on_creation(
        self, workflow: CompanyIngestionWorkflow, repo: FakeCompanyRepository
    ) -> None:
        event = make_event(signals=(Signal(kind="volume_trend", detail="growing"),))
        outcome = await workflow.handle(event)
        assert outcome.company_id is not None
        assert repo.items[outcome.company_id].signals == ("volume_trend: growing",)

    async def test_invalid_website_dropped_but_company_created(
        self, workflow: CompanyIngestionWorkflow, repo: FakeCompanyRepository
    ) -> None:
        outcome = await workflow.handle(make_event(website_text="not a url at all"))
        assert outcome.status is IngestionStatus.CREATED
        assert outcome.company_id is not None
        assert repo.items[outcome.company_id].website is None
        assert any("dropped" in note for note in outcome.notes)


class TestMerge:
    async def test_duplicate_name_merges_not_creates(
        self, workflow: CompanyIngestionWorkflow, repo: FakeCompanyRepository
    ) -> None:
        first = await workflow.handle(make_event())
        second = await workflow.handle(
            make_event(name_text="PACIFIC  HOME GOODS INC", reference="https://other.ref/2")
        )
        assert second.status is IngestionStatus.MERGED
        assert second.company_id == first.company_id
        assert len(repo.items) == 1

    async def test_same_host_different_name_merges_with_alias(
        self, workflow: CompanyIngestionWorkflow, repo: FakeCompanyRepository
    ) -> None:
        first = await workflow.handle(make_event())
        second = await workflow.handle(
            make_event(name_text="PHG Incorporated", reference="https://other.ref/3")
        )
        assert second.status is IngestionStatus.MERGED
        assert second.company_id == first.company_id
        company = repo.items[first.company_id]  # type: ignore[index]
        assert CompanyName("PHG Incorporated") in company.aliases

    async def test_alias_merge_is_idempotent(
        self, workflow: CompanyIngestionWorkflow, repo: FakeCompanyRepository
    ) -> None:
        await workflow.handle(make_event())
        await workflow.handle(make_event(name_text="PHG Inc", reference="r2"))
        outcome = await workflow.handle(make_event(name_text="PHG Inc", reference="r3"))
        assert outcome.status is IngestionStatus.MERGED
        company = repo.items[outcome.company_id]  # type: ignore[index]
        assert [a.value for a in company.aliases].count("PHG Inc") == 1

    async def test_signals_appended_on_merge(
        self, workflow: CompanyIngestionWorkflow, repo: FakeCompanyRepository
    ) -> None:
        await workflow.handle(make_event())
        outcome = await workflow.handle(
            make_event(
                signals=(Signal(kind="cadence_gap", detail="8-week pause"),),
                reference="https://other.ref/4",
            )
        )
        company = repo.items[outcome.company_id]  # type: ignore[index]
        assert "cadence_gap: 8-week pause" in company.signals

    async def test_duplicate_source_skipped(
        self, workflow: CompanyIngestionWorkflow, repo: FakeCompanyRepository
    ) -> None:
        await workflow.handle(make_event())
        outcome = await workflow.handle(make_event())  # identical source reference
        company = repo.items[outcome.company_id]  # type: ignore[index]
        assert len(company.sources) == 1
        assert any("already recorded" in note for note in outcome.notes)

    async def test_conflicting_website_keeps_existing(
        self, workflow: CompanyIngestionWorkflow, repo: FakeCompanyRepository
    ) -> None:
        await workflow.handle(make_event())
        outcome = await workflow.handle(
            make_event(
                name_text="Pacific Home Goods Inc",
                website_text="totally-different.com",
                reference="r5",
            )
        )
        assert outcome.status is IngestionStatus.MERGED
        company = repo.items[outcome.company_id]  # type: ignore[index]
        assert company.website == WebsiteUrl("https://pacifichomegoods.com")
        assert any("website kept unchanged" in note for note in outcome.notes)

    async def test_website_filled_when_missing(
        self, workflow: CompanyIngestionWorkflow, repo: FakeCompanyRepository
    ) -> None:
        await workflow.handle(make_event(website_text=None))
        outcome = await workflow.handle(make_event(reference="r6"))
        company = repo.items[outcome.company_id]  # type: ignore[index]
        assert company.website == WebsiteUrl("https://pacifichomegoods.com")


class TestRejection:
    async def test_unusable_name_rejects_claim(
        self, workflow: CompanyIngestionWorkflow, repo: FakeCompanyRepository, uow: FakeUnitOfWork
    ) -> None:
        # blank names die at snapshot construction; the workflow-level
        # rejection is a name the snapshot allows but CompanyName refuses
        outcome = await workflow.handle(make_event(name_text="x" * 500))
        assert outcome.status is IngestionStatus.REJECTED
        assert outcome.company_id is None
        assert repo.items == {}
        assert uow.committed == 0
