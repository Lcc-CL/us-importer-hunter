"""Values shared by the delivery workflow, queue and transport."""

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

DeliveryOutcome = Literal["accepted", "retry", "failed", "unknown"]
FeedbackKind = Literal["delivered", "hard_bounced", "unsubscribed", "complained"]


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
    ) -> None: ...

    async def summary(self, campaign_id: UUID) -> CampaignSummary: ...

    async def transition(
        self,
        campaign_id: UUID,
        action: str,
        actor: str,
        sender_hash: str | None,
    ) -> None: ...
