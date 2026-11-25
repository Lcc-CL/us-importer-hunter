"""Test authenticated provider events and delivery evidence in PostgreSQL."""

import json
from datetime import timedelta
from hmac import digest

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.database.models.contact_touch import ContactTouchModel
from app.database.models.umail_export import SuppressionEntryModel
from app.domain.clock import utcnow
from app.domain.mail_delivery import MailResult, smtp_message_id
from app.main import create_app
from app.services.email.feedback import MAIL_FEEDBACK_MAX_BYTES
from app.tasks.mail_delivery_worker import MailWorker
from app.workflows.mail_delivery.workflow import configured_sender, sender_fingerprint
from tests.api.test_operator_identity import TestIssuer
from tests.database.integration.test_mail_delivery import RecordingTransport, configured_settings
from tests.database.integration.test_mail_delivery import mail_engine as mail_engine
from tests.database.integration.test_mail_reconciliation import _campaign, _content

SIGNING_KEY = "relay-signing-test-credential"
SIGNED_PATH = "/api/v1/mail-feedback/v1"


def signed_headers(body: bytes, *, age: int = 0) -> dict[str, str]:
    stamp = str(int(utcnow().timestamp()) - age)
    data = f"hunter-mail-feedback-v1.{stamp}.".encode() + body
    return {
        "Content-Type": "application/json",
        "X-Mail-Feedback-Timestamp": stamp,
        "X-Mail-Feedback-Signature": f"v1={digest(SIGNING_KEY.encode(), data, 'sha256').hex()}",
    }


async def test_signed_feedback_validates_events_and_preserves_evidence(
    mail_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(mail_engine, expire_on_commit=False)
    settings = configured_settings()
    settings.mail_feedback_signing_secret = SecretStr(SIGNING_KEY)
    settings.app_env = "production"
    issuer = TestIssuer()
    verifier = issuer.configure(settings)
    app = create_app(settings)
    app.state.operator_verifier = verifier
    app.state.session_factory = sessions
    sender = configured_sender(settings)
    assert sender is not None
    content = await _content(sessions)
    campaign = await _campaign(sessions, sender_fingerprint(sender), content)
    transport = RecordingTransport(MailResult("unknown", "smtp_submission_unconfirmed"))
    assert await MailWorker(sessions, settings, transport, sender).run_once()
    delivery = transport.transmissions[0]
    message_id = smtp_message_id(delivery.id, sender.address)
    receipt_time = utcnow() - timedelta(seconds=4)
    main_event: dict[str, str] = {
        "provider": "relay-a",
        "event_id": "delivery-1",
        "message_id": message_id,
        "occurred_at": receipt_time.isoformat(),
        "kind": "delivered",
    }
    body = json.dumps(main_event).encode()
    approval = issuer.headers("approver", "reviewer")
    timeline = f"/api/v1/mail-campaigns/{campaign}/messages/{delivery.id}/feedback"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        blocked_legacy = await client.post(
            "/api/v1/mail-feedback",
            headers={"X-Mail-Feedback-Key": "feedback-test-only"},
            json={"delivery_id": str(delivery.id), "event_id": "legacy", "kind": "delivered"},
        )
        assert blocked_legacy.status_code == 401
        assert (await client.post(SIGNED_PATH, content=body)).status_code == 401
        bad_signature = await client.post(
            SIGNED_PATH,
            content=body + b" ",
            headers=signed_headers(body),
        )
        assert bad_signature.status_code == 401
        expired = await client.post(
            SIGNED_PATH,
            content=body,
            headers=signed_headers(body, age=600),
        )
        assert expired.status_code == 401
        huge = b" " * (MAIL_FEEDBACK_MAX_BYTES + 1)
        assert (
            await client.post(
                SIGNED_PATH,
                content=huge,
                headers=signed_headers(huge),
            )
        ).status_code == 413
        assert (await client.get(timeline, headers=approval)).json() == []

        for _ in range(2):
            response = await client.post(SIGNED_PATH, content=body, headers=signed_headers(body))
            assert response.status_code == 204, response.text

        async def send(event: dict[str, str]) -> int:
            encoded = json.dumps(event, separators=(",", ":")).encode()
            return (
                await client.post(SIGNED_PATH, content=encoded, headers=signed_headers(encoded))
            ).status_code

        assert await send({**main_event, "kind": "hard_bounced"}) == 409
        assert await send({**main_event, "message_id": f"<{delivery.id}@wrong.example>"}) == 404
        assert (
            await send(
                {**main_event, "occurred_at": (utcnow() + timedelta(minutes=10)).isoformat()}
            )
            == 422
        )
        # Different provider namespace; event date is older, so the touch date
        # from the delivery proof must stay fixed.
        assert (
            await send(
                {
                    **main_event,
                    "provider": "relay-b",
                    "occurred_at": (receipt_time - timedelta(seconds=1)).isoformat(),
                    "kind": "hard_bounced",
                }
            )
            == 204
        )
        unsubscribe = await client.post(
            f"/api/v1/mail-unsubscribe/{delivery.id}",
            data={"List-Unsubscribe": "One-Click"},
        )
        assert unsubscribe.status_code == 200

        assert (await client.get(timeline)).status_code == 401
        assert (
            await client.get(
                timeline,
                headers=issuer.headers("sales", "seller"),
            )
        ).status_code == 403
        timeline_response = await client.get(timeline, headers=approval)
        assert timeline_response.status_code == 200
        events = timeline_response.json()
        assert [event["source"] for event in events] == [
            "one_click",
            "provider:relay-b",
            "provider:relay-a",
        ]
        assert [event["kind"] for event in events] == ["unsubscribed", "hard_bounced", "delivered"]
        assert events[0]["occurred_at"] is None
        assert events[2]["message_id"] == message_id
        assert (
            await client.get(timeline + "?limit=1&offset=1", headers=approval)
        ).json() == events[1:2]

    async with sessions() as session:
        touch = await session.get(ContactTouchModel, ("smtp", delivery.id))
        assert touch is not None and touch.state == "confirmed"
        assert touch.confirmed_at == receipt_time
        suppression = await session.scalar(
            select(SuppressionEntryModel).where(
                SuppressionEntryModel.email == content.recipient,
                SuppressionEntryModel.active.is_(True),
            )
        )
        assert suppression is not None and suppression.reason == "hard_bounced"
