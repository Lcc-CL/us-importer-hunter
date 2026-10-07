"""PostgreSQL repository for offline Umail result feedback."""

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.mappers.umail_feedback import UmailFeedbackMapper
from app.database.models.umail_export import UmailExportBatchModel, UmailExportRowModel
from app.database.models.umail_feedback import (
    ContactEngagementEventModel,
    UmailResultImportModel,
    UmailResultRowModel,
)
from app.domain.prospect_routing import ProspectTier
from app.domain.umail_feedback import (
    UMAIL_RESULT_MAPPING_VERSION,
    ContactEngagementEvent,
    FeedbackExportSnapshot,
    UmailResultImport,
    UmailResultMatchStatus,
    UmailResultRow,
)

SUPPRESSION_EVENT_TYPES = ("hard_bounced", "unsubscribed", "complained")


class SqlAlchemyUmailFeedbackRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_import_by_file_hash(self, file_sha256: str) -> UmailResultImport | None:
        model = await self._session.scalar(
            select(UmailResultImportModel).where(
                UmailResultImportModel.file_sha256 == file_sha256,
                UmailResultImportModel.mapping_version == UMAIL_RESULT_MAPPING_VERSION,
            )
        )
        return UmailFeedbackMapper.result_import_to_domain(model) if model else None

    async def get_import(self, result_import_id: UUID) -> UmailResultImport | None:
        model = await self._session.get(UmailResultImportModel, result_import_id)
        return UmailFeedbackMapper.result_import_to_domain(model) if model else None

    async def get_import_for_update(
        self, result_import_id: UUID
    ) -> UmailResultImport | None:
        model = await self._session.scalar(
            select(UmailResultImportModel)
            .where(UmailResultImportModel.id == result_import_id)
            .with_for_update()
        )
        return UmailFeedbackMapper.result_import_to_domain(model) if model else None

    async def add_import(
        self,
        result_import: UmailResultImport,
        rows: tuple[UmailResultRow, ...],
    ) -> None:
        self._session.add(UmailFeedbackMapper.result_import_to_model(result_import))
        self._session.add_all(
            [UmailFeedbackMapper.result_row_to_model(row) for row in rows]
        )

    async def save_import(self, result_import: UmailResultImport) -> None:
        await self._session.merge(
            UmailFeedbackMapper.result_import_to_model(result_import)
        )

    async def list_rows(
        self,
        *,
        result_import_id: UUID,
        match_status: UmailResultMatchStatus | None,
        event_type: str | None,
        campaign: str | None,
        suppression_impact: bool | None,
        offset: int,
        limit: int,
    ) -> tuple[list[UmailResultRow], int]:
        filters = [UmailResultRowModel.result_import_id == result_import_id]
        if match_status is not None:
            filters.append(UmailResultRowModel.match_status == match_status.value)
        if event_type is not None:
            filters.append(UmailResultRowModel.canonical_event_type == event_type)
        if campaign is not None:
            filters.append(UmailResultRowModel.campaign == campaign)
        if suppression_impact is True:
            filters.append(
                UmailResultRowModel.canonical_event_type.in_(SUPPRESSION_EVENT_TYPES)
            )
        elif suppression_impact is False:
            filters.append(
                or_(
                    UmailResultRowModel.canonical_event_type.is_(None),
                    UmailResultRowModel.canonical_event_type.not_in(
                        SUPPRESSION_EVENT_TYPES
                    ),
                )
            )
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(UmailResultRowModel).where(*filters)
            )
            or 0
        )
        models = list(
            await self._session.scalars(
                select(UmailResultRowModel)
                .where(*filters)
                .order_by(UmailResultRowModel.row_number)
                .offset(offset)
                .limit(limit)
            )
        )
        return [UmailFeedbackMapper.result_row_to_domain(model) for model in models], total

    async def list_rows_for_apply(self, result_import_id: UUID) -> list[UmailResultRow]:
        models = list(
            await self._session.scalars(
                select(UmailResultRowModel)
                .where(
                    UmailResultRowModel.result_import_id == result_import_id,
                    UmailResultRowModel.match_status == UmailResultMatchStatus.MATCHED.value,
                )
                .order_by(UmailResultRowModel.row_number)
            )
        )
        return [UmailFeedbackMapper.result_row_to_domain(model) for model in models]

    async def load_export_snapshots(
        self,
        *,
        export_row_ids: tuple[UUID, ...],
        emails: tuple[str, ...],
    ) -> tuple[FeedbackExportSnapshot, ...]:
        if not export_row_ids and not emails:
            return ()
        selectors = []
        if export_row_ids:
            selectors.append(UmailExportRowModel.id.in_(export_row_ids))
        if emails:
            selectors.append(UmailExportRowModel.email.in_(emails))
        rows = list(
            (
                await self._session.execute(
                    select(UmailExportRowModel, UmailExportBatchModel)
                    .join(
                        UmailExportBatchModel,
                        UmailExportBatchModel.id == UmailExportRowModel.batch_id,
                    )
                    .where(
                        UmailExportRowModel.status == "ready",
                        or_(*selectors),
                    )
                    .order_by(
                        UmailExportBatchModel.created_at,
                        UmailExportBatchModel.id,
                        UmailExportRowModel.position,
                    )
                )
            ).tuples()
        )
        snapshots: list[FeedbackExportSnapshot] = []
        for row, batch in rows:
            if row.email is None or row.contact_id is None:
                continue
            snapshots.append(
                FeedbackExportSnapshot(
                    export_batch_id=batch.id,
                    export_row_id=row.id,
                    email=row.email,
                    campaign=batch.campaign,
                    company_id=row.company_id,
                    company_name=row.company_name,
                    contact_id=row.contact_id,
                    route=ProspectTier(row.route),
                    batch_created_at=batch.created_at,
                )
            )
        return tuple(snapshots)

    async def existing_event_fingerprints(
        self, fingerprints: tuple[str, ...]
    ) -> set[str]:
        if not fingerprints:
            return set()
        return set(
            await self._session.scalars(
                select(ContactEngagementEventModel.event_fingerprint).where(
                    ContactEngagementEventModel.event_fingerprint.in_(fingerprints)
                )
            )
        )

    async def add_events(self, events: tuple[ContactEngagementEvent, ...]) -> None:
        self._session.add_all(
            [UmailFeedbackMapper.event_to_model(event) for event in events]
        )

    async def list_events(
        self, result_import_id: UUID
    ) -> list[ContactEngagementEvent]:
        models = list(
            await self._session.scalars(
                select(ContactEngagementEventModel)
                .where(ContactEngagementEventModel.result_import_id == result_import_id)
                .order_by(
                    ContactEngagementEventModel.occurred_at,
                    ContactEngagementEventModel.id,
                )
            )
        )
        return [UmailFeedbackMapper.event_to_domain(model) for model in models]
