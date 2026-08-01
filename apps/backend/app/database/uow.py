"""Lightweight async Unit of Work (ADR-0017).

One AsyncSession, one transaction, one application use case. Exposes the
four aggregate repositories; commit/rollback are explicit. Domain event
publishing is deliberately NOT here yet — it arrives with the event
dispatcher in a later lesson.

Usage:
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        company = await uow.companies.get_by_id(company_id)
        ...
        await uow.commit()

Leaving the block without commit rolls the transaction back.
"""

from types import TracebackType

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.repositories import (
    SqlAlchemyCalibrationRunRepository,
    SqlAlchemyCompanyRepository,
    SqlAlchemyContactRepository,
    SqlAlchemyDiscoveryTaskRepository,
    SqlAlchemyImportEvidencePromotionRepository,
    SqlAlchemyImportEvidenceRepository,
    SqlAlchemyOpportunityRepository,
    SqlAlchemyOutreachRepository,
    SqlAlchemyProspectBatchRepository,
    SqlAlchemyProspectJobRepository,
    SqlAlchemyResearchRunRepository,
    SqlAlchemyTaskRepository,
)
from app.domain.exceptions import DuplicateOperation
from app.domain.repositories import (
    CalibrationRunRepository,
    CompanyRepository,
    ContactRepository,
    DiscoveryTaskRepository,
    ImportEvidencePromotionRepository,
    ImportEvidenceRepository,
    ImportEvidenceUnitOfWork,
    OpportunityRepository,
    OutreachRepository,
    ProspectBatchRepository,
    ProspectJobRepository,
    ResearchRunRepository,
    TaskRepository,
)


class SqlAlchemyUnitOfWork(ImportEvidenceUnitOfWork):
    calibrations: CalibrationRunRepository
    companies: CompanyRepository
    contacts: ContactRepository
    import_evidence: ImportEvidenceRepository
    import_evidence_promotions: ImportEvidencePromotionRepository
    opportunities: OpportunityRepository
    outreaches: OutreachRepository
    research_runs: ResearchRunRepository
    tasks: TaskRepository
    discovery_tasks: DiscoveryTaskRepository
    prospect_batches: ProspectBatchRepository
    prospect_jobs: ProspectJobRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._committed = False

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self._session = self._session_factory()
        self._committed = False
        self.companies = SqlAlchemyCompanyRepository(self._session)
        self.calibrations = SqlAlchemyCalibrationRunRepository(self._session)
        self.contacts = SqlAlchemyContactRepository(self._session)
        self.discovery_tasks = SqlAlchemyDiscoveryTaskRepository(self._session)
        self.prospect_batches = SqlAlchemyProspectBatchRepository(self._session)
        self.prospect_jobs = SqlAlchemyProspectJobRepository(self._session)
        self.import_evidence = SqlAlchemyImportEvidenceRepository(self._session)
        self.import_evidence_promotions = SqlAlchemyImportEvidencePromotionRepository(self._session)
        self.opportunities = SqlAlchemyOpportunityRepository(self._session)
        self.outreaches = SqlAlchemyOutreachRepository(self._session)
        self.research_runs = SqlAlchemyResearchRunRepository(self._session)
        self.tasks = SqlAlchemyTaskRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._session is not None
        try:
            if not self._committed:
                await self._session.rollback()
        finally:
            await self._session.close()
            self._session = None

    async def commit(self) -> None:
        assert self._session is not None, "commit outside the unit-of-work context"
        try:
            await self._session.commit()
        except IntegrityError as exc:
            # unique-constraint races (e.g. duplicate assessment fingerprint,
            # concurrent active task keys) surface as a domain-level duplicate
            # so callers above the persistence boundary never import SQLAlchemy
            await self._session.rollback()
            raise DuplicateOperation("database rejected a duplicate record") from exc
        self._committed = True

    async def flush(self) -> None:
        assert self._session is not None, "flush outside the unit-of-work context"
        await self._session.flush()

    async def rollback(self) -> None:
        assert self._session is not None, "rollback outside the unit-of-work context"
        await self._session.rollback()
