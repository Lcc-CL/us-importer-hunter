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
    Evidence,
    OpportunityAssessment,
    OpportunityScore,
    Priority,
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
                    scoring_version=assessment.scoring_version,
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
                user_lens_version=row.user_lens_version,
                assessed_at=row.assessed_at,
            )
            for row in model.assessments
        ]
        return opportunity
