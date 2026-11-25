"""SMTP result classification and envelope contract without real mail."""

import smtplib
from email.message import EmailMessage
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.domain.mail_delivery import ClaimedMail, MailSender
from app.providers.smtp_delivery import SmtpDelivery


@pytest.mark.parametrize(
    ("error", "outcome"),
    [
        (None, "accepted"),
        (smtplib.SMTPDataError(451, b"temporarily rejected"), "retry"),
        (smtplib.SMTPDataError(550, b"permanently rejected"), "failed"),
        (smtplib.SMTPServerDisconnected("lost after submit"), "unknown"),
    ],
)
async def test_smtp_envelope_and_submission_outcome(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception | None,
    outcome: str,
) -> None:
    client = MagicMock()
    constructor = MagicMock(return_value=client)
    client.send_message.side_effect = error
    monkeypatch.setattr(smtplib, "SMTP", constructor)
    settings = Settings(
        _env_file=None,
        mail_smtp_host="relay.example.com",
        mail_smtp_username="sender",
        mail_smtp_password="test-only",
    )
    sender = MailSender(
        "freight@example.com",
        "Freight",
        "sales@example.com",
        "Main Street",
        "https://app.example.com",
        "",
    )
    mail = ClaimedMail(uuid4(), 1, "buyer@example.org", "Subject", "Body")
    result = await SmtpDelivery(settings).send(mail, sender)
    assert result.outcome == outcome
    client.starttls.assert_called_once()
    client.login.assert_called_once_with("sender", "test-only")
    args, options = client.send_message.call_args
    message = args[0]
    assert isinstance(message, EmailMessage)
    assert message["Message-ID"] == f"<{mail.id}@example.com>"
    assert message["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert sender.unsubscribe_url(mail.id) in message.get_content()
    assert options == {"from_addr": "freight@example.com", "to_addrs": ["buyer@example.org"]}
    client.close.assert_called_once()
