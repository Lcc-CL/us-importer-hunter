"""Company aggregate (Discovery context): the importer as a real-world fact.

Invariants:
- Valid, non-empty canonical name.
- Verification requires at least one source reference (provenance).
- Aliases never duplicate the canonical name.
- Carries no opportunity score and no sales state — judgments live in the
  Opportunity aggregate, conversations in the Outreach aggregate.
"""

from datetime import datetime
from uuid import UUID, uuid4

from app.domain.clock import utcnow
from app.domain.events import CompanyVerified, DomainEvent
from app.domain.exceptions import DomainError, DuplicateOperation, MissingEvidence
from app.domain.values import CompanyName, SourceReference, WebsiteUrl


class Company:
    """Aggregate root. All state changes go through the methods below."""

    def __init__(
        self,
        *,
        id: UUID,
        name: CompanyName,
        website: WebsiteUrl | None,
        created_at: datetime,
    ) -> None:
        self._id = id
        self._name = name
        self._website = website
        self._created_at = created_at
        self._aliases: list[CompanyName] = []
        self._sources: list[SourceReference] = []
        self._signals: list[str] = []
        self._verified = False
        self._events: list[DomainEvent] = []

    # -- construction -------------------------------------------------

    @classmethod
    def create(cls, name: CompanyName, website: WebsiteUrl | None = None) -> "Company":
        return cls(id=uuid4(), name=name, website=website, created_at=utcnow())

    # -- behaviors ----------------------------------------------------

    def rename(self, new_name: CompanyName) -> None:
        """Change the canonical name; the old name becomes an alias."""
        if new_name.normalized == self._name.normalized:
            raise DuplicateOperation("new name is identical to the canonical name")
        old_name = self._name
        self._name = new_name
        self._aliases = [a for a in self._aliases if a.normalized != new_name.normalized]
        if all(a.normalized != old_name.normalized for a in self._aliases):
            self._aliases.append(old_name)

    def add_alias(self, alias: CompanyName) -> None:
        if alias.normalized == self._name.normalized:
            raise DuplicateOperation("alias duplicates the canonical name")
        if any(a.normalized == alias.normalized for a in self._aliases):
            raise DuplicateOperation(f"alias already recorded: {alias.value!r}")
        self._aliases.append(alias)

    def add_source(self, reference: SourceReference) -> None:
        """Record provenance; facts without provenance don't enter the profile."""
        self._sources.append(reference)

    def set_website(self, website: WebsiteUrl) -> None:
        """Set the website when unknown; idempotent for the same URL.

        A *different* website is a conflict the aggregate refuses to
        resolve silently — resolution policy is pending (L7).
        """
        if self._website is None:
            self._website = website
            return
        if self._website == website:
            return
        raise DomainError(
            f"website conflict: {self._website.value!r} vs {website.value!r} — "
            "resolution policy pending"
        )

    def mark_verified(self) -> None:
        """Idempotent: workflow retries may re-verify — no error, no second event."""
        if self._verified:
            return
        if not self._sources:
            raise MissingEvidence("verification requires at least one source reference")
        self._verified = True
        self._events.append(CompanyVerified(company_id=self._id))

    def add_signal(self, signal: str) -> None:
        """Record a switching hint (e.g. 'volume growing', 'cadence gap')."""
        if not signal.strip():
            raise DomainError("signal must not be empty")
        self._signals.append(signal.strip())

    # -- events -------------------------------------------------------

    def drain_events(self) -> tuple[DomainEvent, ...]:
        events = tuple(self._events)
        self._events.clear()
        return events

    # -- read-only state ----------------------------------------------

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def name(self) -> CompanyName:
        return self._name

    @property
    def website(self) -> WebsiteUrl | None:
        return self._website

    @property
    def aliases(self) -> tuple[CompanyName, ...]:
        return tuple(self._aliases)

    @property
    def sources(self) -> tuple[SourceReference, ...]:
        return tuple(self._sources)

    @property
    def signals(self) -> tuple[str, ...]:
        return tuple(self._signals)

    @property
    def verified(self) -> bool:
        return self._verified

    @property
    def created_at(self) -> datetime:
        return self._created_at
