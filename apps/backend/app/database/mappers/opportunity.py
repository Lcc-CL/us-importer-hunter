"""Opportunity aggregate ↔ persistence mapping."""

from datetime import datetime
from typing import Any

from app.database.models.opportunity import (
    OpportunityAssessmentModel,
    OpportunityEvidenceModel,
    OpportunityModel,
)
from app.domain.opportunity import Opportunity, OpportunityStage
from app.domain.values import (
    Confidence,
    DataCompleteness,
    DimensionAssessment,
    DimensionStatus,
    Evidence,
    OpportunityAssessment,
    OpportunityScore,
    Priority,
    QualificationDecision,
    ScoreBreakdown,
    ScoringDimension,
    SourceReference,
)


def _sources_to_json(sources: tuple[SourceReference, ...]) -> list[dict[str, Any]]:
    return [
        {
            "source": ref.source,
            "reference": ref.reference,
            "retrieved_at": ref.retrieved_at.isoformat(),
        }
        for ref in sources
    ]


def _sources_from_json(payload: list[dict[str, Any]]) -> tuple[SourceReference, ...]:
    return tuple(
        SourceReference(
            source=item["source"],
            reference=item["reference"],
            retrieved_at=datetime.fromisoformat(item["retrieved_at"]),
        )
        for item in payload
    )


def _breakdown_to_json(breakdown: ScoreBreakdown) -> dict[str, Any]:
    return {
        "total_score": breakdown.total_score,
        "maximum_score": breakdown.maximum_score,
        "assessed_weight": breakdown.assessed_weight,
        "missing_weight": breakdown.missing_weight,
        "dimensions": [
            {
                "dimension": d.dimension.value,
                "weight": d.weight,
                "status": d.status.value,
                "earned_score": d.earned_score,
                "normalized_value": d.normalized_value,
                "raw_value": d.raw_value,
                "confidence": d.confidence,
                "reasons": list(d.reasons),
                "evidence": [
                    {"claim": e.claim, "sources": _sources_to_json(e.sources)} for e in d.evidence
                ],
            }
            for d in breakdown.dimensions
        ],
    }


def _breakdown_from_json(payload: dict[str, Any]) -> ScoreBreakdown:
    return ScoreBreakdown(
        total_score=payload["total_score"],
        maximum_score=payload["maximum_score"],
        assessed_weight=payload["assessed_weight"],
        missing_weight=payload["missing_weight"],
        dimensions=tuple(
            DimensionAssessment(
                dimension=ScoringDimension(item["dimension"]),
                weight=item["weight"],
                status=DimensionStatus(item["status"]),
                earned_score=item["earned_score"],
                normalized_value=item["normalized_value"],
                raw_value=item["raw_value"],
                confidence=item["confidence"],
                reasons=tuple(item["reasons"]),
                evidence=tuple(
                    Evidence(claim=e["claim"], sources=_sources_from_json(e["sources"]))
                    for e in item["evidence"]
                ),
            )
            for item in payload["dimensions"]
        ),
    )


class OpportunityMapper:
    @staticmethod
    def to_model(opportunity: Opportunity) -> OpportunityModel:
        return OpportunityModel(
            id=opportunity.id,
            company_id=opportunity.company_id,
            user_id=opportunity.user_id,
            stage=opportunity.stage.value,
            stage_reason=opportunity.stage_reason,
            score=opportunity.score.value if opportunity.score else None,
            confidence=opportunity.confidence.value if opportunity.confidence else None,
            priority=opportunity.priority.value if opportunity.priority else None,
            created_at=opportunity.created_at,
            assessments=[
                OpportunityAssessmentModel(
                    opportunity_id=opportunity.id,
                    position=position,
                    old_score=assessment.old_score.value if assessment.old_score else None,
                    new_score=assessment.new_score.value,
                    confidence=assessment.confidence.value,
                    reasons=list(assessment.reasons),
                    priority=assessment.priority.value if assessment.priority else None,
                    recommended_action=assessment.recommended_action,
                    assessed_by=assessment.assessed_by,
                    data_completeness=(
                        assessment.data_completeness.value
                        if assessment.data_completeness
                        else None
                    ),
                    qualification_decision=(
                        assessment.qualification_decision.value
                        if assessment.qualification_decision
                        else None
                    ),
                    score_breakdown=(
                        _breakdown_to_json(assessment.score_breakdown)
                        if assessment.score_breakdown
                        else None
                    ),
                    assessment_fingerprint=assessment.assessment_fingerprint,
                    scoring_version=assessment.scoring_version,
                    policy_version=assessment.policy_version,
                    user_lens_version=assessment.user_lens_version,
                    assessed_at=assessment.assessed_at,
                    evidence=[
                        OpportunityEvidenceModel(
                            opportunity_id=opportunity.id,
                            assessment_position=position,
                            position=ev_position,
                            claim=evidence.claim,
                            sources=_sources_to_json(evidence.sources),
                        )
                        for ev_position, evidence in enumerate(assessment.evidence)
                    ],
                )
                for position, assessment in enumerate(opportunity.history)
            ],
        )

    @staticmethod
    def to_domain(model: OpportunityModel) -> Opportunity:
        opportunity = Opportunity(
            id=model.id,
            company_id=model.company_id,
            user_id=model.user_id,
            created_at=model.created_at,
        )
        opportunity._stage = OpportunityStage(model.stage)
        opportunity._stage_reason = model.stage_reason
        opportunity._score = OpportunityScore(model.score) if model.score is not None else None
        opportunity._confidence = (
            Confidence(model.confidence) if model.confidence is not None else None
        )
        opportunity._priority = Priority(model.priority) if model.priority is not None else None
        opportunity._history = [
            OpportunityAssessment(
                new_score=OpportunityScore(row.new_score),
                confidence=Confidence(row.confidence),
                reasons=tuple(row.reasons),
                scoring_version=row.scoring_version,
                evidence=tuple(
                    Evidence(claim=ev.claim, sources=_sources_from_json(ev.sources))
                    for ev in row.evidence
                ),
                old_score=OpportunityScore(row.old_score) if row.old_score is not None else None,
                priority=Priority(row.priority) if row.priority is not None else None,
                recommended_action=row.recommended_action,
                assessed_by=row.assessed_by,
                data_completeness=(
                    DataCompleteness(row.data_completeness)
                    if row.data_completeness is not None
                    else None
                ),
                qualification_decision=(
                    QualificationDecision(row.qualification_decision)
                    if row.qualification_decision is not None
                    else None
                ),
                score_breakdown=(
                    _breakdown_from_json(row.score_breakdown)
                    if row.score_breakdown is not None
                    else None
                ),
                assessment_fingerprint=row.assessment_fingerprint,
                policy_version=row.policy_version,
                user_lens_version=row.user_lens_version,
                assessed_at=row.assessed_at,
            )
            for row in model.assessments
        ]
        return opportunity
