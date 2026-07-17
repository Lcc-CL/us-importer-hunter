"""Outreach aggregate (Outreach context): one pursuit conversation.

An EmailDraft is one artifact inside the conversation, not the sales
process itself (ADR-0015). Invariants:
- Nothing is approved without a draft; nothing is sent without approval.
- Sent draft content is immutable (drafts are frozen values; new content
  means a new version).
- A reply stops automatic follow-up.
- Won/lost are terminal — no behavior is allowed afterwards.
"""

import dataclasses
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.clock import ensure_utc, utcnow
from app.domain.events import (
    DomainEvent,
    EmailDraftGenerated,
    OpportunityLost,
    OpportunityWon,
    OutreachApproved,
    OutreachReplied,
    OutreachSent,
)
from app.domain.exceptions import (
    DomainError,
    DuplicateOperation,
    InvalidStateTransition,
)


class OutreachStatus(StrEnum):
    CREATED = "created"
    APPROVED = "approved"
    SENT = "sent"
    REPLIED = "replied"
    WON = "won"
    LOST = "lost"


TERMINAL_STATUSES = frozenset({OutreachStatus.WON, OutreachStatus.LOST})


class OutcomeKind(StrEnum):
    REPLY = "reply"
    WON = "won"
    LOST = "lost"


@dataclass(frozen=True)
class Outcome:
    """One immutable feedback event from reality — append-only history
    on the outreach (L4 review follow-up)."""

    kind: OutcomeKind
    detail: str
    draft_version: int | None
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not self.detail.strip():
            raise DomainError("outcome requires a detail")


class EmailDraftStatus(StrEnum):
    GENERATED = "generated"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, kw_only=True)
class EmailDraft:
    """One immutable draft version. New content = new version; approved
    drafts are never modified (regeneration appends, L11)."""

    version: int
    subject: str
    body: str
    prompt_version: str
    generated_at: datetime
    approval_status: EmailDraftStatus = EmailDraftStatus.GENERATED
    approved_at: datetime | None = None
    approved_by_name: str | None = None
    provider: str = "unknown"
    model: str = "unknown"
    context_fingerprint: str = ""  # empty = pre-L11 draft, exempt from dedup

    def __post_init__(self) -> None:
        if not self.subject.strip() or not self.body.strip():
            raise DomainError("draft requires a subject and a body")
        if self.approved_at is not None:
            object.__setattr__(
                self,
                "approved_at",
                ensure_utc(self.approved_at, field="approved_at"),
            )
        if self.approved_by_name is not None:
            cleaned = self.approved_by_name.strip()
            if not cleaned:
                raise DomainError("approved_by_name must not be blank")
            if len(cleaned) > 200:
                raise DomainError("approved_by_name exceeds 200 characters")
            object.__setattr__(self, "approved_by_name", cleaned)

    @property
    def status(self) -> EmailDraftStatus:
        """Backward-compatible alias for clients created before approval metadata."""
        return self.approval_status


class Outreach:
    """Aggregate root for the conversation with one opportunity's contact."""

    def __init__(self, *, id: UUID, opportunity_id: UUID, created_at: datetime) -> None:
        self._id = id
        self._opportunity_id = opportunity_id
        self._created_at = created_at
        self._contact_id: UUID | None = None
        self._drafts: list[EmailDraft] = []
        self._approved_version: int | None = None
        self._sent_version: int | None = None
        self._status = OutreachStatus.CREATED
        self._follow_up_active = True
        self._closed_reason: str | None = None
        self._outcomes: list[Outcome] = []
        self._events: list[DomainEvent] = []

    # -- construction -------------------------------------------------

    @classmethod
    def create(cls, opportunity_id: UUID) -> "Outreach":
        return cls(id=uuid4(), opportunity_id=opportunity_id, created_at=utcnow())

    # -- guards -------------------------------------------------------

    def _ensure_not_terminal(self) -> None:
        if self._status in TERMINAL_STATUSES:
            raise InvalidStateTransition(
                f"outreach is {self._status.value} (terminal) — no further changes allowed"
            )

    # -- behaviors ----------------------------------------------------

    def attach_contact(self, contact_id: UUID) -> None:
        self._ensure_not_terminal()
        if self._approved_version is not None:
            raise InvalidStateTransition("cannot change the contact after approval")
        self._contact_id = contact_id

    def add_draft(
        self,
        subject: str,
        body: str,
        prompt_version: str,
        *,
        provider: str = "unknown",
        model: str = "unknown",
        context_fingerprint: str = "",
    ) -> EmailDraft:
        self._ensure_not_terminal()
        if context_fingerprint and any(
            d.context_fingerprint == context_fingerprint and d.prompt_version == prompt_version
            for d in self._drafts
        ):
            raise DuplicateOperation(
                "a draft for this context and prompt version already exists — "
                "regeneration requires new facts or a new prompt"
            )
        draft = EmailDraft(
            version=len(self._drafts) + 1,
            subject=subject,
            body=body,
            prompt_version=prompt_version,
            provider=provider,
            model=model,
            context_fingerprint=context_fingerprint,
            generated_at=utcnow(),
        )
        self._drafts.append(draft)
        self._events.append(
            EmailDraftGenerated(
                outreach_id=self._id,
                draft_version=draft.version,
                prompt_version=prompt_version,
                provider=provider,
                model=model,
            )
        )
        return draft

    def approve_draft(self, version: int, *, approved_by_name: str) -> None:
        self._ensure_not_terminal()
        approved_by_name = approved_by_name.strip()
        if not approved_by_name:
            raise DomainError("draft approval requires an approver name")
        if not self._drafts:
            raise InvalidStateTransition("cannot approve without a draft")
        if not any(d.version == version for d in self._drafts):
            raise DomainError(f"no draft with version {version}")
        if version == self._sent_version:
            raise DuplicateOperation(f"draft v{version} was already sent")
        index = next(i for i, d in enumerate(self._drafts) if d.version == version)
        if self._drafts[index].approval_status is EmailDraftStatus.APPROVED:
            return
        self._approved_version = version
        approved_at = utcnow()
        self._drafts[index] = dataclasses.replace(
            self._drafts[index],
            approval_status=EmailDraftStatus.APPROVED,
            approved_at=approved_at,
            approved_by_name=approved_by_name,
        )
        if self._status is OutreachStatus.CREATED:
            self._status = OutreachStatus.APPROVED
        self._events.append(
            OutreachApproved(
                outreach_id=self._id,
                draft_version=version,
                approved_by_name=approved_by_name,
                occurred_at=approved_at,
            )
        )

    def mark_sent(self) -> None:
        self._ensure_not_terminal()
        if self._approved_version is None:
            raise InvalidStateTransition("cannot send an unapproved draft")
        if self._approved_version == self._sent_version:
            raise DuplicateOperation(f"draft v{self._approved_version} was already sent")
        self._sent_version = self._approved_version
        self._status = OutreachStatus.SENT
        self._events.append(
            OutreachSent(outreach_id=self._id, draft_version=self._sent_version)
        )

    def record_reply(self, sentiment: str) -> None:
        self._ensure_not_terminal()
        if self._sent_version is None:
            raise InvalidStateTransition("cannot record a reply before anything was sent")
        if not sentiment.strip():
            raise DomainError("reply requires a sentiment")
        self._status = OutreachStatus.REPLIED
        self._follow_up_active = False  # a human is talking now — stop automation
        self._outcomes.append(
            Outcome(
                kind=OutcomeKind.REPLY,
                detail=sentiment.strip(),
                draft_version=self._sent_version,
                occurred_at=utcnow(),
            )
        )
        self._events.append(OutreachReplied(outreach_id=self._id, sentiment=sentiment.strip()))

    def mark_won(self, reason: str) -> None:
        self._close(OutreachStatus.WON, reason)
        self._events.append(
            OpportunityWon(opportunity_id=self._opportunity_id, outreach_id=self._id, reason=reason)
        )

    def mark_lost(self, reason: str) -> None:
        self._close(OutreachStatus.LOST, reason)
        self._events.append(
            OpportunityLost(
                opportunity_id=self._opportunity_id, outreach_id=self._id, reason=reason
            )
        )

    def _close(self, status: OutreachStatus, reason: str) -> None:
        self._ensure_not_terminal()
        if not reason.strip():
            raise DomainError(f"marking {status.value} requires a reason")
        if self._sent_version is None:
            raise InvalidStateTransition("cannot close an outreach that never sent anything")
        self._status = status
        self._closed_reason = reason.strip()
        self._follow_up_active = False
        self._outcomes.append(
            Outcome(
                kind=OutcomeKind.WON if status is OutreachStatus.WON else OutcomeKind.LOST,
                detail=reason.strip(),
                draft_version=self._sent_version,
                occurred_at=utcnow(),
            )
        )

    # -- events -------------------------------------------------------

    @property
    def pending_events(self) -> tuple[DomainEvent, ...]:
        """Peek without clearing — publish only after a successful commit."""
        return tuple(self._events)

    def drain_events(self) -> tuple[DomainEvent, ...]:
        events = tuple(self._events)
        self._events.clear()
        return events

    # -- read-only state ----------------------------------------------

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def opportunity_id(self) -> UUID:
        return self._opportunity_id

    @property
    def contact_id(self) -> UUID | None:
        return self._contact_id

    @property
    def drafts(self) -> tuple[EmailDraft, ...]:
        return tuple(self._drafts)

    @property
    def approved_version(self) -> int | None:
        return self._approved_version

    @property
    def sent_version(self) -> int | None:
        return self._sent_version

    @property
    def status(self) -> OutreachStatus:
        return self._status

    @property
    def follow_up_active(self) -> bool:
        return self._follow_up_active

    @property
    def outcomes(self) -> tuple[Outcome, ...]:
        """Append-only: exposed as an immutable snapshot."""
        return tuple(self._outcomes)

    @property
    def closed_reason(self) -> str | None:
        return self._closed_reason

    @property
    def created_at(self) -> datetime:
        return self._created_at
