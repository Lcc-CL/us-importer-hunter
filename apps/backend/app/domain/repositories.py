"""Repository and Unit of Work protocols — the domain's persistence ports.

Interfaces speak domain aggregates only; SQLAlchemy implementations live
in app/database/repositories and must never leak ORM models through
these signatures (enforced by tests). Operations are aggregate-oriented:
no generic CRUD base (ADR-0010/0017).
"""

from types import TracebackType
from typing import Protocol
from uuid import UUID

from app.domain.company import Company
from app.domain.contact import Contact, DecisionMakerFitAssessment
from app.domain.opportunity import Opportunity
from app.domain.outreach import Outreach
from app.domain.research import ResearchRun
from app.domain.task import Task
from app.domain.values import CompanyName, IdempotencyKey


class CompanyRepository(Protocol):
    async def get_by_id(self, company_id: UUID) -> Company | None: ...

    async def add(self, company: Company) -> None: ...

    async def save(self, company: Company) -> None: ...

    async def exists(self, company_id: UUID) -> bool: ...

    async def find_by_normalized_name(self, name: CompanyName) -> Company | None:
        """Dedup lookup: the canonical company already using this name, if any."""
        ...

    async def find_by_website_host(self, host: str) -> Company | None:
        """Dedup lookup: the canonical company already using this web host, if any."""
        ...


class OpportunityRepository(Protocol):
    async def get_by_id(self, opportunity_id: UUID) -> Opportunity | None: ...

    async def add(self, opportunity: Opportunity) -> None: ...

    async def save(self, opportunity: Opportunity) -> None: ...

    async def get_for_company_and_user(self, company_id: UUID, user_id: UUID) -> Opportunity | None:
        """The judgment this user currently holds about this company:
        the open opportunity if one exists, else the most recent one."""
        ...


class OutreachRepository(Protocol):
    async def get_by_id(self, outreach_id: UUID) -> Outreach | None: ...

    async def add(self, outreach: Outreach) -> None: ...

    async def save(self, outreach: Outreach) -> None: ...

    async def list_for_opportunity(self, opportunity_id: UUID) -> list[Outreach]: ...


class ContactRepository(Protocol):
    async def get_by_id(self, contact_id: UUID) -> Contact | None: ...

    async def add(self, contact: Contact) -> None: ...

    async def save(self, contact: Contact) -> None: ...

    async def list_for_company(self, company_id: UUID) -> list[Contact]: ...

    async def find_by_email(self, company_id: UUID, normalized_email: str) -> Contact | None:
        """Dedup lookup: strong match on a company-scoped email channel."""
        ...

    async def find_by_linkedin_url(
        self, company_id: UUID, normalized_url: str
    ) -> Contact | None:
        """Dedup lookup: strong match on a company-scoped LinkedIn channel."""
        ...

    async def record_fit_assessment(self, assessment: DecisionMakerFitAssessment) -> None:
        """Append-only; duplicates rejected by (contact_id, fingerprint)."""
        ...

    async def list_fit_assessments_for_company(
        self, company_id: UUID
    ) -> list[DecisionMakerFitAssessment]:
        """Persisted decision-maker judgments for the MVP prospect read model."""
        ...


class TaskRepository(Protocol):
    async def get_by_id(self, task_id: UUID) -> Task | None: ...

    async def add(self, task: Task) -> None: ...

    async def save(self, task: Task) -> None: ...

    async def active_keys(self) -> set[IdempotencyKey]:
        """Idempotency keys of currently active (created/running) tasks —
        feeds Task.create's duplicate protection."""
        ...


class ResearchRunRepository(Protocol):
    """Persistence for research runs (v0.2). A run is an audit record of what
    a website claimed and what a human decided — never company state."""

    async def get_by_id(self, research_id: UUID) -> "ResearchRun | None": ...

    async def add(self, run: "ResearchRun") -> None: ...

    async def save(self, run: "ResearchRun") -> None: ...

    async def list_for_website(
        self, website: str, *, limit: int = 10
    ) -> "list[ResearchRun]": ...


class UnitOfWork(Protocol):
    """One transaction per application use case (ADR-0017)."""

    companies: CompanyRepository
    opportunities: OpportunityRepository
    outreaches: OutreachRepository
    contacts: ContactRepository
    tasks: TaskRepository
    research_runs: ResearchRunRepository

    async def __aenter__(self) -> "UnitOfWork": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
