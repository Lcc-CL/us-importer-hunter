"""Contact aggregate ↔ persistence mapping."""

from typing import Any

from app.database.mappers.opportunity import _sources_from_json, _sources_to_json
from app.database.models.contact import (
    ContactChannelModel,
    ContactFitAssessmentModel,
    ContactModel,
    ContactSourceModel,
)
from app.domain.contact import (
    Contact,
    ContactChannel,
    ContactChannelType,
    ContactStatus,
    ContactVerificationStatus,
    DecisionMakerFitAssessment,
    Department,
    JobTitle,
    PersonName,
    SeniorityLevel,
)
from app.domain.values import Confidence, Evidence, SourceReference


class ContactMapper:
    @staticmethod
    def to_model(contact: Contact) -> ContactModel:
        return ContactModel(
            id=contact.id,
            company_id=contact.company_id,
            name=contact.name.value,
            normalized_name=contact.name.normalized,
            title_raw=contact.title.raw if contact.title else None,
            department=contact.department.value,
            seniority=contact.seniority.value,
            status=contact.status.value,
            invalid_reason=contact.invalid_reason,
            created_at=contact.created_at,
            updated_at=contact.updated_at,
            channels=[
                ContactChannelModel(
                    contact_id=contact.id,
                    channel_type=channel.channel_type.value,
                    normalized_value=channel.normalized_value,
                    display_value=channel.display_value,
                    verification_status=channel.verification_status.value,
                    source=channel.source_reference.source,
                    source_reference=channel.source_reference.reference,
                    source_retrieved_at=channel.source_reference.retrieved_at,
                    verified_at=channel.verified_at,
                    confidence=channel.confidence,
                )
                for channel in contact.channels
            ],
            sources=[
                ContactSourceModel(
                    contact_id=contact.id,
                    position=position,
                    source=ref.source,
                    reference=ref.reference,
                    retrieved_at=ref.retrieved_at,
                )
                for position, ref in enumerate(contact.sources)
            ],
        )

    @staticmethod
    def to_domain(model: ContactModel) -> Contact:
        contact = Contact(
            id=model.id,
            company_id=model.company_id,
            name=PersonName(model.name),
            title=JobTitle(model.title_raw) if model.title_raw else None,
            created_at=model.created_at,
        )
        contact._department = Department(model.department)
        contact._seniority = SeniorityLevel(model.seniority)
        contact._status = ContactStatus(model.status)
        contact._invalid_reason = model.invalid_reason
        contact._updated_at = model.updated_at
        contact._channels = [
            ContactChannel(
                channel_type=ContactChannelType(row.channel_type),
                normalized_value=row.normalized_value,
                display_value=row.display_value,
                verification_status=ContactVerificationStatus(row.verification_status),
                source_reference=SourceReference(
                    source=row.source,
                    reference=row.source_reference,
                    retrieved_at=row.source_retrieved_at,
                ),
                verified_at=row.verified_at,
                confidence=row.confidence,
            )
            for row in model.channels
        ]
        contact._sources = [
            SourceReference(
                source=row.source, reference=row.reference, retrieved_at=row.retrieved_at
            )
            for row in model.sources
        ]
        return contact


class FitAssessmentMapper:
    @staticmethod
    def to_model(assessment: DecisionMakerFitAssessment) -> ContactFitAssessmentModel:
        return ContactFitAssessmentModel(
            contact_id=assessment.contact_id,
            assessment_fingerprint=assessment.assessment_fingerprint,
            company_id=assessment.company_id,
            role_fit_score=assessment.role_fit_score,
            reachability_score=assessment.reachability_score,
            total_score=assessment.total_score,
            confidence=assessment.confidence.value,
            department=assessment.department.value,
            seniority=assessment.seniority.value,
            recommended_channel=(
                assessment.recommended_channel.value if assessment.recommended_channel else None
            ),
            reasons=list(assessment.reasons),
            evidence=[
                {"claim": e.claim, "sources": _sources_to_json(e.sources)}
                for e in assessment.evidence
            ],
            policy_version=assessment.policy_version,
            roles_json=list(assessment.roles),
            normalized_title=assessment.normalized_title,
            classification_method=assessment.classification_method,
            classification_confidence=assessment.classification_confidence,
            classification_reasons_json=list(assessment.classification_reasons),
            taxonomy_version=assessment.taxonomy_version,
            score_breakdown_json=assessment.score_breakdown_json,
            selection_status=assessment.selection_status,
            selection_reasons_json=list(assessment.selection_reasons_json),
            scoring_version=assessment.scoring_version,
            assessed_at=assessment.assessed_at,
        )

    @staticmethod
    def to_domain(model: ContactFitAssessmentModel) -> DecisionMakerFitAssessment:
        evidence_payload: list[dict[str, Any]] = model.evidence
        return DecisionMakerFitAssessment(
            contact_id=model.contact_id,
            company_id=model.company_id,
            role_fit_score=model.role_fit_score,
            reachability_score=model.reachability_score,
            total_score=model.total_score,
            confidence=Confidence(model.confidence),
            department=Department(model.department),
            seniority=SeniorityLevel(model.seniority),
            reasons=tuple(model.reasons),
            evidence=tuple(
                Evidence(claim=item["claim"], sources=_sources_from_json(item["sources"]))
                for item in evidence_payload
            ),
            recommended_channel=(
                ContactChannelType(model.recommended_channel)
                if model.recommended_channel
                else None
            ),
            policy_version=model.policy_version,
            roles=tuple(model.roles_json),
            normalized_title=model.normalized_title,
            classification_method=model.classification_method,
            classification_confidence=model.classification_confidence,
            classification_reasons=tuple(model.classification_reasons_json),
            taxonomy_version=model.taxonomy_version,
            score_breakdown_json=model.score_breakdown_json or {},
            selection_status=model.selection_status,
            selection_reasons_json=tuple(model.selection_reasons_json),
            scoring_version=model.scoring_version,
            assessment_fingerprint=model.assessment_fingerprint,
            assessed_at=model.assessed_at,
        )
