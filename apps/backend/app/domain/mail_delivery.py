"""Values shared by the delivery workflow, queue and transport."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from app.domain.operator import AuditActor

DeliveryOutcome = Literal["accepted", "retry", "failed", "unknown"]
FeedbackKind = Literal["delivered", "hard_bounced", "unsubscribed", "complained"]
ReconciliationDecision = Literal["accepted", "not_submitted"]


def smtp_message_id(delivery_id: UUID, sender_address: str) -> str:
    return f"<{delivery_id}@{sender_address.rsplit('@', 1)[-1]}>"


@dataclass(frozen=True, slots=True)
class MailSender:
    address: str
    name: str
    reply_to: str
    postal_address: str
    public_origin: str
    signature: str

    def unsubscribe_url(self, delivery_id: UUID) -> str:
        return f"{self.public_origin}/api/v1/mail-unsubscribe/{delivery_id}"


@dataclass(frozen=True, slots=True)
class MailContent:
    source_key: str
    company_id: UUID
    recipient: str
    subject: str
    body: str


@dataclass(frozen=True, slots=True)
class ClaimedMail:
    id: UUID
    attempt: int
    recipient: str
    subject: str
    body: str


@dataclass(frozen=True, slots=True)
class MailResult:
    outcome: DeliveryOutcome
    code: str


class MailTransport(Protocol):
    async def send(self, mail: ClaimedMail, sender: MailSender) -> MailResult: ...


@dataclass(frozen=True, slots=True)
class MailSource:
    key: str
    company_id: UUID
    company_name: str
    recipient: str
    first_name: str
    job_title: str
    subject: str = ""
    body: str = ""


@dataclass(frozen=True, slots=True)
class CampaignSummary:
    id: UUID
    name: str
    status: str
    sender_address: str
    approved_by: str | None
    counts: dict[str, int]
    feedback: dict[str, int]


@dataclass(frozen=True, slots=True)
class MailPreview:
    id: UUID
    recipient: str
    subject: str
    body: str
    status: str
    attempt: int
    result_code: str | None
    message_id: str


@dataclass(frozen=True, slots=True)
class CampaignAuditEvent:
    id: UUID
    action: str
    actor_name: str
    actor_issuer: str | None
    actor_subject: str | None
    from_status: str | None
    to_status: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class ReconciliationEvidence:
    attempt: int
    decision: ReconciliationDecision
    provider_reference: str
    note: str


@dataclass(frozen=True, slots=True)
class DeliveryReconciliation:
    delivery_id: UUID
    evidence: ReconciliationEvidence
    actor: AuditActor
    resolved_at: datetime


@dataclass(frozen=True, slots=True)
class ProviderMailEvidence:
    provider: str
    message_id: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class MailFeedbackEvent:
    event_key: str
    kind: FeedbackKind
    source: str
    message_id: str | None
    occurred_at: datetime | None
    received_at: datetime


class MailCampaignStore(Protocol):
    async def template_sources(self, batch_id: UUID) -> list[MailSource]: ...

    async def draft_sources(self, outreach_id: UUID, version: int) -> list[MailSource]: ...

    async def request_hash(self, campaign_id: UUID) -> str | None: ...

    async def create(
        self,
        campaign_id: UUID,
        name: str,
        request_hash: str,
        sender_hash: str,
        sender_address: str,
        contents: list[MailContent],
        actor: AuditActor | None = None,
    ) -> None: ...

    async def summary(self, campaign_id: UUID) -> CampaignSummary: ...

    async def transition(
        self,
        campaign_id: UUID,
        action: str,
        actor: AuditActor,
        sender_hash: str | None,
    ) -> None: ...

    async def reconcile(
        self,
        campaign_id: UUID,
        delivery_id: UUID,
        evidence: ReconciliationEvidence,
        actor: AuditActor,
    ) -> DeliveryReconciliation: ...
