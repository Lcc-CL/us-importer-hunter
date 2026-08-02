"""Lease/retry/heartbeat execution for background import resolution."""

import logging
from collections.abc import Callable
from datetime import timedelta
from uuid import UUID

from app.domain.clock import utcnow
from app.domain.import_resolution import (
    ImportJobStatus,
    ImportProcessingJob,
    ImportResolutionStatus,
)
from app.domain.repositories import ImportResolutionUnitOfWork
from app.shared.exceptions import ResourceNotFoundError
from app.workflows.import_resolution.workflow import ImportEntityResolutionWorkflow

logger = logging.getLogger(__name__)


class ImportProcessingJobCoordinator:
    def __init__(
        self,
        uow_factory: Callable[[], ImportResolutionUnitOfWork],
        *,
        lease_ttl: timedelta,
        retry_delay: timedelta,
    ) -> None:
        self._uow_factory = uow_factory
        self._lease_ttl = lease_ttl
        self._retry_delay = retry_delay

    async def claim(self, *, owner: str) -> ImportProcessingJob | None:
        async with self._uow_factory() as uow:
            job = await uow.import_processing_jobs.claim_next(
                owner=owner,
                now=utcnow(),
                lease_ttl=self._lease_ttl,
            )
            if job is not None:
                await uow.commit()
            return job

    async def start(self, job_id: UUID, *, owner: str) -> ImportProcessingJob:
        async with self._uow_factory() as uow:
            job = await uow.import_processing_jobs.get_by_id_for_update(job_id)
            if job is None:
                raise ResourceNotFoundError(f"import processing job not found: {job_id}")
            started = job.start(owner=owner)
            await uow.import_processing_jobs.save(started)
            await uow.commit()
            return started

    async def heartbeat(self, job_id: UUID, *, owner: str) -> None:
        async with self._uow_factory() as uow:
            job = await uow.import_processing_jobs.get_by_id_for_update(job_id)
            if job is None:
                raise ResourceNotFoundError(f"import processing job not found: {job_id}")
            await uow.import_processing_jobs.save(
                job.heartbeat(owner=owner, lease_ttl=self._lease_ttl)
            )
            await uow.commit()

    async def complete(self, job_id: UUID, *, owner: str) -> ImportProcessingJob:
        async with self._uow_factory() as uow:
            job = await uow.import_processing_jobs.get_by_id_for_update(job_id)
            if job is None:
                raise ResourceNotFoundError(f"import processing job not found: {job_id}")
            completed = job.complete(owner=owner)
            await uow.import_processing_jobs.save(completed)
            await uow.commit()
            return completed

    async def record_failure(
        self,
        job_id: UUID,
        *,
        owner: str,
        error_code: str,
        error_summary: str,
    ) -> ImportProcessingJob:
        async with self._uow_factory() as uow:
            job = await uow.import_processing_jobs.get_by_id_for_update(job_id)
            if job is None:
                raise ResourceNotFoundError(f"import processing job not found: {job_id}")
            updated = job.retry_after_error(
                owner=owner,
                error_code=error_code,
                error_summary=error_summary,
                delay=self._retry_delay,
            )
            resolution = await uow.import_resolution.get_resolution_for_update(
                job.import_session_id
            )
            if resolution is not None:
                if updated.status is ImportJobStatus.PENDING:
                    resolution.pause_for_retry()
                else:
                    resolution.fail("background entity resolution exhausted its retry limit")
                await uow.import_resolution.save_resolution(resolution)
            await uow.import_processing_jobs.save(updated)
            await uow.commit()
            return updated

    async def recover_stale(self, *, limit: int = 20) -> tuple[ImportProcessingJob, ...]:
        now = utcnow()
        recovered: list[ImportProcessingJob] = []
        async with self._uow_factory() as uow:
            jobs = await uow.import_processing_jobs.get_stale_for_update(now=now, limit=limit)
            for job in jobs:
                resolution = await uow.import_resolution.get_resolution_for_update(
                    job.import_session_id
                )
                if resolution is not None and resolution.status in {
                    ImportResolutionStatus.COMPLETED,
                    ImportResolutionStatus.PARTIAL_FAILED,
                }:
                    updated = job.reconcile_completed_after_recovery(now=now)
                else:
                    updated = job.recover_stale(now=now)
                    if resolution is not None:
                        if updated.status is ImportJobStatus.PENDING:
                            resolution.pause_for_retry()
                        else:
                            resolution.fail("background entity resolution lease expired")
                        await uow.import_resolution.save_resolution(resolution)
                await uow.import_processing_jobs.save(updated)
                recovered.append(updated)
            if recovered:
                await uow.commit()
        return tuple(recovered)


class ImportProcessingJobRunner:
    def __init__(
        self,
        *,
        coordinator: ImportProcessingJobCoordinator,
        workflow: ImportEntityResolutionWorkflow,
    ) -> None:
        self._coordinator = coordinator
        self._workflow = workflow

    async def run_once(self, *, owner: str) -> bool:
        await self._coordinator.recover_stale()
        leased = await self._coordinator.claim(owner=owner)
        if leased is None:
            return False
        running = await self._coordinator.start(leased.id, owner=owner)
        try:
            await self._workflow.execute(
                running.import_session_id,
                heartbeat=lambda: self._coordinator.heartbeat(running.id, owner=owner),
            )
        except Exception as exc:
            logger.error(
                "import entity resolution background job failed",
                extra={
                    "job_id": str(running.id),
                    "import_session_id": str(running.import_session_id),
                    "error_type": type(exc).__name__,
                },
            )
            await self._coordinator.record_failure(
                running.id,
                owner=owner,
                error_code=f"UNHANDLED_{type(exc).__name__.upper()}"[:100],
                error_summary=type(exc).__name__,
            )
        else:
            await self._coordinator.complete(running.id, owner=owner)
        return True
