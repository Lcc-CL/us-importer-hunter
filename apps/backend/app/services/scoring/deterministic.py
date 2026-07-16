"""Deterministic placeholder scorer — mvp-deterministic-v1.

⚠ NOT a business scoring model. This exists so the Company → Opportunity
pipeline runs end-to-end with explainable, stable numbers. It uses only
fields that actually exist today (website, verification, signals,
provenance) and never invents import volume, cargo value or China
dependency. Replace behind OpportunityScoringService when the real
scoring dimensions are decided (open product question).
"""

from dataclasses import dataclass

from app.domain.services import OpportunityScoringInput
from app.domain.values import (
    Confidence,
    Evidence,
    OpportunityAssessment,
    OpportunityScore,
    ScoringPolicy,
)

SCORING_VERSION = "mvp-deterministic-v1"

_TRUSTED_SOURCES = frozenset({"importyeti"})
_IMPORT_KEYWORDS = ("import", "shipment", "bol", "customs")
_GROWTH_KEYWORDS = ("grow", "increas", "rising")


@dataclass(frozen=True)
class DeterministicScoringWeights:
    """Every weight in one place — nothing hides in the workflow."""

    base: float = 20.0
    website_bonus: float = 15.0
    verified_bonus: float = 10.0
    import_signal_bonus: float = 20.0
    growth_signal_bonus: float = 15.0
    base_confidence: float = 0.2
    per_source_confidence: float = 0.1
    trusted_source_confidence: float = 0.2
    max_confidence: float = 0.9


class DeterministicOpportunityScoringService:
    """Same input, same assessment — no I/O, no randomness, no LLM."""

    def __init__(
        self,
        weights: DeterministicScoringWeights | None = None,
        policy: ScoringPolicy | None = None,
    ) -> None:
        self._weights = weights or DeterministicScoringWeights()
        self._policy = policy or ScoringPolicy(version=SCORING_VERSION)

    @property
    def scoring_version(self) -> str:
        return SCORING_VERSION

    async def assess(self, scoring_input: OpportunityScoringInput) -> OpportunityAssessment:
        w = self._weights
        score = w.base
        reasons = [f"baseline for a discovered US importer (+{w.base:g})"]

        if scoring_input.website_host:
            score += w.website_bonus
            reasons.append(f"reachable website {scoring_input.website_host} (+{w.website_bonus:g})")
        if scoring_input.verified:
            score += w.verified_bonus
            reasons.append(f"company verified against sources (+{w.verified_bonus:g})")

        lowered = [signal.lower() for signal in scoring_input.signals]
        if any(any(k in s for k in _IMPORT_KEYWORDS) for s in lowered):
            score += w.import_signal_bonus
            reasons.append(f"import-related signal present (+{w.import_signal_bonus:g})")
        if any(any(k in s for k in _GROWTH_KEYWORDS) for s in lowered):
            score += w.growth_signal_bonus
            reasons.append(f"growth-related signal present (+{w.growth_signal_bonus:g})")

        distinct_sources = {ref.source for ref in scoring_input.sources}
        confidence_value = w.base_confidence + w.per_source_confidence * len(distinct_sources)
        if distinct_sources & _TRUSTED_SOURCES:
            confidence_value += w.trusted_source_confidence
        confidence_value = min(confidence_value, w.max_confidence)
        if not scoring_input.sources:
            reasons.append("no source references — confidence floor applied")

        evidence = tuple(
            Evidence(
                claim=f"{ref.source} recorded this company at {ref.reference}",
                sources=(ref,),
            )
            for ref in scoring_input.sources
        )

        new_score = OpportunityScore(min(score, 100.0))
        priority = self._policy.priority_for(new_score)
        return OpportunityAssessment(
            new_score=new_score,
            confidence=Confidence(confidence_value),
            reasons=tuple(reasons),
            evidence=evidence,
            priority=priority,
            recommended_action=self._recommend(priority.value),
            assessed_by=type(self).__name__,
            scoring_version=SCORING_VERSION,
            user_lens_version=scoring_input.user_lens_version,
            assessed_at=scoring_input.assessed_at,
        )

    @staticmethod
    def _recommend(priority: str) -> str:
        return {
            "high": "start outreach: select a contact and draft an email",
            "medium": "enrich further before outreach (evidence is thin)",
            "low": "deprioritize: monitor for new shipment signals",
        }[priority]
