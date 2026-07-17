"""Contact ingestion workflow: candidate claim → canonical Contact.

    ContactCandidateDiscovered
      → ContactNormalizer (name/title/channels; bad channel dropped with note)
      → RepositoryContactDeduplicator (email → linkedin → name+title)
      → CREATED | MERGED | POSSIBLE_MATCH (no write) | REJECTED
      → one UnitOfWork per event; peek → commit → drain (L9 rule)

No real contact providers are called; Discovery-side code never creates
contacts directly (ADR-0022).
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.domain.contact import Contact, ContactMatchKind, Department, SeniorityLevel
from app.domain.events import ContactCandidateDiscovered, DomainEvent
from app.domain.exceptions import DomainError, DuplicateOperation, InvalidStateTransition
from app.domain.repositories import UnitOfWork
from app.services.contact import (
    ContactNormalizer,
    NormalizedContactCandidate,
    RepositoryContactDeduplicator,
)


class ContactIngestionAction(StrEnum):
    CREATED = "created"
    MERGED = "merged"
    POSSIBLE_MATCH = "possible_match"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ContactIngestionOutcome:
    action: ContactIngestionAction
    company_id: UUID
    contact_id: UUID | None = None
    notes: tuple[str, ...] = ()
    emitted_events_count: int = 0


class ContactIngestionWorkflow:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        normalizer: ContactNormalizer | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._normalizer = normalizer or ContactNormalizer()

    async def handle(self, event: ContactCandidateDiscovered) -> ContactIngestionOutcome:
        snapshot = event.candidate
        try:
            candidate = self._normalizer.normalize(snapshot)
        except DomainError as exc:
            return ContactIngestionOutcome(
                action=ContactIngestionAction.REJECTED,
                company_id=snapshot.company_id,
                notes=(f"unusable contact candidate: {exc}",),
            )

        notes = list(candidate.dropped_notes)
        async with self._uow_factory() as uow:
            deduplicator = RepositoryContactDeduplicator(uow.contacts)
            match = await deduplicator.classify(
                snapshot.company_id,
                candidate.name,
                candidate.title,
                candidate.email.normalized_value if candidate.email else None,
                candidate.linkedin.normalized_value if candidate.linkedin else None,
            )

            if match.kind is ContactMatchKind.POSSIBLE_MATCH:
                return ContactIngestionOutcome(
                    action=ContactIngestionAction.POSSIBLE_MATCH,
                    company_id=snapshot.company_id,
                    contact_id=match.matched_contact_id,
                    notes=(*notes, match.reason),
                )

            if match.kind is ContactMatchKind.NEW:
                contact = Contact.create_for_company(
                    snapshot.company_id, candidate.name, candidate.title
                )
                self._apply_candidate(contact, candidate, event, notes)
                action = ContactIngestionAction.CREATED
            else:
                assert match.matched_contact_id is not None
                existing = await uow.contacts.get_by_id(match.matched_contact_id)
                assert existing is not None, "deduplicator returned a vanished contact id"
                contact = existing
                self._merge_candidate(contact, candidate, event, notes)
                action = ContactIngestionAction.MERGED
                notes.append(match.reason)

            try:
                contact.activate()
            except InvalidStateTransition as exc:
                notes.append(f"contact remains discovered: {exc}")

            if action is ContactIngestionAction.CREATED:
                await uow.contacts.add(contact)
            else:
                await uow.contacts.save(contact)

            pending = len(contact.pending_events)
            await uow.commit()
            events: tuple[DomainEvent, ...] = contact.drain_events()
            assert len(events) == pending
            return ContactIngestionOutcome(
                action=action,
                company_id=snapshot.company_id,
                contact_id=contact.id,
                notes=tuple(notes),
                emitted_events_count=len(events),
            )

    # -- merge policy ---------------------------------------------------

    def _apply_candidate(
        self,
        contact: Contact,
        candidate: NormalizedContactCandidate,
        event: ContactCandidateDiscovered,
        notes: list[str],
    ) -> None:
        if (
            candidate.department is not Department.UNKNOWN
            or candidate.seniority is not SeniorityLevel.UNKNOWN
        ):
            contact.classify_role(candidate.department, candidate.seniority)
        self._record_source(contact, event, notes)
        for channel in candidate.channels:
            try:
                contact.add_channel(channel)
            except DuplicateOperation:
                notes.append(f"channel already recorded: {channel.normalized_value!r}")

    def _merge_candidate(
        self,
        contact: Contact,
        candidate: NormalizedContactCandidate,
        event: ContactCandidateDiscovered,
        notes: list[str],
    ) -> None:
        if candidate.title is not None and contact.title is None:
            contact.update_title(candidate.title)
        if (
            contact.department is Department.UNKNOWN
            and candidate.department is not Department.UNKNOWN
        ):
            contact.classify_role(candidate.department, candidate.seniority)
        self._record_source(contact, event, notes)
        for channel in candidate.channels:
            try:
                contact.add_channel(channel)
            except DuplicateOperation:
                notes.append(f"channel already recorded: {channel.normalized_value!r}")

    @staticmethod
    def _record_source(
        contact: Contact, event: ContactCandidateDiscovered, notes: list[str]
    ) -> None:
        source = event.candidate.source_reference
        already = any(
            ref.source == source.source and ref.reference == source.reference
            for ref in contact.sources
        )
        if already:
            notes.append("source already recorded — skipped")
        else:
            contact.add_source(source)
