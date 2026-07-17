"""Outreach aggregate ↔ persistence mapping."""

from app.database.models.outreach import EmailDraftModel, OutcomeModel, OutreachModel
from app.domain.outreach import (
    EmailDraft,
    EmailDraftStatus,
    Outcome,
    OutcomeKind,
    Outreach,
    OutreachStatus,
)


class OutreachMapper:
    @staticmethod
    def to_model(outreach: Outreach) -> OutreachModel:
        return OutreachModel(
            id=outreach.id,
            opportunity_id=outreach.opportunity_id,
            contact_id=outreach.contact_id,
            status=outreach.status.value,
            approved_version=outreach.approved_version,
            sent_version=outreach.sent_version,
            follow_up_active=outreach.follow_up_active,
            closed_reason=outreach.closed_reason,
            created_at=outreach.created_at,
            drafts=[
                EmailDraftModel(
                    outreach_id=outreach.id,
                    version=draft.version,
                    subject=draft.subject,
                    body=draft.body,
                    approval_status=draft.approval_status.value,
                    approved_at=draft.approved_at,
                    approved_by_name=draft.approved_by_name,
                    provider=draft.provider,
                    model=draft.model,
                    prompt_version=draft.prompt_version,
                    context_fingerprint=draft.context_fingerprint,
                    generated_at=draft.generated_at,
                )
                for draft in outreach.drafts
            ],
            outcomes=[
                OutcomeModel(
                    outreach_id=outreach.id,
                    position=position,
                    kind=outcome.kind.value,
                    detail=outcome.detail,
                    draft_version=outcome.draft_version,
                    occurred_at=outcome.occurred_at,
                )
                for position, outcome in enumerate(outreach.outcomes)
            ],
        )

    @staticmethod
    def to_domain(model: OutreachModel) -> Outreach:
        outreach = Outreach(
            id=model.id, opportunity_id=model.opportunity_id, created_at=model.created_at
        )
        outreach._contact_id = model.contact_id
        outreach._status = OutreachStatus(model.status)
        outreach._approved_version = model.approved_version
        outreach._sent_version = model.sent_version
        outreach._follow_up_active = model.follow_up_active
        outreach._closed_reason = model.closed_reason
        outreach._drafts = [
            EmailDraft(
                version=row.version,
                subject=row.subject,
                body=row.body,
                approval_status=EmailDraftStatus(row.approval_status),
                approved_at=row.approved_at,
                approved_by_name=row.approved_by_name,
                provider=row.provider,
                model=row.model,
                prompt_version=row.prompt_version,
                context_fingerprint=row.context_fingerprint,
                generated_at=row.generated_at,
            )
            for row in model.drafts
        ]
        outreach._outcomes = [
            Outcome(
                kind=OutcomeKind(row.kind),
                detail=row.detail,
                draft_version=row.draft_version,
                occurred_at=row.occurred_at,
            )
            for row in model.outcomes
        ]
        return outreach
