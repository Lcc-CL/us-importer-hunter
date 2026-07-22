"""Read-only current Import Evidence projections for qualification scoring."""

from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.mappers.import_evidence import ImportEvidencePromotionMapper
from app.database.models.company import CompanySignalModel
from app.database.models.import_evidence import ImportEvidenceCompanySignalModel
from app.database.models.research import ResearchPromotionModel
from app.domain.import_evidence.models import ImportEvidenceScoringProjection


class SqlAlchemyImportEvidenceProjectionReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read_for_company(self, company_id: UUID) -> ImportEvidenceScoringProjection:
        async with self._session_factory() as session:
            signal_result = await session.execute(
                select(ImportEvidenceCompanySignalModel)
                .where(
                    ImportEvidenceCompanySignalModel.company_id == company_id,
                    ImportEvidenceCompanySignalModel.is_active.is_(True),
                    ImportEvidenceCompanySignalModel.ownership == "import_evidence",
                )
                .order_by(ImportEvidenceCompanySignalModel.signal_kind)
            )
            research_result = await session.execute(
                select(CompanySignalModel.signal)
                .join(
                    ResearchPromotionModel,
                    and_(
                        ResearchPromotionModel.company_id == CompanySignalModel.company_id,
                        ResearchPromotionModel.company_signal_position
                        == CompanySignalModel.position,
                    ),
                )
                .where(CompanySignalModel.company_id == company_id)
            )
            return ImportEvidenceScoringProjection(
                signals=tuple(
                    ImportEvidencePromotionMapper.signal_to_domain(row)
                    for row in signal_result.scalars()
                ),
                research_signals=tuple(research_result.scalars()),
            )
