"""Real PostgreSQL tests for campaign approval, competing workers and retries."""

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from time import monotonic
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.database.models.mail_delivery import MailDeliveryModel, MailRateGateModel
from app.database.repositories.mail_delivery import MailDeliveryRepository
from app.database.uow import SqlAlchemyUnitOfWork
from app.domain.clock import utcnow
from app.domain.mail_delivery import ClaimedMail, MailContent, MailResult, MailSender
from app.main import create_app
from app.services.email import FakeEmailDraftGenerator
from app.tasks.mail_delivery_worker import MailWorker
from app.workflows.email import EmailDraftGenerationWorkflow
from app.workflows.mail_delivery.workflow import configured_sender, sender_fingerprint
from tests.database.integration.conftest import (
    _replace_db,
    _run_sql_autocommit,
    run_alembic,
)
from tests.database.integration.test_email_draft_db import SENDER, seed_chain


@pytest.fixture
async def mail_engine(pg_settings: Settings) -> AsyncIterator[AsyncEngine]:
    # Separate database: concurrent sessions commit their changes for real.
    admin = pg_settings.database_url
    db_name = f"mail_test_{uuid4().hex}"
    await _run_sql_autocommit(admin, [f"CREATE DATABASE {db_name}"])
    engine = create_async_engine(_replace_db(admin, db_name))
    try:
        await asyncio.to_thread(run_alembic, ["upgrade", "head"], db_name)
        yield engine
    finally:
        await engine.dispose()
        await _run_sql_autocommit(admin, [f"DROP DATABASE {db_name} WITH (FORCE)"])


def configured_settings() -> Settings:
    return Settings(
        _env_file=None,
        mail_send_enabled=True,
        mail_from_address="freight@example.com",
        mail_from_name="Freight",
        mail_postal_address="123 Main Street",
        mail_signature="Alex / Freight",
        mail_public_origin="https://app.example.com",
        mail_smtp_host="smtp.example.com",
        mail_smtp_username="sender",
        mail_smtp_password="test-only",
        mail_feedback_secret="feedback-test-only",
        mail_rate_per_second=200,
    )


class RecordingTransport:
    def __init__(self, result: MailResult | None = None) -> None:
        self.transmissions: list[ClaimedMail] = []
        self.result = result or MailResult("accepted", "test_accepted")
        self.in_flight = 0
        self.peak = 0

    async def send(self, mail: ClaimedMail, sender: MailSender) -> MailResult:
        self.transmissions.append(mail)
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        await asyncio.sleep(0.04)
        self.in_flight -= 1
        return self.result


async def test_draft_snapshot_api_and_unsubscribe(mail_engine: AsyncEngine) -> None:
    sessions = async_sessionmaker(mail_engine, expire_on_commit=False)
    settings = configured_settings()
    app = create_app(settings)
    app.state.session_factory = sessions

    def uow() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(sessions)

    opportunity, contact_id = await seed_chain(uow)
    draft = await EmailDraftGenerationWorkflow(
        uow_factory=uow,
        generator=FakeEmailDraftGenerator(),
    ).handle(opportunity_id=opportunity.id, contact_id=contact_id, sender=SENDER)
    assert draft.outreach_id is not None
    campaign_id = uuid4()
    payload = {
        "id": str(campaign_id),
        "name": "One reviewed draft",
        "outreach_id": str(draft.outreach_id),
        "draft_version": 1,
        "recipient": "maria@phg.com",
        "subject": "Custom review",
    }
    root = f"/api/v1/mail-campaigns/{campaign_id}"
    sender = configured_sender(settings)
    assert sender is not None
    transport = RecordingTransport()
    worker = MailWorker(sessions, settings, transport, sender)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        wrong_recipient = await client.post(
            "/api/v1/mail-campaigns/draft",
            json={**payload, "recipient": "wrong@example.com"},
        )
        assert wrong_recipient.status_code == 422
        for _ in range(2):
            prepared = await client.post("/api/v1/mail-campaigns/draft", json=payload)
            assert prepared.status_code == 201, prepared.text
            assert prepared.json()["counts"] == {"pending": 1}
        conflict = await client.post(
            "/api/v1/mail-campaigns/draft",
            json={**payload, "subject": "Changed"},
        )
        assert conflict.status_code == 409
        assert not await worker.run_once()
        messages = await client.get(f"{root}/messages")
        item = messages.json()[0]
        assert item["subject"] == "Custom review"
        assert item["body"].endswith("Alex / Freight\n\n123 Main Street")
        path = f"/api/v1/mail-unsubscribe/{item['id']}"
        assert (await client.get(path)).status_code == 200
        settings.mail_send_enabled = False
        approved = await client.post(
            f"{root}/actions",
            json={"action": "approve", "actor": "Operator"},
        )
        assert approved.status_code == 409
        settings.mail_send_enabled = True
        approved = await client.post(
            f"{root}/actions",
            json={"action": "approve", "actor": "Operator"},
        )
        assert approved.status_code == 200
        assert await worker.run_once()
        assert (await client.get(root)).json()["counts"] == {"accepted": 1}
        assert (await client.get(root)).json()["feedback"] == {}
        for _ in range(2):
            response = await client.post(path, data={"List-Unsubscribe": "One-Click"})
            assert response.status_code == 200
        feedback = {
            "event_id": "test-event",
            "delivery_id": item["id"],
            "kind": "delivered",
        }
        assert (await client.post("/api/v1/mail-feedback", json=feedback)).status_code == 401
        for _ in range(2):
            response = await client.post(
                "/api/v1/mail-feedback",
                json=feedback,
                headers={"X-Mail-Feedback-Key": "feedback-test-only"},
            )
            assert response.status_code == 204
        assert (await client.get(root)).json()["feedback"] == {"unsubscribed": 1, "delivered": 1}


async def test_concurrent_workers_rate_dedup_retry_and_recovery(mail_engine: AsyncEngine) -> None:
    sessions = async_sessionmaker(mail_engine, expire_on_commit=False)
    settings = configured_settings()
    settings.mail_rate_per_second = 100
    sender = configured_sender(settings)
    assert sender is not None
    fingerprint = sender_fingerprint(sender)
    campaign_id = uuid4()

    def uow() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(sessions)

    opportunity, _ = await seed_chain(uow)

    async def seed(id_: UUID, rows: list[MailContent]) -> None:
        async with sessions.begin() as session:
            repo = MailDeliveryRepository(session)
            await repo.create(id_, "Queue test", "x", fingerprint, sender.address, rows)
            await repo.transition(id_, "approve", "Operator", fingerprint)

    data = [
        MailContent(
            f"test:{campaign_id}:{i}",
            opportunity.company_id,
            f"buyer{i}@example.com",
            "Subject",
            "Body",
        )
        for i in range(60)
    ]
    await seed(campaign_id, data)
    async with sessions.begin() as session:
        await MailDeliveryRepository(session).transition(campaign_id, "pause", "Operator", None)

    transport = RecordingTransport()
    workers = [MailWorker(sessions, settings, transport, sender) for _ in range(2)]
    assert not await workers[0].run_once()
    async with sessions.begin() as session:
        await MailDeliveryRepository(session).transition(
            campaign_id,
            "resume",
            "Operator",
            fingerprint,
        )

    async def drain(worker: MailWorker) -> None:
        async with asyncio.timeout(15):
            while len(transport.transmissions) < len(data):
                if not await worker.run_once():
                    await asyncio.sleep(0.005)

    started = monotonic()
    await asyncio.gather(*(drain(workers[i % 2]) for i in range(16)))
    elapsed = monotonic() - started
    assert elapsed >= (len(data) - 1) / settings.mail_rate_per_second
    assert len({item.id for item in transport.transmissions}) == len(data)
    assert transport.peak > 1
    async with sessions() as session:
        assert (await MailDeliveryRepository(session).summary(campaign_id)).counts == {
            "accepted": len(data),
        }

    duplicate_id = uuid4()
    await seed(duplicate_id, data[:1])
    async with sessions.begin() as session:
        await session.execute(update(MailRateGateModel).values(next_slot=utcnow()))
    assert not await workers[0].run_once()
    async with sessions() as session:
        assert (await MailDeliveryRepository(session).summary(duplicate_id)).counts == {
            "suppressed": 1,
        }

    recovery_id = uuid4()
    await seed(
        recovery_id,
        [
            MailContent(
                f"test:{recovery_id}",
                opportunity.company_id,
                "another@example.com",
                "Subject",
                "Body",
            ),
        ],
    )
    retry_transport = RecordingTransport(MailResult("retry", "smtp_451"))
    retry_worker = MailWorker(sessions, settings, retry_transport, sender)
    assert await retry_worker.run_once()
    assert not await retry_worker.run_once()
    async with sessions.begin() as session:
        await session.execute(
            update(MailDeliveryModel)
            .where(MailDeliveryModel.campaign_id == recovery_id)
            .values(available_at=utcnow())
        )
        claimed = await MailDeliveryRepository(session).claim(fingerprint, 100)
        assert claimed is not None and claimed.attempt == 2
    async with sessions.begin() as session:
        await session.execute(
            update(MailDeliveryModel)
            .where(MailDeliveryModel.id == claimed.id)
            .values(lease_until=utcnow() - timedelta(seconds=1))
        )
        await MailDeliveryRepository(session).recover()
    assert not await workers[0].run_once()
    async with sessions() as session:
        status = await session.scalar(
            select(MailDeliveryModel.status).where(MailDeliveryModel.id == claimed.id)
        )
        assert status == "unknown"
