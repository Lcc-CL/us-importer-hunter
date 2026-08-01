"""Application services for PostgreSQL-backed prospect job execution."""

import logging
from collections.abc import Callable
from datetime import timedelta
from uuid import UUID

from app.domain.clock import utcnow
from app.domain.prospect_batch import ProspectBatchStatus
from app.domain.prospect_job import ProspectJob, ProspectJobStatus
from app.domain.repositories import ProspectBatchUnitOfWork
from app.shared.exceptions import ResourceNotFoundError
from app.workflows.prospect_batch.workflow import ProspectBatchWorkflow

logger = logging.getLogger(__name__)


class ProspectJobCoordinator:
    def __init__(
        self,
        uow_factory: Callable[[], ProspectBatchUnitOfWork],
        *,
        lease_ttl: timedelta,
        retry_delay: timedelta,
    ) -> None:
        self._uow_factory = uow_factory
        self._lease_ttl = lease_ttl
        self._retry_delay = retry_delay

    async def claim(self, *, owner: str) -> ProspectJob | None:
        async with self._uow_factory() as uow:
            job = await uow.prospect_jobs.claim_next(
                owner=owner,
                now=utcnow(),
                lease_ttl=self._lease_ttl,
            )
            if job is not None:
                await uow.commit()
            return job

    async def start(self, job_id: UUID, *, owner: str) -> ProspectJob:
        async with self._uow_factory() as uow:
            job = await uow.prospect_jobs.get_by_id_for_update(job_id)
            if job is None:
                raise ResourceNotFoundError(f"prospect job not found: {job_id}")
            started = job.start(owner=owner)
            await uow.prospect_jobs.save(started)
            await uow.commit()
            return started

    async def heartbeat(self, job_id: UUID, *, owner: str) -> None:
        async with self._uow_factory() as uow:
            job = await uow.prospect_jobs.get_by_id_for_update(job_id)
            if job is None:
                raise ResourceNotFoundError(f"prospect job not found: {job_id}")
            await uow.prospect_jobs.save(
                job.heartbeat(owner=owner, lease_ttl=self._lease_ttl)
            )
            await uow.commit()

    async def complete(self, job_id: UUID, *, owner: str) -> ProspectJob:
        async with self._uow_factory() as uow:
            job = await uow.prospect_jobs.get_by_id_for_update(job_id)
            if job is None:
                raise ResourceNotFoundError(f"prospect job not found: {job_id}")
            completed = job.complete(owner=owner)
            await uow.prospect_jobs.save(completed)
            await uow.commit()
            return completed

    async def record_failure(
        self,
        job_id: UUID,
        *,
        owner: str,
        error_code: str,
        error_summary: str,
    ) -> ProspectJob:
        async with self._uow_factory() as uow:
            job = await uow.prospect_jobs.get_by_id_for_update(job_id)
            if job is None:
                raise ResourceNotFoundError(f"prospect job not found: {job_id}")
            updated = job.retry_after_error(
                owner=owner,
                error_code=error_code,
                error_summary=error_summary,
                delay=self._retry_delay,
            )
            batch = await uow.prospect_batches.get_by_id_for_update(job.batch_id)
            if batch is None:
                raise ResourceNotFoundError(f"prospect batch not found: {job.batch_id}")
            if updated.status is ProspectJobStatus.PENDING:
                batch.recover_stale_execution()
            else:
                batch.fail_active_execution(
                    error_code="WORKER_EXECUTION_FAILED",
                    error_summary="background processing exhausted its retry limit",
                )
            await uow.prospect_jobs.save(updated)
            await uow.prospect_batches.save(batch)
            await uow.commit()
            return updated

    async def recover_stale(self, *, limit: int = 20) -> tuple[ProspectJob, ...]:
        now = utcnow()
        recovered: list[ProspectJob] = []
        async with self._uow_factory() as uow:
            stale_jobs = await uow.prospect_jobs.get_stale_for_update(now=now, limit=limit)
            for job in stale_jobs:
                batch = await uow.prospect_batches.get_by_id_for_update(job.batch_id)
                if batch is None:
                    updated = job.recover_stale(now=now)
                elif not batch.has_active_companies:
                    if batch.status in {
                        ProspectBatchStatus.PENDING,
                        ProspectBatchStatus.RUNNING,
                    }:
                        batch.finalize()
                        await uow.prospect_batches.save(batch)
                    updated = job.reconcile_completed_after_recovery(now=now)
                else:
                    updated = job.recover_stale(now=now)
                    if updated.status is ProspectJobStatus.PENDING:
                        batch.recover_stale_execution()
                    else:
                        batch.fail_active_execution(
                            error_code="WORKER_LEASE_EXPIRED",
                            error_summary="background worker lease expired too many times",
                        )
                    await uow.prospect_batches.save(batch)
                await uow.prospect_jobs.save(updated)
                recovered.append(updated)
            if recovered:
                await uow.commit()
        return tuple(recovered)


class ProspectJobRunner:
    """Single-worker, single-job runner; PostgreSQL owns all durable state."""

    def __init__(
        self,
        *,
        coordinator: ProspectJobCoordinator,
        batch_workflow: ProspectBatchWorkflow,
    ) -> None:
        self._coordinator = coordinator
        self._batch_workflow = batch_workflow

    async def run_once(self, *, owner: str) -> bool:
        await self._coordinator.recover_stale()
        leased = await self._coordinator.claim(owner=owner)
        if leased is None:
            return False
        running = await self._coordinator.start(leased.id, owner=owner)
        try:
            await self._batch_workflow.execute(
                running.batch_id,
                sender=running.sender,
                heartbeat=lambda: self._coordinator.heartbeat(running.id, owner=owner),
            )
        except Exception as exc:
            error_code = f"UNHANDLED_{type(exc).__name__.upper()}"
            logger.error(
                "prospect background job failed",
                extra={"job_id": str(running.id), "batch_id": str(running.batch_id)},
            )
            await self._coordinator.record_failure(
                running.id,
                owner=owner,
                error_code=error_code[:100],
                error_summary=type(exc).__name__,
            )
        else:
            await self._coordinator.complete(running.id, owner=owner)
        return True


class ProspectJobQueryWorkflow:
    def __init__(self, uow_factory: Callable[[], ProspectBatchUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def latest_for_batch(self, batch_id: UUID) -> ProspectJob | None:
        async with self._uow_factory() as uow:
            return await uow.prospect_jobs.get_latest_for_batch(batch_id)
