"""Standalone single-job worker for PostgreSQL-backed prospect execution."""

import asyncio
import os
import signal
import socket
from collections.abc import Callable
from datetime import timedelta
from uuid import uuid4

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
from app.database.repositories import SqlAlchemyImportEvidenceProjectionReader
from app.database.session import create_engine, create_session_factory
from app.database.uow import SqlAlchemyUnitOfWork
from app.domain.repositories import ProspectBatchUnitOfWork, UnitOfWork
from app.observability.logging import configure_logging
from app.workflows.mvp_prospect_analysis import UowFactory
from app.workflows.prospect_batch import ProspectJobCoordinator, ProspectJobRunner


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)

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

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for shutdown_signal in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(shutdown_signal, stop.set)
    owner = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"

    try:
        while not stop.is_set():
            worked = await runner.run_once(owner=owner)
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
        await engine.dispose()


def _prospect_uow_factory(
    factory: UowFactory,
) -> Callable[[], ProspectBatchUnitOfWork]:
    return factory  # type: ignore[return-value]


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
