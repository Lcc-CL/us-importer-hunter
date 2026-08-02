"""Contact aggregate (Outreach context): an independent aggregate root.

A contact is a person identity used by many outreaches (by id), and its
role/channels/verification evolve independently (ADR-0022). D5b1 keeps the
original company id as a nullable compatibility reference while new import
employment is represented by CompanyContact. It holds facts about a person —
never opportunity scores, never email sending.

Invariants:
- may be unassigned; name is valid (PersonName).
- no duplicate channel per (type, normalized_value); INVALID channels
  are never usable.
- ACTIVE requires a title or at least one usable channel.
- INVALID requires a reason.
"""

import dataclasses
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.clock import utcnow
from app.domain.contact.values import (
    ContactChannel,
    ContactChannelType,
    ContactStatus,
    ContactVerificationStatus,
    Department,
    JobTitle,
    PersonName,
    SeniorityLevel,
)
from app.domain.events import (
    ContactabilityChanged,
    ContactChannelAdded,
    ContactChannelVerified,
    ContactCreated,
    ContactInvalidated,
    ContactUpdated,
    DomainEvent,
)
from app.domain.exceptions import (
    DomainError,
    DuplicateOperation,
    InvalidStateTransition,
)
from app.domain.values import SourceReference


class Contact:
    """Aggregate root. All state changes go through the methods below."""

    def __init__(
        self,
        *,
        id: UUID,
        company_id: UUID | None,
        name: PersonName,
        title: JobTitle | None,
        created_at: datetime,
    ) -> None:
        self._id = id
        self._company_id = company_id
        self._name = name
        self._title = title
        self._department = Department.UNKNOWN
        self._seniority = SeniorityLevel.UNKNOWN
        self._status = ContactStatus.DISCOVERED
        self._invalid_reason: str | None = None
        self._channels: list[ContactChannel] = []
        self._sources: list[SourceReference] = []
        self._created_at = created_at
        self._updated_at = created_at
        self._events: list[DomainEvent] = []

    # -- construction -------------------------------------------------

    @classmethod
    def create_for_company(
        cls, company_id: UUID, name: PersonName, title: JobTitle | None = None
    ) -> "Contact":
        contact = cls(
            id=uuid4(), company_id=company_id, name=name, title=title, created_at=utcnow()
        )
        contact._events.append(ContactCreated(contact_id=contact._id, company_id=company_id))
        return contact

    @classmethod
    def create_unassigned(
        cls, name: PersonName, title: JobTitle | None = None
    ) -> "Contact":
        return cls(id=uuid4(), company_id=None, name=name, title=title, created_at=utcnow())

    # -- behaviors ----------------------------------------------------

    def update_title(self, title: JobTitle) -> None:
        self._ensure_not_invalid()
        if self._title is not None and self._title.normalized == title.normalized:
            return  # idempotent
        self._title = title
        self._touch()
        self._events.append(ContactUpdated(contact_id=self._id, changed_fields=("title",)))

    def classify_role(self, department: Department, seniority: SeniorityLevel) -> None:
        self._ensure_not_invalid()
        if department is self._department and seniority is self._seniority:
            return  # idempotent
        self._department = department
        self._seniority = seniority
        self._touch()
        self._events.append(
            ContactUpdated(contact_id=self._id, changed_fields=("department", "seniority"))
        )

    def add_source(self, reference: SourceReference) -> None:
        self._sources.append(reference)
        self._touch()

    def add_channel(self, channel: ContactChannel) -> None:
        self._ensure_not_invalid()
        if self._find_channel(channel.channel_type, channel.normalized_value) is not None:
            raise DuplicateOperation(
                f"channel already recorded: {channel.channel_type.value} "
                f"{channel.normalized_value!r}"
            )
        self._channels.append(channel)
        self._touch()
        self._events.append(
            ContactChannelAdded(
                contact_id=self._id,
                channel_type=channel.channel_type.value,
                normalized_value=channel.normalized_value,
            )
        )

    def verify_channel(
        self,
        channel_type: ContactChannelType,
        normalized_value: str,
        *,
        status: ContactVerificationStatus = ContactVerificationStatus.SOURCE_VERIFIED,
    ) -> None:
        self._ensure_not_invalid()
        if status not in (
            ContactVerificationStatus.SOURCE_VERIFIED,
            ContactVerificationStatus.MANUALLY_VERIFIED,
        ):
            raise DomainError(f"cannot verify a channel into status {status.value}")
        channel = self._require_channel(channel_type, normalized_value)
        if channel.verification_status is ContactVerificationStatus.INVALID:
            raise InvalidStateTransition("cannot verify an invalidated channel")
        self._replace_channel(
            channel,
            dataclasses.replace(
                channel, verification_status=status, verified_at=utcnow(), confidence=0.9
            ),
        )
        self._events.append(
            ContactChannelVerified(
                contact_id=self._id,
                channel_type=channel_type.value,
                normalized_value=normalized_value,
                verification_status=status.value,
            )
        )
        self._record_contactability(f"{channel_type.value} channel verified")

    def invalidate_channel(
        self, channel_type: ContactChannelType, normalized_value: str, reason: str
    ) -> None:
        if not reason.strip():
            raise DomainError("channel invalidation requires a reason")
        channel = self._require_channel(channel_type, normalized_value)
        if channel.verification_status is ContactVerificationStatus.INVALID:
            return  # idempotent
        self._replace_channel(
            channel,
            dataclasses.replace(
                channel, verification_status=ContactVerificationStatus.INVALID, confidence=0.0
            ),
        )
        self._events.append(
            ContactUpdated(contact_id=self._id, changed_fields=("channels",))
        )
        self._record_contactability(
            f"{channel_type.value} channel invalidated: {reason.strip()}"
        )

    def activate(self) -> None:
        """ACTIVE requires substance: a title or at least one usable channel.

        Re-validates every call (L11 fix): an already-ACTIVE contact whose
        channels have since been invalidated fails instead of no-opping.
        """
        if self._status is ContactStatus.INVALID:
            raise InvalidStateTransition("an invalid contact cannot be activated")
        if self._title is None and not self.usable_channels:
            raise InvalidStateTransition(
                "activation requires a job title or at least one usable channel"
            )
        if self._status is ContactStatus.ACTIVE:
            return  # idempotent — but only after re-validation
        self._status = ContactStatus.ACTIVE
        self._touch()
        self._record_contactability("contact activated")

    def mark_invalid(self, reason: str) -> None:
        if not reason.strip():
            raise DomainError("marking a contact invalid requires a reason")
        if self._status is ContactStatus.INVALID:
            raise InvalidStateTransition("contact is already invalid")
        self._status = ContactStatus.INVALID
        self._invalid_reason = reason.strip()
        self._touch()
        self._events.append(ContactInvalidated(contact_id=self._id, reason=reason.strip()))
        self._record_contactability(f"contact invalidated: {reason.strip()}")

    def deactivate(self) -> None:
        if self._status is not ContactStatus.ACTIVE:
            raise InvalidStateTransition(f"cannot deactivate a {self._status.value} contact")
        self._status = ContactStatus.INACTIVE
        self._touch()
        self._record_contactability("contact deactivated")

    def reactivate(self) -> None:
        if self._status is not ContactStatus.INACTIVE:
            raise InvalidStateTransition(f"cannot reactivate a {self._status.value} contact")
        self._status = ContactStatus.DISCOVERED
        self.activate()

    # -- events -------------------------------------------------------

    @property
    def pending_events(self) -> tuple[DomainEvent, ...]:
        return tuple(self._events)

    def drain_events(self) -> tuple[DomainEvent, ...]:
        events = tuple(self._events)
        self._events.clear()
        return events

    # -- internals ----------------------------------------------------

    def _ensure_not_invalid(self) -> None:
        if self._status is ContactStatus.INVALID:
            raise InvalidStateTransition("contact is invalid — no further changes allowed")

    def _find_channel(
        self, channel_type: ContactChannelType, normalized_value: str
    ) -> ContactChannel | None:
        for channel in self._channels:
            if (
                channel.channel_type is channel_type
                and channel.normalized_value == normalized_value
            ):
                return channel
        return None

    def _require_channel(
        self, channel_type: ContactChannelType, normalized_value: str
    ) -> ContactChannel:
        channel = self._find_channel(channel_type, normalized_value)
        if channel is None:
            raise DomainError(f"no {channel_type.value} channel {normalized_value!r}")
        return channel

    def _replace_channel(self, old: ContactChannel, new: ContactChannel) -> None:
        self._channels[self._channels.index(old)] = new
        self._touch()

    def _touch(self) -> None:
        self._updated_at = utcnow()

    def _record_contactability(self, reason: str) -> None:
        if self._company_id is not None:
            self._events.append(
                ContactabilityChanged(
                    company_id=self._company_id,
                    contact_id=self._id,
                    reason=reason,
                )
            )

    # -- read-only state ----------------------------------------------

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def company_id(self) -> UUID | None:
        return self._company_id

    @property
    def name(self) -> PersonName:
        return self._name

    @property
    def title(self) -> JobTitle | None:
        return self._title

    @property
    def department(self) -> Department:
        return self._department

    @property
    def seniority(self) -> SeniorityLevel:
        return self._seniority

    @property
    def status(self) -> ContactStatus:
        return self._status

    @property
    def invalid_reason(self) -> str | None:
        return self._invalid_reason

    @property
    def channels(self) -> tuple[ContactChannel, ...]:
        return tuple(self._channels)

    @property
    def usable_channels(self) -> tuple[ContactChannel, ...]:
        return tuple(c for c in self._channels if c.usable)

    @property
    def sources(self) -> tuple[SourceReference, ...]:
        return tuple(self._sources)

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at
