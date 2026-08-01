"""PostgreSQL queue repository using row locks and SKIP LOCKED."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.mappers.prospect_job import ProspectJobMapper
from app.database.models.prospect_batch import ProspectBatchJobModel
from app.domain.prospect_job import ACTIVE_JOB_STATUSES, ProspectJob, ProspectJobStatus


class SqlAlchemyProspectJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, job_id: UUID) -> ProspectJob | None:
        model = await self._session.get(ProspectBatchJobModel, job_id)
        return ProspectJobMapper.to_domain(model) if model else None

    async def get_by_id_for_update(self, job_id: UUID) -> ProspectJob | None:
        model = await self._session.scalar(
            select(ProspectBatchJobModel)
            .where(ProspectBatchJobModel.id == job_id)
            .with_for_update()
        )
        return ProspectJobMapper.to_domain(model) if model else None

    async def get_latest_for_batch(self, batch_id: UUID) -> ProspectJob | None:
        model = await self._session.scalar(
            select(ProspectBatchJobModel)
            .where(ProspectBatchJobModel.batch_id == batch_id)
            .order_by(ProspectBatchJobModel.created_at.desc())
            .limit(1)
        )
        return ProspectJobMapper.to_domain(model) if model else None

    async def find_by_request_key_hash(self, request_key_hash: str) -> ProspectJob | None:
        model = await self._session.scalar(
            select(ProspectBatchJobModel).where(
                ProspectBatchJobModel.request_key_hash == request_key_hash
            )
        )
        return ProspectJobMapper.to_domain(model) if model else None

    async def find_active_by_business_key(self, business_key: str) -> ProspectJob | None:
        model = await self._session.scalar(
            select(ProspectBatchJobModel).where(
                ProspectBatchJobModel.business_key == business_key,
                ProspectBatchJobModel.status.in_([status.value for status in ACTIVE_JOB_STATUSES]),
            )
        )
        return ProspectJobMapper.to_domain(model) if model else None

    async def add(self, job: ProspectJob) -> None:
        self._session.add(ProspectJobMapper.to_model(job))

    async def save(self, job: ProspectJob) -> None:
        await self._session.merge(ProspectJobMapper.to_model(job))

    async def claim_next(
        self,
        *,
        owner: str,
        now: datetime,
        lease_ttl: timedelta,
    ) -> ProspectJob | None:
        model = await self._session.scalar(
            select(ProspectBatchJobModel)
            .where(
                ProspectBatchJobModel.status == ProspectJobStatus.PENDING.value,
                ProspectBatchJobModel.available_at <= now,
            )
            .order_by(ProspectBatchJobModel.available_at, ProspectBatchJobModel.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if model is None:
            return None
        leased = ProspectJobMapper.to_domain(model).lease(
            owner=owner,
            lease_ttl=lease_ttl,
            now=now,
        )
        await self.save(leased)
        return leased

    async def get_stale_for_update(
        self, *, now: datetime, limit: int
    ) -> list[ProspectJob]:
        models = list(
            await self._session.scalars(
                select(ProspectBatchJobModel)
                .where(
                    ProspectBatchJobModel.status.in_(
                        [ProspectJobStatus.LEASED.value, ProspectJobStatus.RUNNING.value]
                    ),
                    ProspectBatchJobModel.lease_expires_at < now,
                )
                .order_by(ProspectBatchJobModel.lease_expires_at)
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
        )
        return [ProspectJobMapper.to_domain(model) for model in models]
