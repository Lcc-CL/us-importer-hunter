"""Persistence for delivery and its read-only prospect sources."""

from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.company import CompanyModel
from app.database.models.contact import ContactChannelModel, ContactModel
from app.database.models.mail_delivery import (
    MailCampaignAuditModel,
    MailCampaignModel,
    MailDeliveryModel,
    MailFeedbackModel,
    MailRateGateModel,
    MailSourceReservationModel,
)
from app.database.models.opportunity import OpportunityModel
from app.database.models.outreach import EmailDraftModel, OutreachModel
from app.database.models.umail_export import SuppressionEntryModel, UmailExportRowModel
from app.domain.clock import utcnow
from app.domain.mail_delivery import (
    CampaignAuditEvent,
    CampaignSummary,
    ClaimedMail,
    FeedbackKind,
    MailContent,
    MailPreview,
    MailResult,
    MailSource,
)
from app.domain.operator import AuditActor
from app.domain.umail_export.models import normalize_suppression_company
from app.shared.exceptions import ApplicationConflictError, ResourceNotFoundError


class MailDeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def template_sources(self, batch_id: UUID) -> list[MailSource]:
        rows = await self.session.scalars(
            select(UmailExportRowModel)
            .where(
                UmailExportRowModel.batch_id == batch_id,
                UmailExportRowModel.status == "ready",
                UmailExportRowModel.email.is_not(None),
            )
            .order_by(UmailExportRowModel.position)
            .limit(1001)
        )
        return [
            MailSource(
                key=f"export:{row.id}",
                company_id=row.company_id,
                company_name=row.company_name,
                recipient=row.email or "",
                first_name=row.first_name or "",
                job_title=row.contact_title or "",
            )
            for row in rows
        ]

    async def draft_sources(self, outreach_id: UUID, version: int) -> list[MailSource]:
        rows = await self.session.execute(
            select(
                CompanyModel.id,
                CompanyModel.name,
                ContactChannelModel.normalized_value,
                EmailDraftModel.subject,
                EmailDraftModel.body,
            )
            .select_from(EmailDraftModel)
            .join(OutreachModel, OutreachModel.id == EmailDraftModel.outreach_id)
            .join(OpportunityModel, OpportunityModel.id == OutreachModel.opportunity_id)
            .join(CompanyModel, CompanyModel.id == OpportunityModel.company_id)
            .join(ContactModel, ContactModel.id == OutreachModel.contact_id)
            .join(ContactChannelModel, ContactChannelModel.contact_id == ContactModel.id)
            .where(
                EmailDraftModel.outreach_id == outreach_id,
                EmailDraftModel.version == version,
                EmailDraftModel.approval_status != "rejected",
                ContactModel.status == "active",
                ContactChannelModel.channel_type == "email",
                ContactChannelModel.verification_status != "invalid",
            )
            .order_by(ContactChannelModel.normalized_value)
        )
        return [
            MailSource(
                key=f"draft:{outreach_id}:{version}",
                company_id=row[0],
                company_name=row[1],
                recipient=row[2],
                first_name="",
                job_title="",
                subject=row[3],
                body=row[4],
            )
            for row in rows
        ]

    async def create(
        self,
        campaign_id: UUID,
        name: str,
        request_hash: str,
        sender_hash: str,
        sender_address: str,
        contents: list[MailContent],
        actor: AuditActor | None = None,
    ) -> None:
        now = utcnow()
        created = await self.session.scalar(
            insert(MailCampaignModel)
            .values(
                id=campaign_id,
                name=name,
                status="draft",
                request_hash=request_hash,
                sender_hash=sender_hash,
                sender_address=sender_address,
                created_at=now,
            )
            .on_conflict_do_nothing()
            .returning(MailCampaignModel.id)
        )
        if created is None:
            return
        await self.session.execute(
            insert(MailDeliveryModel),
            [
                {
                    "id": uuid4(),
                    "campaign_id": campaign_id,
                    "company_id": item.company_id,
                    "source_key": item.source_key,
                    "recipient": item.recipient,
                    "subject": item.subject,
                    "body": item.body,
                    "status": "pending",
                    "attempt": 0,
                    "available_at": now,
                }
                for item in contents
            ],
        )

        if actor is not None:
            self._audit(campaign_id, "create", actor, None, "draft")

    def _audit(
        self,
        campaign_id: UUID,
        action: str,
        actor: AuditActor,
        previous: str | None,
        target: str,
    ) -> None:
        self.session.add(
            MailCampaignAuditModel(
                id=uuid4(),
                campaign_id=campaign_id,
                action=action,
                actor_name=actor.name,
                actor_issuer=actor.issuer,
                actor_subject=actor.subject,
                from_status=previous,
                to_status=target,
                occurred_at=utcnow(),
            )
        )

    async def audit_events(
        self,
        campaign_id: UUID,
        offset: int,
        limit: int,
    ) -> list[CampaignAuditEvent]:
        await self._campaign(campaign_id)
        rows = await self.session.scalars(
            select(MailCampaignAuditModel)
            .where(MailCampaignAuditModel.campaign_id == campaign_id)
            .order_by(MailCampaignAuditModel.occurred_at.desc(), MailCampaignAuditModel.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return [
            CampaignAuditEvent(
                row.id,
                row.action,
                row.actor_name,
                row.actor_issuer,
                row.actor_subject,
                row.from_status,
                row.to_status,
                row.occurred_at,
            )
            for row in rows
        ]

    async def request_hash(self, campaign_id: UUID) -> str | None:
        return (
            await self.session.execute(
                select(MailCampaignModel.request_hash).where(MailCampaignModel.id == campaign_id)
            )
        ).scalar_one_or_none()

    async def list_campaigns(self, offset: int, limit: int) -> list[CampaignSummary]:
        campaigns = list(
            await self.session.scalars(
                select(MailCampaignModel)
                .order_by(
                    MailCampaignModel.created_at.desc(),
                    MailCampaignModel.id.desc(),
                )
                .offset(offset)
                .limit(limit)
            )
        )
        return await self._summaries(campaigns)

    async def _campaign(self, campaign_id: UUID, *, lock: bool = False) -> MailCampaignModel:
        query = select(MailCampaignModel).where(MailCampaignModel.id == campaign_id)
        row = await self.session.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise ResourceNotFoundError("Mail campaign not found")
        return row

    async def summary(self, campaign_id: UUID) -> CampaignSummary:
        return (await self._summaries([await self._campaign(campaign_id)]))[0]

    async def _summaries(self, campaigns: list[MailCampaignModel]) -> list[CampaignSummary]:
        if not campaigns:
            return []
        counts: dict[UUID, dict[str, int]] = {campaign.id: {} for campaign in campaigns}
        feedback: dict[UUID, dict[str, int]] = {campaign.id: {} for campaign in campaigns}
        deliveries = await self.session.execute(
            select(MailDeliveryModel.campaign_id, MailDeliveryModel.status, func.count())
            .where(MailDeliveryModel.campaign_id.in_(counts))
            .group_by(MailDeliveryModel.campaign_id, MailDeliveryModel.status)
        )
        for campaign_id, status, total in deliveries:
            counts[campaign_id][status] = total
        events = await self.session.execute(
            select(MailDeliveryModel.campaign_id, MailFeedbackModel.kind, func.count())
            .join(MailFeedbackModel, MailFeedbackModel.delivery_id == MailDeliveryModel.id)
            .where(MailDeliveryModel.campaign_id.in_(feedback))
            .group_by(MailDeliveryModel.campaign_id, MailFeedbackModel.kind)
        )
        for campaign_id, kind, total in events:
            feedback[campaign_id][kind] = total
        return [
            CampaignSummary(
                row.id,
                row.name,
                row.status,
                row.sender_address,
                row.approved_by,
                counts[row.id],
                feedback[row.id],
            )
            for row in campaigns
        ]

    async def preview(self, campaign_id: UUID, offset: int, limit: int) -> list[MailPreview]:
        await self._campaign(campaign_id)
        rows = await self.session.scalars(
            select(MailDeliveryModel)
            .where(MailDeliveryModel.campaign_id == campaign_id)
            .order_by(MailDeliveryModel.recipient)
            .offset(offset)
            .limit(limit)
        )
        return [
            MailPreview(
                row.id,
                row.recipient,
                row.subject,
                row.body,
                row.status,
                row.attempt,
                row.result_code,
            )
            for row in rows
        ]

    async def transition(
        self,
        campaign_id: UUID,
        action: str,
        actor: AuditActor,
        sender_hash: str | None,
    ) -> None:
        campaign = await self._campaign(campaign_id, lock=True)
        current, target = {
            "approve": ("draft", "active"),
            "pause": ("active", "paused"),
            "resume": ("paused", "active"),
            "cancel": (None, "cancelled"),
        }[action]
        if campaign.status == target:
            return
        if campaign.status == "cancelled" or current not in (None, campaign.status):
            raise ApplicationConflictError("Campaign action is invalid for the current state")
        if target == "active" and sender_hash != campaign.sender_hash:
            raise ApplicationConflictError("Sender configuration is disabled or has changed")
        if action == "resume" and actor.verified and campaign.approved_subject is None:
            raise ApplicationConflictError("Prepare and approve a new campaign with a staff login")
        self._audit(campaign.id, action, actor, campaign.status, target)
        campaign.status = target
        if action == "approve":
            campaign.approved_by = actor.name
            campaign.approved_issuer = actor.issuer
            campaign.approved_subject = actor.subject
            campaign.approved_at = utcnow()

    async def claim(
        self,
        sender_hash: str,
        per_second: float,
        *,
        require_verified_approval: bool = False,
    ) -> ClaimedMail | None:
        # Each consumer locks only its selected row and holds no locks during SMTP.
        query = (
            select(MailDeliveryModel)
            .join(MailCampaignModel, MailCampaignModel.id == MailDeliveryModel.campaign_id)
            .where(
                MailCampaignModel.status == "active",
                MailCampaignModel.sender_hash == sender_hash,
                MailDeliveryModel.status == "pending",
                MailDeliveryModel.available_at <= func.clock_timestamp(),
            )
            .order_by(MailDeliveryModel.available_at, MailDeliveryModel.id)
            .limit(1)
            .with_for_update(of=MailDeliveryModel, skip_locked=True)
        )
        if require_verified_approval:
            query = query.where(MailCampaignModel.approved_subject.is_not(None))
        row = await self.session.scalar(query)
        if row is None:
            return None
        campaign_state = await self.session.scalar(
            select(MailCampaignModel.status)
            .where(MailCampaignModel.id == row.campaign_id)
            .with_for_update(read=True)
        )
        if campaign_state != "active":
            return None
        if await self._suppressed(row):
            row.status = "suppressed"
            row.result_code = "suppression_match"
            return None

        # A short, database-wide reservation spaces dispatches across replicas.
        gate = await self.session.scalar(
            select(MailRateGateModel)
            .where(
                MailRateGateModel.id == 1,
                MailRateGateModel.next_slot <= func.clock_timestamp(),
            )
            .with_for_update(skip_locked=True)
        )
        if gate is None:
            return None
        reservation = await self.session.scalar(
            insert(MailSourceReservationModel)
            .values(source_key=row.source_key, delivery_id=row.id)
            .on_conflict_do_nothing()
            .returning(MailSourceReservationModel.delivery_id)
        )
        if reservation is None:
            reservation = await self.session.scalar(
                select(MailSourceReservationModel.delivery_id).where(
                    MailSourceReservationModel.source_key == row.source_key
                )
            )
        if reservation != row.id:
            row.status = "suppressed"
            row.result_code = "source_already_dispatched"
            return None
        now = await self.session.scalar(select(func.clock_timestamp()))
        assert now is not None
        gate.next_slot = now + timedelta(seconds=1 / per_second)
        row.status = "sending"
        row.attempt += 1
        row.lease_until = now + timedelta(minutes=10)
        return ClaimedMail(row.id, row.attempt, row.recipient, row.subject, row.body)

    async def _suppressed(self, row: MailDeliveryModel) -> bool:
        name = await self.session.scalar(
            select(CompanyModel.name).where(CompanyModel.id == row.company_id)
        )
        if name is None:
            return True
        entry = await self.session.scalar(
            select(SuppressionEntryModel.id)
            .where(
                SuppressionEntryModel.active.is_(True),
                or_(
                    SuppressionEntryModel.email == row.recipient,
                    SuppressionEntryModel.domain == row.recipient.rsplit("@", 1)[-1],
                    SuppressionEntryModel.company == normalize_suppression_company(name),
                ),
            )
            .limit(1)
        )
        return entry is not None

    async def finish(self, mail: ClaimedMail, result: MailResult, max_attempts: int) -> None:
        status = result.outcome
        next_times = {}
        if result.outcome == "retry":
            status = "failed"
            if mail.attempt < max_attempts:
                next_times["available_at"] = utcnow() + timedelta(seconds=15 * 2**mail.attempt)
                await self._finish(mail, "pending", result.code, **next_times)
                return
        await self._finish(mail, status, result.code)

    async def _finish(
        self,
        mail: ClaimedMail,
        status: str,
        code: str,
        **values: object,
    ) -> None:
        await self.session.execute(
            update(MailDeliveryModel)
            .where(
                MailDeliveryModel.id == mail.id,
                MailDeliveryModel.attempt == mail.attempt,
                MailDeliveryModel.status == "sending",
            )
            .values(status=status, result_code=code, lease_until=None, **values)
        )

    async def recover(self) -> None:
        expired = (
            select(MailDeliveryModel.id)
            .where(
                MailDeliveryModel.status == "sending",
                MailDeliveryModel.lease_until < func.clock_timestamp(),
            )
            .order_by(MailDeliveryModel.lease_until, MailDeliveryModel.id)
            .limit(1000)
            .with_for_update(skip_locked=True)
        )
        await self.session.execute(
            update(MailDeliveryModel)
            .where(MailDeliveryModel.id.in_(expired))
            .values(status="unknown", result_code="worker_interrupted", lease_until=None)
        )

    async def record_feedback(self, delivery_id: UUID, event_key: str, kind: FeedbackKind) -> None:
        row = await self.session.scalar(
            select(MailDeliveryModel).where(MailDeliveryModel.id == delivery_id).with_for_update()
        )
        if row is None or row.attempt == 0:
            raise ResourceNotFoundError("Delivery not found")
        now = utcnow()
        created = await self.session.scalar(
            insert(MailFeedbackModel)
            .values(
                event_key=event_key,
                delivery_id=delivery_id,
                kind=kind,
                received_at=now,
            )
            .on_conflict_do_nothing()
            .returning(MailFeedbackModel.event_key)
        )
        if created is None:
            existing = await self.session.get(MailFeedbackModel, event_key)
            if existing is None or (existing.delivery_id, existing.kind) != (delivery_id, kind):
                raise ApplicationConflictError("Feedback event ID is already in use")
            return
        if kind != "unsubscribed" and row.status in ("sending", "unknown"):
            row.status = "accepted"
            row.result_code = "provider_feedback"
            row.lease_until = None
        if kind != "delivered":
            await self.session.execute(
                insert(SuppressionEntryModel)
                .values(
                    id=uuid4(),
                    email=row.recipient,
                    active=True,
                    reason=kind,
                    source="mail_delivery",
                    created_by="mail_delivery",
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(
                    index_elements=[SuppressionEntryModel.email],
                    index_where=text("active AND email IS NOT NULL"),
                )
            )
