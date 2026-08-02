"""SQLAlchemy persistence for traceable bulk CSV intake."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.mappers.bulk_import import BulkImportMapper
from app.database.models.bulk_import import ImportSessionModel, RawImportRowModel
from app.domain.bulk_import import ImportSession, RawImportRow, RawImportRowStatus


class SqlAlchemyBulkImportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_session(self, session_id: UUID) -> ImportSession | None:
        model = await self._session.get(ImportSessionModel, session_id)
        return BulkImportMapper.session_to_domain(model) if model else None

    async def find_session(self, *, source: str, file_sha256: str) -> ImportSession | None:
        result = await self._session.execute(
            select(ImportSessionModel).where(
                ImportSessionModel.source == source,
                ImportSessionModel.file_sha256 == file_sha256,
            )
        )
        model = result.scalar_one_or_none()
        return BulkImportMapper.session_to_domain(model) if model else None

    async def add_session(self, session: ImportSession) -> None:
        self._session.add(BulkImportMapper.session_to_model(session))

    async def save_session(self, session: ImportSession) -> None:
        await self._session.merge(BulkImportMapper.session_to_model(session))

    async def add_rows(self, rows: tuple[RawImportRow, ...]) -> None:
        self._session.add_all([BulkImportMapper.row_to_model(row) for row in rows])

    async def list_rows(
        self,
        *,
        session_id: UUID,
        status: RawImportRowStatus | None,
        offset: int,
        limit: int,
    ) -> tuple[list[RawImportRow], int]:
        filters = [RawImportRowModel.import_session_id == session_id]
        if status is not None:
            filters.append(RawImportRowModel.status == status.value)

        total_result = await self._session.execute(
            select(func.count()).select_from(RawImportRowModel).where(*filters)
        )
        total = int(total_result.scalar_one())
        result = await self._session.execute(
            select(RawImportRowModel)
            .where(*filters)
            .order_by(RawImportRowModel.row_number)
            .offset(offset)
            .limit(limit)
        )
        return (
            [BulkImportMapper.row_to_domain(model) for model in result.scalars()],
            total,
        )
