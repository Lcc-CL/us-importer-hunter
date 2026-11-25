"""Queue diagnostics against PostgreSQL and verified session roles."""

from datetime import timedelta
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.database.models.mail_delivery import (
    MailCampaignModel,
    MailDeliveryModel,
    MailWorkerPulseModel,
)
from app.database.repositories.mail_delivery import MailDeliveryRepository
from app.database.repositories.mail_operations import MailOperationsRepository
from app.domain.clock import utcnow
from app.domain.mail_delivery import MailContent
from app.domain.mail_operations import MAIL_PULSE_TTL_SECONDS, MailWorkerActivity
from app.main import create_app
from app.tasks.mail_delivery_worker import MailWorker
from app.workflows.mail_delivery.operations import read_mail_operations
from app.workflows.mail_delivery.workflow import configured_sender, sender_fingerprint
from tests.api.test_operator_identity import TestIssuer
from tests.database.integration.test_mail_delivery import RecordingTransport, configured_settings
from tests.database.integration.test_mail_delivery import mail_engine as mail_engine
from tests.database.integration.test_mail_reconciliation import _campaign, _content


async def test_operations_api_counts_only_real_backlog(mail_engine: AsyncEngine) -> None:
    sessions = async_sessionmaker(mail_engine, expire_on_commit=False)
    settings = configured_settings()
    settings.app_env = "production"
    issuer = TestIssuer()
    verifier = issuer.configure(settings)
    app = create_app(settings)
    app.state.operator_verifier = verifier
    app.state.session_factory = sessions

    sender = configured_sender(settings)
    assert sender is not None
    fingerprint = sender_fingerprint(sender)
    now = utcnow()
    states = [
        ("ready", "active", "pending", fingerprint, True, now - timedelta(minutes=4)),
        ("scheduled", "active", "pending", fingerprint, True, now + timedelta(minutes=4)),
        ("blocked_sender", "active", "pending", "stale-sender", True, now),
        ("blocked_approval", "active", "pending", fingerprint, False, now),
        ("paused", "paused", "pending", fingerprint, True, now),
        ("draft", "draft", "pending", fingerprint, True, now),
        ("cancelled", "cancelled", "pending", fingerprint, True, now),
        ("sending", "active", "sending", fingerprint, True, now),
        ("expired", "cancelled", "sending", fingerprint, True, now),
        ("unknown", "cancelled", "unknown", "stale-sender", True, now),
        ("accepted", "active", "accepted", fingerprint, True, now),
    ]
    async with sessions.begin() as session:
        repo = MailDeliveryRepository(session)
        for name, campaign_status, status, sender_hash, verified, available_at in states:
            campaign_id = uuid4()
            await repo.create(
                campaign_id,
                name,
                "request",
                sender_hash,
                sender.address,
                [MailContent(name, uuid4(), f"{name}@example.test", "Subject", "Body")],
            )
            await session.execute(
                update(MailCampaignModel)
                .where(MailCampaignModel.id == campaign_id)
                .values(
                    status=campaign_status,
                    approved_subject="owner" if verified else None,
                    approved_issuer="test-issuer" if verified else None,
                )
            )
            await session.execute(
                update(MailDeliveryModel)
                .where(MailDeliveryModel.campaign_id == campaign_id)
                .values(
                    status=status,
                    available_at=available_at,
                    lease_until=(now - timedelta(seconds=1) if name == "expired" else None),
                )
            )

    path = "/api/v1/mail-campaigns/operations"
    editor = issuer.headers("approver", "reviewer")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        assert (await client.get(path)).status_code == 401
        assert (
            await client.get(path, headers=issuer.headers("sales", "seller"))
        ).status_code == 403
        response = await client.get(path, headers=editor)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["dispatch_state"] == "no_worker"
        queue = payload["queue"]
        assert {
            key: queue[key]
            for key in (
                "ready",
                "scheduled",
                "blocked",
                "paused",
                "in_flight",
                "expired_leases",
                "unknown",
            )
        } == {
            "ready": 1,
            "scheduled": 1,
            "blocked": 2,
            "paused": 1,
            "in_flight": 2,
            "expired_leases": 1,
            "unknown": 1,
        }
        assert 239 <= queue["oldest_ready_seconds"] < 300
        assert queue["last_completion_at"] is None

        instance = uuid4()
        incompatible = uuid4()
        async with sessions.begin() as session:
            ops = MailOperationsRepository(session)
            await ops.publish(instance, MailWorkerActivity(fingerprint, True, 60, None))
        stale = (await client.get(path, headers=editor)).json()
        assert stale["dispatch_state"] == "poll_stale"
        assert stale["queue"]["live_workers"] == 1
        assert stale["queue"]["polling_workers"] == 0

        async with sessions.begin() as session:
            ops = MailOperationsRepository(session)
            await ops.publish(instance, MailWorkerActivity(fingerprint, True, 0, 0))
            await ops.publish(incompatible, MailWorkerActivity("old-sender", True, 0, None))
        mismatch = (await client.get(path, headers=editor)).json()
        assert mismatch["dispatch_state"] == "worker_config_mismatch"
        assert mismatch["queue"]["dispatch_workers"] == 2
        assert mismatch["queue"]["polling_workers"] == 1

        async with sessions.begin() as session:
            await session.execute(
                update(MailWorkerPulseModel)
                .where(MailWorkerPulseModel.id == incompatible)
                .values(seen_at=utcnow() - timedelta(seconds=MAIL_PULSE_TTL_SECONDS + 1))
            )
        running = (await client.get(path, headers=editor)).json()
        assert running["dispatch_state"] == "polling"
        assert running["queue"]["last_completion_at"] is not None
        settings.mail_send_enabled = False
        assert (await client.get(path, headers=editor)).json()[
            "dispatch_state"
        ] == "worker_config_mismatch"


async def test_worker_reports_poll_and_completion_independently(mail_engine: AsyncEngine) -> None:
    sessions = async_sessionmaker(mail_engine, expire_on_commit=False)
    settings = configured_settings()
    sender = configured_sender(settings)
    assert sender is not None
    fingerprint = sender_fingerprint(sender)
    worker = MailWorker(sessions, settings, RecordingTransport(), sender)

    assert worker.activity().poll_age_seconds is None
    assert not await worker.run_once()
    assert worker.activity().poll_age_seconds is not None
    assert worker.activity().completion_age_seconds is None
    await _campaign(sessions, fingerprint, await _content(sessions))
    assert await worker.run_once()
    assert worker.activity().completion_age_seconds is not None

    instance = uuid4()
    async with sessions.begin() as session:
        repo = MailOperationsRepository(session)
        await repo.publish(instance, worker.activity())
        reported = await read_mail_operations(repo, settings)
        assert reported.dispatch_state == "polling"
        assert reported.queue.ready == 0
        assert reported.queue.oldest_ready_seconds is None
        assert reported.queue.last_poll_at is not None
        assert reported.queue.last_completion_at is not None
        await repo.retire(instance)
        retired = await read_mail_operations(repo, settings)
        assert retired.dispatch_state == "no_worker"
        assert retired.queue.live_workers == 0
        assert retired.queue.last_completion_at == reported.queue.last_completion_at

    settings.mail_send_enabled = False
    async with sessions() as session:
        disabled = await read_mail_operations(MailOperationsRepository(session), settings)
        assert disabled.dispatch_state == "disabled"
