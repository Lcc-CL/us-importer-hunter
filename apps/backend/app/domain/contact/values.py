"""Contact value objects (L10): people, roles, channels, fit assessments.

Facts about a person are separate from decision-maker judgment
(DecisionMakerFitAssessment) — the same separation Company/Opportunity
uses (ADR-0022).
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.domain.clock import ensure_utc, utcnow
from app.domain.exceptions import DomainError, MissingEvidence
from app.domain.values import Confidence, Evidence, SourceReference

_HAS_WORD_RE = re.compile(r"[A-Za-z0-9À-ɏ一-鿿]")


@dataclass(frozen=True)
class PersonName:
    """A person's name: non-empty, whitespace-collapsed, not symbols-only."""

    value: str

    def __post_init__(self) -> None:
        cleaned = " ".join(self.value.split())
        if not cleaned:
            raise DomainError("person name must not be empty")
        if not _HAS_WORD_RE.search(cleaned):
            raise DomainError(f"person name must contain letters, got {self.value!r}")
        if len(cleaned) > 200:
            raise DomainError("person name exceeds 200 characters")
        object.__setattr__(self, "value", cleaned)

    @property
    def normalized(self) -> str:
        return self.value.lower()


@dataclass(frozen=True)
class JobTitle:
    """Raw job title + normalized form. No role weights here — weights
    are policy (mvp-decision-maker-policy-v1), never value-object truth."""

    raw: str

    def __post_init__(self) -> None:
        cleaned = " ".join(self.raw.split())
        if not cleaned:
            raise DomainError("job title must not be empty")
        object.__setattr__(self, "raw", cleaned)

    @property
    def normalized(self) -> str:
        return self.raw.lower()


class Department(StrEnum):
    PROCUREMENT = "procurement"
    SUPPLY_CHAIN = "supply_chain"
    LOGISTICS = "logistics"
    OPERATIONS = "operations"
    EXECUTIVE = "executive"
    FINANCE = "finance"
    SALES_MARKETING = "sales_marketing"
    HR = "hr"
    OTHER = "other"
    UNKNOWN = "unknown"


class SeniorityLevel(StrEnum):
    C_LEVEL = "c_level"
    VP = "vp"
    DIRECTOR = "director"
    HEAD = "head"
    MANAGER = "manager"
    SPECIALIST = "specialist"
    UNKNOWN = "unknown"


class ContactChannelType(StrEnum):
    EMAIL = "email"
    LINKEDIN = "linkedin"
    PHONE = "phone"


class ContactVerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    SOURCE_VERIFIED = "source_verified"
    MANUALLY_VERIFIED = "manually_verified"
    INVALID = "invalid"


class ContactStatus(StrEnum):
    DISCOVERED = "discovered"
    ACTIVE = "active"
    INVALID = "invalid"
    INACTIVE = "inactive"


@dataclass(frozen=True, kw_only=True)
class ContactChannel:
    """One way to reach a person, with provenance and verification state."""

    channel_type: ContactChannelType
    normalized_value: str
    display_value: str
    source_reference: SourceReference
    verification_status: ContactVerificationStatus = ContactVerificationStatus.UNVERIFIED
    verified_at: datetime | None = None
    confidence: float = 0.5

    def __post_init__(self) -> None:
        if not self.normalized_value.strip():
            raise DomainError("channel requires a normalized value")
        if not 0.0 <= self.confidence <= 1.0:
            raise DomainError("channel confidence must be within 0–1")
        if self.verified_at is not None:
            object.__setattr__(
                self, "verified_at", ensure_utc(self.verified_at, field="verified_at")
            )
        verified_statuses = (
            ContactVerificationStatus.SOURCE_VERIFIED,
            ContactVerificationStatus.MANUALLY_VERIFIED,
        )
        if self.verification_status in verified_statuses and self.verified_at is None:
            raise DomainError("verified channels require verified_at")

    @property
    def usable(self) -> bool:
        return self.verification_status is not ContactVerificationStatus.INVALID


@dataclass(frozen=True, kw_only=True)
class RawContactSnapshot:
    """A source's claim about a person — not yet a trusted Contact."""

    company_id: UUID
    raw_name: str
    source_reference: SourceReference
    raw_title: str | None = None
    raw_email: str | None = None
    raw_linkedin_url: str | None = None
    raw_phone: str | None = None
    external_source_id: str | None = None
    observed_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.raw_name.strip():
            raise DomainError("contact candidate requires a raw name")
        object.__setattr__(self, "observed_at", ensure_utc(self.observed_at, field="observed_at"))


class ContactMatchKind(StrEnum):
    NEW = "new"
    MATCHED = "matched"
    POSSIBLE_MATCH = "possible_match"


@dataclass(frozen=True)
class ContactMatch:
    """Deduplication verdict: is this candidate a person we already know?"""

    kind: ContactMatchKind
    matched_contact_id: UUID | None
    reason: str

    def __post_init__(self) -> None:
        if self.kind is not ContactMatchKind.NEW and self.matched_contact_id is None:
            raise DomainError(f"{self.kind.value} requires a matched contact id")
        if not self.reason.strip():
            raise DomainError("contact match requires a reason")


@dataclass(frozen=True, kw_only=True)
class DecisionMakerFitAssessment:
    """Immutable judgment: how well does this person fit as the logistics
    decision maker, and how reachable are they? Facts stay on Contact."""

    contact_id: UUID
    company_id: UUID
    role_fit_score: float
    reachability_score: float
    total_score: float
    confidence: Confidence
    department: Department
    seniority: SeniorityLevel
    reasons: tuple[str, ...]
    policy_version: str
    evidence: tuple[Evidence, ...] = ()
    recommended_channel: ContactChannelType | None = None
    assessment_fingerprint: str = ""  # auto-computed (SHA-256) when omitted
    assessed_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        for label, score in (
            ("role_fit_score", self.role_fit_score),
            ("reachability_score", self.reachability_score),
            ("total_score", self.total_score),
        ):
            if not 0.0 <= score <= 100.0:
                raise DomainError(f"{label} must be within 0–100, got {score}")
        if not self.policy_version.strip():
            raise DomainError("fit assessment requires a policy_version")
        if not self.reasons or not all(reason.strip() for reason in self.reasons):
            raise MissingEvidence("fit assessment requires at least one non-empty reason")
        object.__setattr__(self, "assessed_at", ensure_utc(self.assessed_at, field="assessed_at"))
        if not self.assessment_fingerprint:
            object.__setattr__(self, "assessment_fingerprint", self._compute_fingerprint())

    def _compute_fingerprint(self) -> str:
        canonical = json.dumps(
            {
                "contact_id": str(self.contact_id),
                "policy_version": self.policy_version,
                "role_fit": self.role_fit_score,
                "reachability": self.reachability_score,
                "total": self.total_score,
                "confidence": self.confidence.value,
                "department": self.department.value,
                "seniority": self.seniority.value,
                "recommended_channel": (
                    self.recommended_channel.value if self.recommended_channel else None
                ),
                "reasons": list(self.reasons),
                "evidence_claims": [e.claim for e in self.evidence],
            },
            sort_keys=True,
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
