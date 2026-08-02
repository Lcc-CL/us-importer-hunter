"""Deterministic decision-maker selection — mvp-decision-maker-policy-v2.

Six-factor scoring (role_relevance, seniority, company_size_fit,
import_logistics_fit, reachability, source_confidence) replaces the
legacy single-department + seniority-bonus. The breakdown is recorded
with each assessment so a reviewer can see why one person ranked above
another.
"""

from collections.abc import Sequence
from uuid import UUID

from app.domain.contact import (
    Contact,
    DecisionMakerFitAssessment,
    Department,
)
from app.domain.contact.roles import (
    DecisionRole,
    legacy_department,
)
from app.domain.values import Confidence, Evidence
from app.services.contact.scorer import (
    POLICY_VERSION_V2,
    CandidateScore,
    ContactSizeProvider,
    SixFactorScorer,
)

POLICY_VERSION = POLICY_VERSION_V2  # backward-compatible alias


class DeterministicDecisionMakerSelectionService:
    """Scores and ranks contacts across six independent dimensions.

    The `rank` method returns fit assessments for persistence and
    compatibility. Callers that need the full selection picture
    (primary / alternatives / supporting / rejected) should use the
    `score_all` method and pass the results to `select()` from the
    selector module.
    """

    def __init__(self, size_provider: ContactSizeProvider | None = None) -> None:
        self._scorer = SixFactorScorer(size_provider)

    @property
    def policy_version(self) -> str:
        return POLICY_VERSION_V2

    def score_all(
        self,
        contacts: Sequence[Contact],
        *,
        company_id: UUID | None = None,
    ) -> tuple[CandidateScore, ...]:
        """Score every contact. Callers own the ranking and selection."""
        return tuple(
            self._scorer.score(contact, company_id=company_id) for contact in contacts
        )

    async def rank(
        self,
        contacts: Sequence[Contact],
        **kwargs: object,
    ) -> tuple[DecisionMakerFitAssessment, ...]:
        """Score, rank, and return legacy-compatible fit assessments.

        Accepts size_provider kwarg for company_size_fit scoring.
        """
        size_provider = kwargs.get("size_provider")
        company_id = kwargs.get("company_id")
        if company_id is not None and not isinstance(company_id, UUID):
            raise TypeError("company_id must be a UUID")
        scorer = SixFactorScorer(size_provider) if size_provider else self._scorer  # type: ignore[arg-type]
        contact_by_id = {contact.id: contact for contact in contacts}
        candidates = tuple(
            scorer.score(contact, company_id=company_id) for contact in contacts
        )
        assessments = [
            _to_assessment(
                candidate,
                contact_by_id[candidate.contact_id],
                self.policy_version,
                company_id,
            )
            for candidate in candidates
        ]
        assessments.sort(key=lambda a: (-a.total_score, -a.confidence.value, str(a.contact_id)))
        return tuple(assessments)


def _to_assessment(
    candidate: CandidateScore,
    contact: Contact,
    policy_version: str,
    company_id: UUID | None,
) -> DecisionMakerFitAssessment:
    roles_values = tuple(r.value for r in candidate.roles)
    department = _department_from_roles(candidate.roles)
    reasons = _build_reasons(candidate)

    reasons_for_fingerprint: list[str] = []
    for r in candidate.selection_reasons:
        reasons_for_fingerprint.append(r)
    for r in candidate.rejection_reasons:
        reasons_for_fingerprint.append(r.value)

    evidence = (
        Evidence(
            claim=(
                f"{contact.name.value} scored as "
                f"{candidate.overall_score:.0f}/100 decision maker"
            ),
            sources=contact.sources,
        ),
    ) if contact.sources else ()
    confidence_value = round(
        0.45 + 0.15 * min(len([r for r in candidate.roles if r != DecisionRole.UNKNOWN]), 3)
        + (0.1 if candidate.role_classification_confidence >= 0.6 else 0.0),
        3,
    )
    confidence_value = min(confidence_value, 0.9)

    resolved_company_id = company_id or contact.company_id
    if resolved_company_id is None:
        raise ValueError("decision-maker assessment requires company context")
    return DecisionMakerFitAssessment(
        contact_id=candidate.contact_id,
        company_id=resolved_company_id,
        role_fit_score=candidate.role_relevance_score,
        reachability_score=candidate.reachability_score,
        total_score=candidate.overall_score,
        confidence=Confidence(confidence_value),
        department=department,
        seniority=candidate.seniority,
        reasons=tuple(reasons),
        roles=roles_values,
        normalized_title=candidate.normalized_title,
        classification_method="deterministic",
        classification_confidence=candidate.role_classification_confidence,
        classification_reasons=(),
        taxonomy_version="decision-role-v1",
        score_breakdown_json=candidate.score_breakdown,
        selection_status=(
            candidate.selection_status.value if candidate.selection_status else None
        ),
        selection_reasons_json=tuple(
            str(r) for r in candidate.rejection_reasons
        ),
        scoring_version=POLICY_VERSION_V2,
        evidence=evidence,
        recommended_channel=candidate.recommended_channel,
        policy_version=policy_version,
    )


def _department_from_roles(roles: tuple[DecisionRole, ...]) -> Department:
    return Department(legacy_department(roles))


def _build_reasons(candidate: CandidateScore) -> list[str]:
    reasons: list[str] = []
    reasons.append(f"role_relevance={candidate.role_relevance_score:.0f}")
    reasons.append(f"seniority={candidate.seniority_score:.0f}")
    reasons.append(f"company_size_fit={candidate.company_size_fit_score:.0f}")
    reasons.append(f"import_logistics_fit={candidate.import_logistics_fit_score:.0f}")
    reasons.append(f"reachability={candidate.reachability_score:.0f}")
    reasons.append(f"source_confidence={candidate.source_confidence_score:.0f}")
    if candidate.historical_role:
        reasons.append("historical_role — not a current decision maker")
    if candidate.assistant_role:
        reasons.append("assistant_role — supports the decision maker")
    if candidate.rejection_reasons:
        reasons.append(f"rejected: {','.join(r.value for r in candidate.rejection_reasons)}")
    return reasons
