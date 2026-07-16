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
from app.domain.opportunity import Opportunity
from app.domain.outreach import Outreach
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

    async def list_for_company_and_user(self, company_id: UUID, user_id: UUID) -> list[Opportunity]:
        """All judgments this user holds about this company (usually 0 or 1 open)."""
        ...


class OutreachRepository(Protocol):
    async def get_by_id(self, outreach_id: UUID) -> Outreach | None: ...

    async def add(self, outreach: Outreach) -> None: ...

    async def save(self, outreach: Outreach) -> None: ...

    async def list_for_opportunity(self, opportunity_id: UUID) -> list[Outreach]: ...


class TaskRepository(Protocol):
    async def get_by_id(self, task_id: UUID) -> Task | None: ...

    async def add(self, task: Task) -> None: ...

    async def save(self, task: Task) -> None: ...

    async def active_keys(self) -> set[IdempotencyKey]:
        """Idempotency keys of currently active (created/running) tasks —
        feeds Task.create's duplicate protection."""
        ...


class UnitOfWork(Protocol):
    """One transaction per application use case (ADR-0017)."""

    companies: CompanyRepository
    opportunities: OpportunityRepository
    outreaches: OutreachRepository
    tasks: TaskRepository

    async def __aenter__(self) -> "UnitOfWork": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
