"""Standalone PostgreSQL worker for prospect and import-resolution jobs."""

import asyncio
import contextlib
import logging
import os
import signal
import socket
from collections.abc import Callable
from datetime import timedelta
from uuid import uuid4

from redis.asyncio import Redis

from app.api.deps import (
    get_contact_ingestion_workflow,
    get_decision_maker_selection_service,
    get_decision_maker_workflow,
    get_email_draft_generator,
    get_email_draft_workflow,
    get_opportunity_scoring_service,
    get_opportunity_workflow,
    get_prospect_batch_workflow,
    get_research_extractor,
    get_research_workflow,
)
from app.core.config import get_settings
from app.core.redis import create_redis_client
from app.core.worker_health import (
    WORKER_HEARTBEAT_KEY,
    WORKER_HEARTBEAT_REFRESH_SECONDS,
    WORKER_HEARTBEAT_TTL_SECONDS,
    build_worker_heartbeat,
)
from app.database.repositories import SqlAlchemyImportEvidenceProjectionReader
from app.database.session import create_engine, create_session_factory
from app.database.uow import SqlAlchemyUnitOfWork
from app.domain.clock import utcnow
from app.domain.repositories import (
    ImportResolutionUnitOfWork,
    ProspectBatchUnitOfWork,
    UnitOfWork,
)
from app.observability.logging import configure_logging
from app.workflows.import_resolution import (
    ImportEntityResolutionWorkflow,
    ImportProcessingJobCoordinator,
    ImportProcessingJobRunner,
)
from app.workflows.mvp_prospect_analysis import UowFactory
from app.workflows.prospect_batch import ProspectJobCoordinator, ProspectJobRunner
from app.workflows.prospect_routing import ProspectRoutingExecutionWorkflow

logger = logging.getLogger(__name__)


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    redis = create_redis_client(settings.redis_url)
    owner = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for shutdown_signal in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(shutdown_signal, stop.set)
    heartbeat_task = asyncio.create_task(_run_heartbeat(redis, owner, stop))

    def uow_factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    typed_uow_factory = uow_factory
    scoring = get_opportunity_scoring_service()
    import_evidence_reader = SqlAlchemyImportEvidenceProjectionReader(session_factory)
    opportunity = get_opportunity_workflow(
        typed_uow_factory,
        scoring,
        import_evidence_reader,
    )
    contact_ingestion = get_contact_ingestion_workflow(typed_uow_factory)
    decision_maker = get_decision_maker_workflow(
        typed_uow_factory,
        get_decision_maker_selection_service(),
    )
    email = get_email_draft_workflow(
        typed_uow_factory,
        get_email_draft_generator(settings),
    )
    research = get_research_workflow(
        typed_uow_factory,
        get_research_extractor(settings),
        settings,
    )
    batch_workflow = get_prospect_batch_workflow(
        typed_uow_factory,
        research,
        opportunity,
        contact_ingestion,
        decision_maker,
        email,
        settings,
    )
    prospect_uow_factory = _prospect_uow_factory(typed_uow_factory)
    coordinator = ProspectJobCoordinator(
        prospect_uow_factory,
        lease_ttl=timedelta(seconds=settings.prospect_job_lease_ttl_seconds),
        retry_delay=timedelta(seconds=settings.prospect_job_retry_delay_seconds),
    )
    runner = ProspectJobRunner(coordinator=coordinator, batch_workflow=batch_workflow)
    import_uow_factory = _import_uow_factory(typed_uow_factory)
    import_coordinator = ImportProcessingJobCoordinator(
        import_uow_factory,
        lease_ttl=timedelta(seconds=settings.import_job_lease_ttl_seconds),
        retry_delay=timedelta(seconds=settings.import_job_retry_delay_seconds),
    )
    import_runner = ImportProcessingJobRunner(
        coordinator=import_coordinator,
        workflow=ImportEntityResolutionWorkflow(import_uow_factory),
        routing_workflow=ProspectRoutingExecutionWorkflow(import_uow_factory),
    )

    try:
        while not stop.is_set():
            import_worked = await import_runner.run_once(owner=owner)
            prospect_worked = await runner.run_once(owner=owner)
            worked = import_worked or prospect_worked
            if worked:
                continue
            try:
                await asyncio.wait_for(
                    stop.wait(),
                    timeout=settings.prospect_worker_poll_seconds,
                )
            except TimeoutError:
                pass
    finally:
        stop.set()
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task
        # Single-worker MVP: remove the key so readiness flips to unavailable
        # immediately instead of waiting for the TTL to expire.
        with contextlib.suppress(Exception):
            await redis.delete(WORKER_HEARTBEAT_KEY)
        await redis.aclose()
        await engine.dispose()


async def _run_heartbeat(
    redis: Redis,
    owner: str,
    stop: asyncio.Event,
) -> None:
    """Refresh the worker heartbeat independently of job execution length."""
    while not stop.is_set():
        try:
            await redis.set(
                WORKER_HEARTBEAT_KEY,
                build_worker_heartbeat(owner, utcnow()),
                ex=WORKER_HEARTBEAT_TTL_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("worker heartbeat write failed: %s", exc)
        try:
            await asyncio.wait_for(stop.wait(), timeout=WORKER_HEARTBEAT_REFRESH_SECONDS)
        except TimeoutError:
            pass


def _prospect_uow_factory(
    factory: UowFactory,
) -> Callable[[], ProspectBatchUnitOfWork]:
    return factory  # type: ignore[return-value]


def _import_uow_factory(
    factory: UowFactory,
) -> Callable[[], ImportResolutionUnitOfWork]:
    return factory  # type: ignore[return-value]


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
