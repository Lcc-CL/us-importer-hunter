"""Verified, transactional reconciliation against a real PostgreSQL queue."""

import asyncio
from datetime import timedelta
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.database.models.contact_touch import ContactTouchModel
from app.database.models.mail_delivery import MailDeliveryModel, MailSourceReservationModel
from app.database.repositories.mail_delivery import MailDeliveryRepository
from app.database.uow import SqlAlchemyUnitOfWork
from app.domain.clock import utcnow
from app.domain.mail_delivery import MailContent, MailResult, ReconciliationEvidence
from app.domain.operator import AuditActor
from app.main import create_app
from app.tasks.mail_delivery_worker import MailWorker
from app.workflows.mail_delivery.workflow import configured_sender, sender_fingerprint
from tests.api.test_operator_identity import TestIssuer
from tests.database.integration.test_email_draft_db import seed_chain
from tests.database.integration.test_mail_delivery import (
    RecordingTransport,
    configured_settings,
)
from tests.database.integration.test_mail_delivery import mail_engine as mail_engine

VERIFIED = AuditActor("Test approver", "https://login.example.test", "approver")


async def _content(sessions: async_sessionmaker[AsyncSession]) -> MailContent:
    def uow() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(sessions)

    opportunity, _ = await seed_chain(uow)
    return MailContent(
        "reconciliation-source",
        opportunity.company_id,
        "buyer@example.test",
        "Test subject",
        "Test body",
    )


async def _campaign(
    sessions: async_sessionmaker[AsyncSession],
    fingerprint: str,
    content: MailContent,
    *,
    approve: bool = True,
) -> UUID:
    campaign_id = uuid4()
    async with sessions.begin() as session:
        repo = MailDeliveryRepository(session)
        await repo.create(
            campaign_id, "Test", "request", fingerprint, "freight@example.com", [content]
        )
        if approve:
            await repo.transition(campaign_id, "approve", VERIFIED, fingerprint)
    return campaign_id


async def test_verified_roles_replay_and_fresh_approval(mail_engine: AsyncEngine) -> None:
    sessions = async_sessionmaker(mail_engine, expire_on_commit=False)
    settings = configured_settings()
    settings.app_env = "production"
    issuer = TestIssuer()
    verifier = issuer.configure(settings)
    app = create_app(settings)
    app.state.operator_verifier = verifier
    app.state.session_factory = sessions
    legacy_app = create_app(configured_settings())
    legacy_app.state.session_factory = sessions

    sender = configured_sender(settings)
    assert sender is not None
    fingerprint = sender_fingerprint(sender)
    content = await _content(sessions)
    original = await _campaign(sessions, fingerprint, content)
    transport = RecordingTransport(MailResult("unknown", "smtp_submission_unconfirmed"))
    worker = MailWorker(sessions, settings, transport, sender)
    assert await worker.run_once()
    delivery = transport.transmissions[0]
    path = f"/api/v1/mail-campaigns/{original}/messages/{delivery.id}/reconciliations"
    approval = issuer.headers("approver", "reviewer")
    administrator = issuer.headers("admin", "owner")
    sales = issuer.headers("sales", "seller")
    evidence = {
        "attempt": delivery.attempt,
        "decision": "not_submitted",
        "provider_reference": "relay incident #1",
        "note": "Relay confirmed no submission and the client attempt ended.",
    }

    async with AsyncClient(transport=ASGITransport(app=legacy_app), base_url="https://test") as cli:
        assert (await cli.post(path, json=evidence)).status_code == 403

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        assert (await client.post(path, json=evidence, headers=sales)).status_code == 403
        assert (await client.post(path, json=evidence, headers=approval)).status_code == 403
        wrong_attempt = await client.post(
            path,
            json={**evidence, "attempt": delivery.attempt + 1},
            headers=administrator,
        )
        assert wrong_attempt.status_code == 409
        wrong_campaign = path.replace(str(original), str(uuid4()))
        assert (
            await client.post(wrong_campaign, json=evidence, headers=administrator)
        ).status_code == 404
        listing = await client.get(
            f"/api/v1/mail-campaigns/{original}/messages?status=unknown",
            headers=approval,
        )
        assert listing.json()[0]["message_id"] == f"<{delivery.id}@example.com>"

        first, replay = await asyncio.gather(
            *(client.post(path, json=evidence, headers=administrator) for _ in range(2))
        )
        assert first.status_code == replay.status_code == 200
        assert first.json() == replay.json()
        assert first.json()["actor"]["subject"] == "owner"
        assert (await client.get(path, headers=sales)).status_code == 403
        assert (await client.get(path, headers=approval)).json() == [first.json()]
        different = await client.post(
            path,
            json={**evidence, "decision": "accepted"},
            headers=administrator,
        )
        assert different.status_code == 409
        assert (
            await client.get(
                f"/api/v1/mail-campaigns/{original}/messages?status=unknown",
                headers=approval,
            )
        ).json() == []

    async with sessions() as session:
        row = await session.get(MailDeliveryModel, delivery.id)
        touch = await session.get(ContactTouchModel, ("smtp", delivery.id))
        assert row is not None and row.status == "failed" and row.attempt == delivery.attempt
        assert touch is not None and touch.state == "released"
        assert await session.get(MailSourceReservationModel, content.source_key) is None

    replacement = await _campaign(sessions, fingerprint, content, approve=False)
    assert not await worker.run_once()
    async with sessions.begin() as session:
        await MailDeliveryRepository(session).transition(
            replacement,
            "approve",
            VERIFIED,
            fingerprint,
        )
    assert await worker.run_once()
    assert transport.transmissions[1].id != delivery.id


async def test_late_smtp_receipt_preserves_audit_and_blocks_replacement(
    mail_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(mail_engine, expire_on_commit=False)
    settings = configured_settings()
    sender = configured_sender(settings)
    assert sender is not None
    fingerprint = sender_fingerprint(sender)
    content = await _content(sessions)
    original = await _campaign(sessions, fingerprint, content)
    async with sessions.begin() as session:
        repo = MailDeliveryRepository(session)
        delivery = await repo.claim(fingerprint, 200)
        assert delivery is not None
        await session.execute(
            update(MailDeliveryModel)
            .where(MailDeliveryModel.id == delivery.id)
            .values(lease_until=utcnow() - timedelta(minutes=1))
        )
        await repo.recover()

    evidence = ReconciliationEvidence(
        delivery.attempt,
        "not_submitted",
        "relay incident #2",
        "Verified client stopped.",
    )
    async with sessions.begin() as session:
        await MailDeliveryRepository(session).reconcile(original, delivery.id, evidence, VERIFIED)
    replacement = await _campaign(sessions, fingerprint, content)

    async with sessions.begin() as session:
        repo = MailDeliveryRepository(session)
        await repo.finish(delivery, MailResult("accepted", "smtp_accepted"), 3)
        touch = await session.get(ContactTouchModel, ("smtp", delivery.id))
        assert touch is not None and touch.state == "confirmed"
        history = await repo.delivery_reconciliations(original, delivery.id)
        assert len(history) == 1 and history[0].evidence == evidence
        mail = (await repo.preview(original, 0, 1))[0]
        assert mail.status == "accepted" and mail.result_code == "smtp_late_acceptance"
        assert await repo.claim(fingerprint, 200) is None
        blocked = (await repo.preview(replacement, 0, 1))[0]
        assert blocked.result_code == "recent_or_reserved_touch"


async def test_approver_can_confirm_provider_acceptance(mail_engine: AsyncEngine) -> None:
    sessions = async_sessionmaker(mail_engine, expire_on_commit=False)
    settings = configured_settings()
    issuer = TestIssuer()
    verifier = issuer.configure(settings)
    app = create_app(settings)
    app.state.operator_verifier = verifier
    app.state.session_factory = sessions
    sender = configured_sender(settings)
    assert sender is not None
    fingerprint = sender_fingerprint(sender)
    campaign = await _campaign(sessions, fingerprint, await _content(sessions))
    transport = RecordingTransport(MailResult("unknown", "smtp_submission_unconfirmed"))
    assert await MailWorker(sessions, settings, transport, sender).run_once()
    delivery = transport.transmissions[0]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        result = await client.post(
            f"/api/v1/mail-campaigns/{campaign}/messages/{delivery.id}/reconciliations",
            headers=issuer.headers("approver", "reviewer"),
            json={
                "attempt": delivery.attempt,
                "decision": "accepted",
                "provider_reference": "relay log #3",
                "note": "SMTP 250 acceptance recorded.",
            },
        )
        assert result.status_code == 200, result.text
    async with sessions() as session:
        preview = (await MailDeliveryRepository(session).preview(campaign, 0, 1))[0]
        assert preview.status == "accepted" and preview.result_code == "operator_accepted"
        touch = await session.get(ContactTouchModel, ("smtp", delivery.id))
        assert touch is not None and touch.state == "confirmed"
