"""Run independent, bounded SMTP lanes against the shared PostgreSQL queue."""

import asyncio
import logging
import signal
import sys
from time import monotonic
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings
from app.database.models.mail_delivery import MailRateGateModel, MailWorkerPulseModel
from app.database.repositories.mail_delivery import MailDeliveryRepository
from app.database.repositories.mail_operations import MailOperationsRepository
from app.domain.mail_delivery import MailResult, MailSender, MailTransport
from app.domain.mail_operations import MAIL_PULSE_INTERVAL_SECONDS, MailWorkerActivity
from app.observability.logging import configure_logging
from app.providers.smtp_delivery import SmtpDelivery
from app.workflows.mail_delivery.workflow import (
    configured_sender,
    sender_fingerprint,
    transport_configured,
    verified_approval_required,
)

logger = logging.getLogger(__name__)


class MailWorker:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
        transport: MailTransport,
        sender: MailSender,
    ) -> None:
        self.sessions = sessions
        self.settings = settings
        self.transport = transport
        self.sender = sender
        self.sender_hash = sender_fingerprint(sender)
        self.verified_only = verified_approval_required(settings)
        self.last_poll: float | None = None
        self.last_completion: float | None = None

    def activity(self) -> MailWorkerActivity:
        now = monotonic()
        return MailWorkerActivity(
            self.sender_hash,
            self.verified_only,
            now - self.last_poll if self.last_poll is not None else None,
            now - self.last_completion if self.last_completion is not None else None,
        )

    async def run_once(self) -> bool:
        async with self.sessions.begin() as session:
            mail = await MailDeliveryRepository(session).claim(
                self.sender_hash,
                self.settings.mail_rate_per_second,
                contact_window_hours=self.settings.outreach_contact_window_hours,
                require_verified_approval=self.verified_only,
            )
        self.last_poll = monotonic()
        if mail is None:
            return False
        try:
            result = await self.transport.send(mail, self.sender)
        except Exception as exc:
            logger.error("Mail transport error (%s)", type(exc).__name__)
            result = MailResult("unknown", "smtp_unexpected_error")
        async with self.sessions.begin() as session:
            await MailDeliveryRepository(session).finish(
                mail,
                result,
                self.settings.mail_max_attempts,
            )
        self.last_completion = monotonic()
        return True

    async def lane(self, stop: asyncio.Event) -> None:
        poll = min(0.5, max(0.005, 0.5 / self.settings.mail_rate_per_second))
        delay = poll
        while not stop.is_set():
            try:
                if await self.run_once():
                    delay = poll
                    continue
                await _wait(stop, delay)
                delay = min(0.5, delay * 1.5)
            except Exception as exc:
                logger.error("Mail queue error (%s)", type(exc).__name__)
                await _wait(stop, 2)


async def _wait(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except TimeoutError:
        pass


async def recover(
    sessions: async_sessionmaker[AsyncSession],
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        try:
            async with sessions.begin() as session:
                await MailDeliveryRepository(session).recover()
        except Exception as exc:
            logger.error("Mail recovery error (%s)", type(exc).__name__)
        await _wait(stop, 10)


async def publish_activity(
    sessions: async_sessionmaker[AsyncSession],
    stop: asyncio.Event,
    instance_id: UUID,
    worker: MailWorker | None,
) -> None:
    idle = MailWorkerActivity(None, False, None, None)
    while not stop.is_set():
        try:
            activity = worker.activity() if worker is not None else idle
            async with sessions.begin() as session:
                await MailOperationsRepository(session).publish(instance_id, activity)
        except Exception as exc:
            logger.error("Mail worker pulse error (%s)", type(exc).__name__)
        await _wait(stop, MAIL_PULSE_INTERVAL_SECONDS)


async def run(*, check: bool = False) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    sender = configured_sender(settings)
    if (
        settings.mail_send_enabled
        and settings.app_env == "production"
        and settings.operator_identity_mode != "oidc"
    ):
        raise RuntimeError("Production mail delivery requires OIDC operator identity")
    if settings.mail_send_enabled and (sender is None or not transport_configured(settings)):
        raise RuntimeError(
            "Mail delivery is enabled but sender or SMTP configuration is incomplete"
        )
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        hide_parameters=True,
        pool_size=min(settings.mail_worker_concurrency + 1, 12),
        max_overflow=0,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    if check:
        try:
            async with sessions() as session:
                if await session.scalar(select(MailRateGateModel.id)) != 1:
                    raise RuntimeError("Mail delivery schema has not been initialized")
                await session.execute(select(MailWorkerPulseModel.id).limit(0))
        finally:
            await engine.dispose()
        return
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for stop_signal in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(stop_signal, stop.set)
    instance_id = uuid4()
    worker = (
        MailWorker(sessions, settings, SmtpDelivery(settings), sender)
        if settings.mail_send_enabled and sender is not None
        else None
    )
    try:
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(recover(sessions, stop))
            tasks.create_task(publish_activity(sessions, stop, instance_id, worker))
            if worker is not None:
                for _ in range(settings.mail_worker_concurrency):
                    tasks.create_task(worker.lane(stop))
    finally:
        try:
            async with sessions.begin() as session:
                operations = MailOperationsRepository(session)
                if worker is not None:
                    await operations.publish(instance_id, worker.activity())
                await operations.retire(instance_id)
        except Exception as exc:
            logger.error("Mail worker retirement error (%s)", type(exc).__name__)
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run(check=sys.argv[1:] == ["--check"]))
