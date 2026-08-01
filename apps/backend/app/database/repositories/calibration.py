"""SQLAlchemy repository for D4a calibration runs."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.mappers.calibration import CalibrationRunMapper
from app.database.models.calibration import CalibrationRunModel
from app.domain.calibration import CalibrationRun


class SqlAlchemyCalibrationRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, calibration_id: UUID) -> CalibrationRun | None:
        model = await self._session.get(CalibrationRunModel, calibration_id)
        return CalibrationRunMapper.to_domain(model) if model else None

    async def get_by_batch_id(self, batch_id: UUID) -> CalibrationRun | None:
        model = await self._session.scalar(
            select(CalibrationRunModel).where(
                CalibrationRunModel.prospect_batch_id == batch_id
            )
        )
        return CalibrationRunMapper.to_domain(model) if model else None

    async def add(self, run: CalibrationRun) -> None:
        self._session.add(CalibrationRunMapper.to_model(run))

    async def save(self, run: CalibrationRun) -> None:
        await self._session.merge(CalibrationRunMapper.to_model(run))
