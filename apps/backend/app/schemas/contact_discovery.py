"""API shapes for website contact discovery (read-only, no persistence)."""

from typing import Literal

from pydantic import BaseModel

from app.services.contact_discovery import (
    ContactSelection,
    DiscoveredContact,
    DiscoverySourceType,
    RankedContact,
    department_display_name,
)


class DiscoveredContactResponse(BaseModel):
    name: str
    title: str
    email: str
    phone: str
    source_url: str
    source_type: Literal["named", "department", "generic"]
    #: How a draft may address this contact. A person's real name, or the
    #: department salutation ("Purchasing Team") — never an invented person.
    display_name: str
    evidence_snippet: str
    confidence: float

    @classmethod
    def from_contact(cls, contact: DiscoveredContact) -> "DiscoveredContactResponse":
        if contact.name:
            display = contact.name
        elif contact.email and contact.source_type is DiscoverySourceType.DEPARTMENT:
            display = department_display_name(contact.email)
        elif contact.email:
            display = "Team"
        else:
            display = ""
        return cls(
            name=contact.name,
            title=contact.title,
            email=contact.email,
            phone=contact.phone,
            source_url=contact.source_url,
            source_type=contact.source_type.value,
            display_name=display,
            evidence_snippet=contact.evidence_snippet,
            confidence=contact.confidence,
        )


class RankedContactResponse(BaseModel):
    contact: DiscoveredContactResponse
    score: float
    reasons: list[str]

    @classmethod
    def from_ranked(cls, ranked: RankedContact) -> "RankedContactResponse":
        return cls(
            contact=DiscoveredContactResponse.from_contact(ranked.contact),
            score=ranked.score,
            reasons=list(ranked.reasons),
        )


class ContactDiscoveryResponse(BaseModel):
    """FULL_CONTACT: a named person leads. DEPARTMENT_CONTACT: only functional
    mailboxes. COMPANY_ONLY: nothing usable — analysis may still proceed."""

    discovery_status: Literal["FULL_CONTACT", "DEPARTMENT_CONTACT", "COMPANY_ONLY"]
    pages_scanned: int
    pages_failed: int
    primary: RankedContactResponse | None
    alternatives: list[RankedContactResponse]
    supporting: list[RankedContactResponse]
    rejected: list[RankedContactResponse]
    review_required: bool
    selection_reasons: list[str]

    @classmethod
    def from_selection(
        cls, selection: ContactSelection, *, pages_scanned: int, pages_failed: int
    ) -> "ContactDiscoveryResponse":
        if selection.primary is None:
            status: Literal["FULL_CONTACT", "DEPARTMENT_CONTACT", "COMPANY_ONLY"] = (
                "COMPANY_ONLY"
            )
        elif selection.primary.contact.source_type.value == "named":
            status = "FULL_CONTACT"
        else:
            status = "DEPARTMENT_CONTACT"
        return cls(
            discovery_status=status,
            pages_scanned=pages_scanned,
            pages_failed=pages_failed,
            primary=(
                RankedContactResponse.from_ranked(selection.primary)
                if selection.primary
                else None
            ),
            alternatives=[
                RankedContactResponse.from_ranked(item) for item in selection.alternatives
            ],
            supporting=[
                RankedContactResponse.from_ranked(item) for item in selection.supporting
            ],
            rejected=[RankedContactResponse.from_ranked(item) for item in selection.rejected],
            review_required=selection.review_required,
            selection_reasons=list(selection.selection_reasons),
        )
