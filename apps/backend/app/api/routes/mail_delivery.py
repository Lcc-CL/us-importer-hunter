"""Administrative campaign endpoints, opt-out and authenticated event intake."""

from secrets import compare_digest
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Query, Response
from fastapi.responses import HTMLResponse

from app.api.deps import DbSessionDep, SettingsDep
from app.api.operator_identity import get_operator, require_operator_roles
from app.database.repositories.mail_delivery import MailDeliveryRepository
from app.database.repositories.mail_operations import MailOperationsRepository
from app.domain.mail_delivery import (
    CampaignAuditEvent,
    CampaignSummary,
    DeliveryReconciliation,
    MailPreview,
    ReconciliationEvidence,
)
from app.domain.mail_operations import MailQueueStatus
from app.domain.operator import AuditActor, Operator
from app.schemas.mail_delivery import (
    MailCampaignAction,
    MailDraftCampaign,
    MailFeedbackInput,
    MailReconciliationInput,
    MailTemplateCampaign,
)
from app.shared.exceptions import ResourceNotFoundError
from app.workflows.mail_delivery.operations import read_mail_operations
from app.workflows.mail_delivery.workflow import CampaignRequest, MailCampaignWorkflow

router = APIRouter(tags=["mail-delivery"])
Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=50)]
OperatorDep = Annotated[Operator | None, Depends(get_operator)]


def get_campaign_workflow(session: DbSessionDep, settings: SettingsDep) -> MailCampaignWorkflow:
    return MailCampaignWorkflow(MailDeliveryRepository(session), session.commit, settings)


CampaignWorkflowDep = Annotated[MailCampaignWorkflow, Depends(get_campaign_workflow)]


def get_reconciliation_operator(operator: OperatorDep) -> Operator:
    if operator is None:
        raise HTTPException(status_code=403, detail="A verified staff login is required")
    require_operator_roles(operator, "approver", "admin")
    return operator


ReconciliationOperatorDep = Annotated[Operator, Depends(get_reconciliation_operator)]


@router.get("/mail-campaigns/config")
async def config(
    workflow: CampaignWorkflowDep,
    operator: OperatorDep,
) -> dict[str, str | bool | None]:
    roles = operator.roles if operator is not None else {"sales", "approver", "admin"}
    return {
        "sender": workflow.sender.address if workflow.sender else None,
        "send_ready": workflow.send_ready,
        "operator_name": operator.name if operator else None,
        "can_create": bool(roles.intersection({"sales", "admin"})),
        "can_approve": bool(roles.intersection({"approver", "admin"})),
        "can_pause": bool(roles.intersection({"approver", "admin"})),
        "can_manage": "admin" in roles,
    }


@router.post("/mail-campaigns/template", status_code=201)
async def template_campaign(
    payload: MailTemplateCampaign,
    workflow: CampaignWorkflowDep,
    operator: OperatorDep,
) -> CampaignSummary:
    require_operator_roles(operator, "sales", "admin")
    return await workflow.prepare(
        CampaignRequest(
            id=payload.id,
            name=payload.name,
            export_id=payload.export_id,
            outreach_id=None,
            draft_version=None,
            recipient=None,
            subject=payload.subject,
            body=payload.body,
        ),
        operator.audit_actor() if operator else AuditActor("Unverified operator"),
    )


@router.post("/mail-campaigns/draft", status_code=201)
async def draft_campaign(
    payload: MailDraftCampaign,
    workflow: CampaignWorkflowDep,
    operator: OperatorDep,
) -> CampaignSummary:
    require_operator_roles(operator, "sales", "admin")
    return await workflow.prepare(
        CampaignRequest(
            id=payload.id,
            name=payload.name,
            export_id=None,
            outreach_id=payload.outreach_id,
            draft_version=payload.draft_version,
            recipient=payload.recipient,
            subject=payload.subject,
            body=payload.body,
        ),
        operator.audit_actor() if operator else AuditActor("Unverified operator"),
    )


@router.get("/mail-campaigns")
async def list_campaigns(
    session: DbSessionDep,
    offset: Offset = 0,
    limit: Limit = 20,
) -> list[CampaignSummary]:
    return await MailDeliveryRepository(session).list_campaigns(offset, limit)


@router.get("/mail-campaigns/operations")
async def operations(
    operator: ReconciliationOperatorDep,
    session: DbSessionDep,
    settings: SettingsDep,
) -> MailQueueStatus:
    return await read_mail_operations(MailOperationsRepository(session), settings)


@router.get("/mail-campaigns/{campaign_id}")
async def campaign(campaign_id: UUID, session: DbSessionDep) -> CampaignSummary:
    return await MailDeliveryRepository(session).summary(campaign_id)


@router.get("/mail-campaigns/{campaign_id}/messages")
async def messages(
    campaign_id: UUID,
    session: DbSessionDep,
    offset: Offset = 0,
    limit: Limit = 20,
    status: Literal["unknown"] | None = None,
) -> list[MailPreview]:
    return await MailDeliveryRepository(session).preview(campaign_id, offset, limit, status=status)


@router.get("/mail-campaigns/{campaign_id}/messages/{delivery_id}/reconciliations")
async def reconciliation_history(
    campaign_id: UUID,
    delivery_id: UUID,
    operator: ReconciliationOperatorDep,
    session: DbSessionDep,
) -> list[DeliveryReconciliation]:
    return await MailDeliveryRepository(session).delivery_reconciliations(campaign_id, delivery_id)


@router.post("/mail-campaigns/{campaign_id}/messages/{delivery_id}/reconciliations")
async def reconcile_delivery(
    campaign_id: UUID,
    delivery_id: UUID,
    payload: MailReconciliationInput,
    operator: ReconciliationOperatorDep,
    workflow: CampaignWorkflowDep,
) -> DeliveryReconciliation:
    if payload.decision == "not_submitted":
        require_operator_roles(operator, "admin")
    evidence = ReconciliationEvidence(
        payload.attempt,
        payload.decision,
        payload.provider_reference,
        payload.note,
    )
    return await workflow.reconcile(campaign_id, delivery_id, evidence, operator.audit_actor())


@router.get("/mail-campaigns/{campaign_id}/audit")
async def campaign_audit(
    campaign_id: UUID,
    session: DbSessionDep,
    operator: OperatorDep,
    offset: Offset = 0,
    limit: Limit = 20,
) -> list[CampaignAuditEvent]:
    require_operator_roles(operator, "approver", "admin")
    return await MailDeliveryRepository(session).audit_events(campaign_id, offset, limit)


@router.post("/mail-campaigns/{campaign_id}/actions")
async def campaign_action(
    campaign_id: UUID,
    payload: MailCampaignAction,
    workflow: CampaignWorkflowDep,
    operator: OperatorDep,
) -> CampaignSummary:
    if payload.action in ("approve", "pause"):
        require_operator_roles(operator, "approver", "admin")
    else:
        require_operator_roles(operator, "admin")
    actor = (
        operator.audit_actor() if operator else AuditActor(payload.actor or "Unverified operator")
    )
    return await workflow.change(campaign_id, payload.action, actor)


@router.post("/mail-feedback", status_code=204)
async def feedback(
    payload: MailFeedbackInput,
    session: DbSessionDep,
    settings: SettingsDep,
    mail_feedback_key: Annotated[str | None, Header(alias="X-Mail-Feedback-Key")] = None,
) -> Response:
    expected = settings.mail_feedback_secret.get_secret_value()
    if not expected or not compare_digest(expected.encode(), (mail_feedback_key or "").encode()):
        raise HTTPException(status_code=401, detail="Mail feedback authentication required")
    await MailDeliveryRepository(session).record_feedback(
        payload.delivery_id,
        f"provider:{payload.event_id}",
        payload.kind,
    )
    await session.commit()
    return Response(status_code=204)


def _optout_page(content: str) -> HTMLResponse:
    return HTMLResponse(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Email preferences</title><body><main>{content}</main></body></html>",
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": (
                "default-src 'none'; form-action 'self'; frame-ancestors 'none'"
            ),
            "Referrer-Policy": "no-referrer",
        },
    )


@router.get("/mail-unsubscribe/{delivery_id}", response_class=HTMLResponse)
async def unsubscribe_form(delivery_id: UUID) -> HTMLResponse:
    return _optout_page(
        '<h1>Unsubscribe</h1><form method="post">'
        '<button name="List-Unsubscribe" value="One-Click">Unsubscribe</button></form>'
    )


@router.post("/mail-unsubscribe/{delivery_id}", response_class=HTMLResponse)
async def unsubscribe(
    delivery_id: UUID,
    session: DbSessionDep,
    preference: Annotated[Literal["One-Click"], Form(alias="List-Unsubscribe")],
) -> HTMLResponse:
    try:
        await MailDeliveryRepository(session).record_feedback(
            delivery_id,
            f"unsubscribe:{delivery_id}",
            "unsubscribed",
        )
        await session.commit()
    except ResourceNotFoundError:
        pass
    return _optout_page("<h1>Unsubscribe request processed</h1>")
