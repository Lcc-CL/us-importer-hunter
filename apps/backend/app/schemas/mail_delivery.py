"""Campaign creation and delivery control requests."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.mail_delivery import FeedbackKind, ReconciliationDecision
from app.workflows.mail_delivery.workflow import MailAction

TEXT_INPUT = ConfigDict(str_strip_whitespace=True, extra="forbid")


class MailTemplateCampaign(BaseModel):
    model_config = TEXT_INPUT

    id: UUID
    name: str = Field(min_length=1, max_length=160)
    export_id: UUID
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)


class MailDraftCampaign(BaseModel):
    model_config = TEXT_INPUT

    id: UUID
    name: str = Field(min_length=1, max_length=160)
    outreach_id: UUID
    draft_version: int = Field(ge=1, le=2147483647)
    recipient: str = Field(min_length=1, max_length=320)
    subject: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=20000)


class MailCampaignAction(BaseModel):
    model_config = TEXT_INPUT

    action: MailAction
    actor: str | None = Field(default=None, min_length=1, max_length=160)


class MailFeedbackInput(BaseModel):
    model_config = TEXT_INPUT

    event_id: str = Field(min_length=1, max_length=140)
    delivery_id: UUID
    kind: FeedbackKind


class MailReconciliationInput(BaseModel):
    model_config = TEXT_INPUT

    attempt: int = Field(ge=1, le=2147483647)
    decision: ReconciliationDecision
    provider_reference: str = Field(min_length=1, max_length=256)
    note: str = Field(min_length=1, max_length=1000)
