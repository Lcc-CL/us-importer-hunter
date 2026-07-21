"""Six-factor deterministic decision-maker scoring — mvp-decision-maker-policy-v2.

Each contact is scored on six independent dimensions. The total is their sum
(capped at 100), and the breakdown is stored so a reviewer can see why one
person ranked above another without reverse-engineering a formula.

This service replaces the legacy single-department / seniority-bonus scoring
in decision_maker.py, which is kept as a reference for the old policy.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.domain.contact import (
    Contact,
    ContactChannelType,
    ContactVerificationStatus,
    SeniorityLevel,
)
from app.domain.contact.roles import (
    DecisionRole,
)
from app.services.contact.role_matcher import RoleClassification, classify_title

POLICY_VERSION_V2 = "mvp-decision-maker-policy-v2"


class SelectionStatus(StrEnum):
    SELECTED = "selected"
    ALTERNATIVES_AVAILABLE = "alternatives_available"
    REVIEW_REQUIRED = "review_required"
    NO_RELEVANT_CONTACT = "no_relevant_contact"
    NO_REACHABLE_CONTACT = "no_reachable_contact"


class RejectionReason(StrEnum):
    HISTORICAL_ROLE = "historical_role"
    IRRELEVANT_ROLE = "irrelevant_role"
    SALES_ONLY = "sales_only"
    INVALID_CONTACT = "invalid_contact"
    DUPLICATE_CONTACT = "duplicate_contact"
    INSUFFICIENT_ROLE_FIT = "insufficient_role_fit"
    NO_SOURCE = "no_source"
    BELOW_SELECTION_THRESHOLD = "below_selection_threshold"


_ROLE_RELEVANCE_BASE: dict[DecisionRole, float] = {
    DecisionRole.PROCUREMENT: 38,
    DecisionRole.SOURCING: 36,
    DecisionRole.SUPPLY_CHAIN: 40,
    DecisionRole.IMPORT: 40,
    DecisionRole.LOGISTICS: 38,
    DecisionRole.VENDOR_MANAGEMENT: 28,
    DecisionRole.MERCHANDISING: 26,
    DecisionRole.INVENTORY: 24,
    DecisionRole.OPERATIONS: 20,
    DecisionRole.OWNERSHIP: 22,
    DecisionRole.COMPLIANCE: 18,
    DecisionRole.SALES: 6,
    DecisionRole.FINANCE: 10,
    DecisionRole.CUSTOMER_SERVICE: 4,
    DecisionRole.MARKETING: 2,
    DecisionRole.ENGINEERING: 2,
    DecisionRole.HUMAN_RESOURCES: 2,
    DecisionRole.UNKNOWN: 2,
}

_SENIORITY_SCORE: dict[SeniorityLevel, float] = {
    SeniorityLevel.C_LEVEL: 15,
    SeniorityLevel.VP: 14,
    SeniorityLevel.DIRECTOR: 12,
    SeniorityLevel.HEAD: 11,
    SeniorityLevel.MANAGER: 9,
    SeniorityLevel.SPECIALIST: 6,
    SeniorityLevel.UNKNOWN: 5,
}

_IMPORT_LOGISTICS_BASE: dict[DecisionRole, float] = {
    DecisionRole.IMPORT: 15,
    DecisionRole.LOGISTICS: 15,
    DecisionRole.SUPPLY_CHAIN: 14,
    DecisionRole.PROCUREMENT: 11,
    DecisionRole.SOURCING: 10,
    DecisionRole.OPERATIONS: 7,
    DecisionRole.VENDOR_MANAGEMENT: 7,
    DecisionRole.MERCHANDISING: 6,
    DecisionRole.INVENTORY: 8,
    DecisionRole.OWNERSHIP: 5,
    DecisionRole.COMPLIANCE: 6,
}

_REACHABILITY_VERIFIED_EMAIL = 15
_REACHABILITY_UNVERIFIED_EMAIL = 11
_REACHABILITY_LINKEDIN = 8
_REACHABILITY_PHONE = 6
_REACHABILITY_GENERIC = 2

_SOURCE_CONFIDENCE_TRUSTED = 5
_SOURCE_CONFIDENCE_WEBSITE = 4
_SOURCE_CONFIDENCE_MANUAL = 4
_SOURCE_CONFIDENCE_PUBLIC = 3
_SOURCE_CONFIDENCE_USER = 2
_SOURCE_CONFIDENCE_UNKNOWN = 1


@dataclass(frozen=True)
class CandidateScore:
    """One contact scored across six independent dimensions."""

    contact_id: UUID
    original_title: str | None
    normalized_title: str | None
    roles: tuple[DecisionRole, ...]
    role_classification_confidence: float
    historical_role: bool
    assistant_role: bool
    seniority: SeniorityLevel

    role_relevance_score: float
    seniority_score: float
    company_size_fit_score: float
    import_logistics_fit_score: float
    reachability_score: float
    source_confidence_score: float
    overall_score: float

    eligible: bool
    recommended_channel: ContactChannelType | None = None
    selection_status: SelectionStatus | None = None
    selection_reasons: tuple[str, ...] = ()
    rejection_reasons: tuple[RejectionReason, ...] = ()

    @property
    def score_breakdown(self) -> dict[str, float]:
        return {
            "role_relevance": self.role_relevance_score,
            "seniority": self.seniority_score,
            "company_size_fit": self.company_size_fit_score,
            "import_logistics_fit": self.import_logistics_fit_score,
            "reachability": self.reachability_score,
            "source_confidence": self.source_confidence_score,
        }


@dataclass(frozen=True)
class DecisionMakerSelectionResult:
    """The full picture: who to contact, who else is worth knowing, and why."""

    status: SelectionStatus
    review_required: bool
    review_reasons: tuple[str, ...]
    primary_contact: CandidateScore | None
    alternative_contacts: tuple[CandidateScore, ...]
    supporting_contacts: tuple[CandidateScore, ...]
    rejected_contacts: tuple[CandidateScore, ...]
    scoring_version: str = POLICY_VERSION_V2


class ContactSizeProvider(Protocol):
    """Provide a company-size hint so scoring can adjust for scale."""

    def company_size_hint(self, company_id: UUID) -> str:
        """One of 'small', 'medium', 'large', 'unknown'."""
        ...


class SixFactorScorer:
    """Deterministic six-factor scoring. No LLM, no external API calls."""

    def __init__(self, size_provider: ContactSizeProvider | None = None) -> None:
        self._size = size_provider

    def score(self, contact: Contact) -> CandidateScore:
        classification = classify_title(contact.title.raw if contact.title else None)
        roles = classification.roles
        if classification.historical_role:
            seniority = SeniorityLevel.UNKNOWN
        else:
            seniority = _derive_seniority(contact, classification)

        rr = _role_relevance(roles)
        sn = _seniority_score_value(classification, seniority)
        cs = _company_size_fit(contact, roles, seniority, self._size)
        il = _import_logistics_fit(roles)
        reach, rec_channel = _reachability(contact)
        sc = _source_confidence_score(contact)

        overall = round(min(rr + sn + cs + il + reach + sc, 100.0), 1)

        eligible = True
        rejection: list[RejectionReason] = []
        if classification.historical_role:
            eligible = False
            rejection.append(RejectionReason.HISTORICAL_ROLE)
        if _is_sales_only(roles):
            eligible = False
            rejection.append(RejectionReason.SALES_ONLY)
        if not contact.sources:
            eligible = False
            rejection.append(RejectionReason.NO_SOURCE)
        if _is_irrelevant(roles):
            eligible = False
            rejection.append(RejectionReason.IRRELEVANT_ROLE)
        if overall < 25:
            eligible = False
            rejection.append(RejectionReason.BELOW_SELECTION_THRESHOLD)

        return CandidateScore(
            contact_id=contact.id,
            original_title=contact.title.raw if contact.title else None,
            normalized_title=classification.normalized_title or None,
            roles=roles,
            role_classification_confidence=classification.confidence,
            historical_role=classification.historical_role,
            assistant_role=classification.assistant_role,
            seniority=seniority,
            role_relevance_score=rr,
            seniority_score=sn,
            company_size_fit_score=cs,
            import_logistics_fit_score=il,
            reachability_score=reach,
            source_confidence_score=sc,
            overall_score=overall,
            eligible=eligible,
            recommended_channel=rec_channel,
            rejection_reasons=tuple(rejection),
        )


def _role_relevance(roles: tuple[DecisionRole, ...]) -> float:
    if not roles or roles == (DecisionRole.UNKNOWN,):
        return 0.0
    best = max(_ROLE_RELEVANCE_BASE.get(r, 2.0) for r in roles)
    freight_roles = {
        DecisionRole.PROCUREMENT,
        DecisionRole.SOURCING,
        DecisionRole.SUPPLY_CHAIN,
        DecisionRole.IMPORT,
        DecisionRole.LOGISTICS,
    }
    freight_count = sum(1 for r in roles if r in freight_roles)
    bonus = min((freight_count - 1) * 2, 6) if freight_count >= 2 else 0
    return min(best + bonus, 40.0)


def _seniority_score_value(
    classification: RoleClassification, seniority: SeniorityLevel
) -> float:
    if classification.historical_role:
        return 0.0
    if classification.assistant_role:
        return min(_SENIORITY_SCORE.get(seniority, 5.0), 3.0)
    return _SENIORITY_SCORE.get(seniority, 5.0)


def _company_size_fit(
    contact: Contact,
    roles: tuple[DecisionRole, ...],
    seniority: SeniorityLevel,
    size_provider: ContactSizeProvider | None,
) -> float:
    hint = size_provider.company_size_hint(contact.company_id) if size_provider else "unknown"
    if hint == "unknown":
        return 5.0

    has_ownership = DecisionRole.OWNERSHIP in roles
    is_senior = seniority in (SeniorityLevel.C_LEVEL, SeniorityLevel.VP, SeniorityLevel.DIRECTOR)

    if hint == "small":
        if has_ownership:
            return 10.0
        if is_senior:
            return 8.0
        return 6.0
    elif hint == "medium":
        if is_senior and not has_ownership:
            return 10.0
        if has_ownership:
            return 7.0
        return 6.0
    elif hint == "large":
        if is_senior and not has_ownership:
            return 10.0
        if has_ownership:
            return 4.0
        return 5.0
    return 5.0


def _import_logistics_fit(roles: tuple[DecisionRole, ...]) -> float:
    if not roles or roles == (DecisionRole.UNKNOWN,):
        return 0.0
    return max(_IMPORT_LOGISTICS_BASE.get(r, 0.0) for r in roles)


def _reachability(contact: Contact) -> tuple[float, ContactChannelType | None]:
    score = 0.0
    recommended: ContactChannelType | None = None
    for channel in contact.usable_channels:
        if channel.channel_type is ContactChannelType.EMAIL:
            verified = channel.verification_status in (
                ContactVerificationStatus.SOURCE_VERIFIED,
                ContactVerificationStatus.MANUALLY_VERIFIED,
            )
            pts = _REACHABILITY_VERIFIED_EMAIL if verified else _REACHABILITY_UNVERIFIED_EMAIL
            score += pts
            if recommended is None or verified:
                recommended = ContactChannelType.EMAIL
        elif channel.channel_type is ContactChannelType.LINKEDIN:
            score += _REACHABILITY_LINKEDIN
            recommended = recommended or ContactChannelType.LINKEDIN
        elif channel.channel_type is ContactChannelType.PHONE:
            score += _REACHABILITY_PHONE
            recommended = recommended or ContactChannelType.PHONE
    if not contact.usable_channels:
        score = _REACHABILITY_GENERIC if contact.channels else 0.0
    return min(score, 15.0), recommended


def _source_confidence_score(contact: Contact) -> float:
    if not contact.sources:
        return float(_SOURCE_CONFIDENCE_UNKNOWN)
    best: float = float(_SOURCE_CONFIDENCE_UNKNOWN)
    for ref in contact.sources:
        src = ref.source.lower()
        if any(term in src for term in ("importyeti", "customs", "panjiva", "trade")):
            best = max(best, _SOURCE_CONFIDENCE_TRUSTED)
        elif any(term in src for term in ("company_website", "website", "official")):
            best = max(best, _SOURCE_CONFIDENCE_WEBSITE)
        elif "manual" in src:
            best = max(best, _SOURCE_CONFIDENCE_MANUAL)
        elif any(term in src for term in ("linkedin", "public")):
            best = max(best, _SOURCE_CONFIDENCE_PUBLIC)
        elif "user" in src:
            best = max(best, _SOURCE_CONFIDENCE_USER)
        else:
            best = max(best, float(_SOURCE_CONFIDENCE_UNKNOWN))
    return best


def _derive_seniority(
    contact: Contact, classification: RoleClassification
) -> SeniorityLevel:
    from app.services.contact.title_normalizer import normalize_title

    if classification.historical_role:
        title = normalize_title(contact.title.raw if contact.title else None)
        return title.seniority
    title = normalize_title(contact.title.raw if contact.title else None)
    return title.seniority


def _is_sales_only(roles: tuple[DecisionRole, ...]) -> bool:
    freight_roles = {
        DecisionRole.PROCUREMENT,
        DecisionRole.SOURCING,
        DecisionRole.SUPPLY_CHAIN,
        DecisionRole.IMPORT,
        DecisionRole.LOGISTICS,
        DecisionRole.VENDOR_MANAGEMENT,
        DecisionRole.MERCHANDISING,
        DecisionRole.INVENTORY,
        DecisionRole.OPERATIONS,
        DecisionRole.OWNERSHIP,
        DecisionRole.COMPLIANCE,
    }
    has_sales = DecisionRole.SALES in roles
    has_freight = bool(set(roles) & freight_roles)
    return has_sales and not has_freight


def _is_irrelevant(roles: tuple[DecisionRole, ...]) -> bool:
    if not roles or roles == (DecisionRole.UNKNOWN,):
        return True
    relevant = {
        DecisionRole.PROCUREMENT,
        DecisionRole.SOURCING,
        DecisionRole.SUPPLY_CHAIN,
        DecisionRole.IMPORT,
        DecisionRole.LOGISTICS,
        DecisionRole.VENDOR_MANAGEMENT,
        DecisionRole.MERCHANDISING,
        DecisionRole.INVENTORY,
        DecisionRole.OPERATIONS,
        DecisionRole.OWNERSHIP,
        DecisionRole.COMPLIANCE,
        DecisionRole.FINANCE,
    }
    return not bool(set(roles) & relevant)
