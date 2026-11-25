"""Prepare an approved, immutable campaign from existing prospect data."""

import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from email.errors import HeaderParseError
from email.headerregistry import Address
from string import Formatter
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from app.core.config import Settings
from app.domain.exceptions import InvalidEmailAddress
from app.domain.mail_delivery import (
    CampaignSummary,
    MailCampaignStore,
    MailContent,
    MailSender,
    MailSource,
)
from app.domain.operator import AuditActor
from app.domain.values import EmailAddress
from app.shared.exceptions import ApplicationConflictError, InvalidInputError

MailAction = Literal["approve", "pause", "resume", "cancel"]


@dataclass(frozen=True, slots=True)
class CampaignRequest:
    id: UUID
    name: str
    export_id: UUID | None
    outreach_id: UUID | None
    draft_version: int | None
    recipient: str | None
    subject: str | None
    body: str | None


def _fingerprint(data: object) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def sender_fingerprint(sender: MailSender) -> str:
    return _fingerprint(asdict(sender))


def _address(raw: str) -> str:
    try:
        value = EmailAddress(raw).value
        # The transport uses SMTP ASCII envelope addresses and MIME for display text.
        if not value.isascii():
            raise ValueError
        Address(addr_spec=value)
        return value
    except (InvalidEmailAddress, ValueError, HeaderParseError):
        raise InvalidInputError(
            code="mail_invalid_address",
            message="An email address is invalid",
        ) from None


def configured_sender(settings: Settings) -> MailSender | None:
    if not settings.mail_from_address or not settings.mail_postal_address:
        return None
    try:
        origin = urlsplit(settings.mail_public_origin.strip())
        address = _address(settings.mail_from_address)
        reply_to = _address(settings.mail_reply_to.strip() or address)
    except (InvalidInputError, ValueError):
        return None
    if (
        origin.scheme != "https"
        or not origin.netloc
        or not origin.hostname
        or origin.path not in ("", "/")
        or origin.username is not None
        or origin.query
        or origin.fragment
        or not settings.mail_postal_address.strip()
        or any(ord(char) < 32 for char in settings.mail_from_name)
    ):
        return None
    return MailSender(
        address,
        settings.mail_from_name.strip(),
        reply_to,
        settings.mail_postal_address.strip(),
        origin.geturl().rstrip("/"),
        settings.mail_signature.strip(),
    )


def transport_configured(settings: Settings) -> bool:
    return bool(
        settings.mail_send_enabled
        and settings.mail_smtp_host.strip()
        and settings.mail_smtp_username
        and settings.mail_smtp_password.get_secret_value()
    )


def _render(text: str, source: MailSource) -> str:
    values = {
        "first_name": source.first_name or "there",
        "company": source.company_name,
        "job_title": source.job_title,
    }
    try:
        for _, field, spec, conversion in Formatter().parse(text):
            if field is not None and (field not in values or spec or conversion):
                raise ValueError
        return text.format_map(values)
    except ValueError:
        raise InvalidInputError(
            code="mail_invalid_template",
            message="Use only {first_name}, {company} or {job_title} as template variables",
        ) from None


class MailCampaignWorkflow:
    def __init__(
        self,
        repository: MailCampaignStore,
        commit: Callable[[], Awaitable[None]],
        settings: Settings,
    ) -> None:
        self.commit = commit
        self.repository = repository
        self.sender = configured_sender(settings)
        self.requires_verified_actor = (
            settings.app_env == "production" or settings.operator_identity_mode == "oidc"
        )
        self.send_ready = (
            self.sender is not None
            and transport_configured(settings)
            and (settings.app_env != "production" or settings.operator_identity_mode == "oidc")
        )

    async def prepare(
        self, request: CampaignRequest, actor: AuditActor | None = None,
    ) -> CampaignSummary:
        sender = self.sender
        if sender is None:
            raise ApplicationConflictError(
                "Configure the mail sender and HTTPS public origin first"
            )
        request_hash = _fingerprint(asdict(request))
        previous = await self.repository.request_hash(request.id)
        if previous is None:
            contents = await self._contents(request, sender)
            await self.repository.create(
                request.id,
                request.name,
                request_hash,
                sender_fingerprint(sender),
                sender.address,
                contents,
                actor,
            )
            previous = await self.repository.request_hash(request.id)
        if previous != request_hash:
            raise ApplicationConflictError("This request ID already identifies another campaign")
        await self.commit()
        return await self.repository.summary(request.id)

    async def _contents(self, request: CampaignRequest, sender: MailSender) -> list[MailContent]:
        if request.export_id is not None:
            sources = await self.repository.template_sources(request.export_id)
        else:
            assert request.outreach_id is not None and request.draft_version is not None
            sources = await self.repository.draft_sources(
                request.outreach_id, request.draft_version
            )
            sources = [
                item for item in sources if item.recipient == _address(request.recipient or "")
            ]
        if not 1 <= len(sources) <= 1000:
            raise InvalidInputError(
                code="mail_no_eligible_source",
                message="Select a valid draft recipient or an export with 1–1000 ready contacts",
            )

        contents: list[MailContent] = []
        seen: set[str] = set()
        for source in sources:
            recipient = _address(source.recipient)
            if recipient in seen:
                continue
            seen.add(recipient)
            subject = request.subject if request.subject is not None else source.subject
            body = request.body if request.body is not None else source.body
            if request.export_id is not None:
                subject = _render(subject, source)
                body = _render(body, source)
            if (
                not subject.strip()
                or len(subject) > 200
                or any(ord(char) < 32 for char in subject)
                or not body.strip()
                or len(body) > 20000
            ):
                raise InvalidInputError(
                    code="mail_invalid_content",
                    message="Rendered subject or body is invalid",
                )
            body = "\n\n".join(
                part
                for part in (
                    body.strip(),
                    sender.signature,
                    sender.postal_address,
                )
                if part
            )
            contents.append(MailContent(source.key, source.company_id, recipient, subject, body))
        return contents

    async def change(
        self,
        campaign_id: UUID,
        action: MailAction,
        actor: AuditActor,
    ) -> CampaignSummary:
        if action in ("approve", "resume") and self.requires_verified_actor and not actor.verified:
            raise ApplicationConflictError(
                "A verified staff login is required to activate delivery"
            )
        sender_hash = (
            sender_fingerprint(self.sender) if self.send_ready and self.sender is not None else None
        )
        await self.repository.transition(campaign_id, action, actor, sender_hash)
        await self.commit()
        return await self.repository.summary(campaign_id)
