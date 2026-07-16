"""Deterministic decision-maker selection — mvp-decision-maker-policy-v1.

⚠ Placeholder policy, not validated against real reply data. All weights
live here; unknown data lowers confidence, never fitness. Contacts with
no channels are NOT invalid — they just rank lower on reachability.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

from app.domain.contact import (
    Contact,
    ContactChannelType,
    ContactVerificationStatus,
    DecisionMakerFitAssessment,
    Department,
    SeniorityLevel,
)
from app.domain.values import Confidence, Evidence

POLICY_VERSION = "mvp-decision-maker-policy-v1"

_DEPARTMENT_FIT: Mapping[Department, float] = MappingProxyType(
    {
        Department.SUPPLY_CHAIN: 95.0,
        Department.LOGISTICS: 95.0,
        Department.PROCUREMENT: 90.0,
        Department.OPERATIONS: 65.0,
        Department.EXECUTIVE: 55.0,  # fallback when no specialist exists — never assumed from scale
        Department.FINANCE: 35.0,
        Department.OTHER: 30.0,
        Department.UNKNOWN: 30.0,  # unknown is not negative — mid-low with low confidence
        Department.SALES_MARKETING: 15.0,
        Department.HR: 10.0,
    }
)

_SENIORITY_BONUS: Mapping[SeniorityLevel, float] = MappingProxyType(
    {
        SeniorityLevel.C_LEVEL: 5.0,
        SeniorityLevel.VP: 10.0,
        SeniorityLevel.DIRECTOR: 10.0,
        SeniorityLevel.HEAD: 8.0,
        SeniorityLevel.MANAGER: 5.0,
        SeniorityLevel.SPECIALIST: 0.0,
        SeniorityLevel.UNKNOWN: 0.0,
    }
)


@dataclass(frozen=True)
class DecisionMakerWeights:
    """Every reachability/blend knob in one place."""

    verified_email: float = 60.0
    unverified_email: float = 25.0
    linkedin: float = 15.0
    phone: float = 10.0
    role_share: float = 0.6  # total = role_share × role + (1-role_share) × reachability
    base_confidence: float = 0.35
    title_confidence: float = 0.25
    channel_confidence: float = 0.15
    source_confidence: float = 0.15
    departments: Mapping[Department, float] = field(default_factory=lambda: _DEPARTMENT_FIT)
    seniority_bonus: Mapping[SeniorityLevel, float] = field(
        default_factory=lambda: _SENIORITY_BONUS
    )


class DeterministicDecisionMakerSelectionService:
    def __init__(self, weights: DecisionMakerWeights | None = None) -> None:
        self._w = weights or DecisionMakerWeights()

    @property
    def policy_version(self) -> str:
        return POLICY_VERSION

    async def rank(self, contacts: Sequence[Contact]) -> tuple[DecisionMakerFitAssessment, ...]:
        assessments = [self._assess(contact) for contact in contacts]
        assessments.sort(key=lambda a: (-a.total_score, -a.confidence.value, str(a.contact_id)))
        return tuple(assessments)

    def _assess(self, contact: Contact) -> DecisionMakerFitAssessment:
        w = self._w
        reasons: list[str] = []

        role_fit = w.departments[contact.department]
        reasons.append(f"department {contact.department.value}: role fit {role_fit:g}")
        bonus = w.seniority_bonus[contact.seniority]
        role_fit = min(role_fit + bonus, 100.0)
        if bonus:
            reasons.append(f"seniority {contact.seniority.value}: +{bonus:g}")
        if contact.department is Department.UNKNOWN:
            reasons.append("department unknown — needs research, not a write-off")

        reachability, channel = self._reachability(contact, reasons)
        total = min(w.role_share * role_fit + (1 - w.role_share) * reachability, 100.0)

        confidence_value = w.base_confidence
        if contact.title is not None:
            confidence_value += w.title_confidence
        if contact.usable_channels:
            confidence_value += w.channel_confidence
        if contact.sources:
            confidence_value += w.source_confidence
        else:
            reasons.append("no source references — confidence floor applied")

        evidence = tuple(
            Evidence(
                claim=(
                    f"{contact.name.value} recorded as "
                    f"{contact.title.raw if contact.title else 'unknown role'}"
                ),
                sources=contact.sources,
            )
            for _ in (0,)
            if contact.sources
        )

        return DecisionMakerFitAssessment(
            contact_id=contact.id,
            company_id=contact.company_id,
            role_fit_score=role_fit,
            reachability_score=reachability,
            total_score=total,
            confidence=Confidence(min(confidence_value, 0.9)),
            department=contact.department,
            seniority=contact.seniority,
            reasons=tuple(reasons),
            evidence=evidence,
            recommended_channel=channel,
            policy_version=self.policy_version,  # subclass overrides propagate
        )

    def _reachability(
        self, contact: Contact, reasons: list[str]
    ) -> tuple[float, ContactChannelType | None]:
        w = self._w
        score = 0.0
        recommended: ContactChannelType | None = None
        for channel in contact.usable_channels:
            if channel.channel_type is ContactChannelType.EMAIL:
                verified = channel.verification_status in (
                    ContactVerificationStatus.SOURCE_VERIFIED,
                    ContactVerificationStatus.MANUALLY_VERIFIED,
                )
                points = w.verified_email if verified else w.unverified_email
                label = "verified" if verified else "unverified"
                reasons.append(f"{label} email: reachability +{points:g}")
                score += points
                if recommended is None or verified:
                    recommended = ContactChannelType.EMAIL
            elif channel.channel_type is ContactChannelType.LINKEDIN:
                score += w.linkedin
                reasons.append(f"linkedin profile: reachability +{w.linkedin:g}")
                recommended = recommended or ContactChannelType.LINKEDIN
            elif channel.channel_type is ContactChannelType.PHONE:
                score += w.phone
                reasons.append(f"phone: reachability +{w.phone:g}")
                recommended = recommended or ContactChannelType.PHONE
        if not contact.usable_channels:
            reasons.append("no usable channels — reachability 0, contact still valid")
        return min(score, 100.0), recommended
