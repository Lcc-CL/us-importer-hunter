"""Durable worker pulses and read-only, bounded live-queue aggregation."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import DateTime, and_, delete, false, func, select, text, true, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.mail_delivery import (
    MailCampaignModel,
    MailDeliveryModel,
    MailWorkerPulseModel,
)
from app.domain.mail_operations import MAIL_PULSE_TTL_SECONDS, MailQueueFacts, MailWorkerActivity


class MailOperationsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _now(self) -> datetime:
        return (
            await self.session.execute(select(func.now(type_=DateTime(timezone=True))))
        ).scalar_one()

    async def publish(self, instance_id: UUID, activity: MailWorkerActivity) -> None:
        now = await self._now()
        values = {
            "seen_at": now,
            "retired_at": None,
            "polled_at": (
                now - timedelta(seconds=activity.poll_age_seconds)
                if activity.poll_age_seconds is not None
                else None
            ),
            "completed_at": (
                now - timedelta(seconds=activity.completion_age_seconds)
                if activity.completion_age_seconds is not None
                else None
            ),
            "sender_hash": activity.sender_hash,
            "verified_only": activity.verified_only,
        }
        await self.session.execute(
            insert(MailWorkerPulseModel)
            .values(id=instance_id, **values)
            .on_conflict_do_update(index_elements=[MailWorkerPulseModel.id], set_=values)
        )
        await self.session.execute(
            delete(MailWorkerPulseModel).where(
                MailWorkerPulseModel.seen_at < now - timedelta(days=1)
            )
        )

    async def retire(self, instance_id: UUID) -> None:
        await self.session.execute(
            update(MailWorkerPulseModel)
            .where(MailWorkerPulseModel.id == instance_id)
            .values(retired_at=func.now())
        )

    async def snapshot(
        self,
        sender_hash: str | None,
        *,
        verified_only: bool,
    ) -> MailQueueFacts:
        time = func.now(type_=DateTime(timezone=True))
        cutoff = time - timedelta(seconds=MAIL_PULSE_TTL_SECONDS)
        delivery, campaign = MailDeliveryModel, MailCampaignModel
        active = campaign.status == "active"
        eligible = campaign.sender_hash == sender_hash if sender_hash is not None else false()
        if verified_only:
            eligible = and_(eligible, campaign.approved_subject.is_not(None))
        ready = and_(active, eligible, delivery.available_at <= time)
        pending = (
            select(
                func.count().filter(ready).label("ready"),
                func.count()
                .filter(active, eligible, delivery.available_at > time)
                .label("scheduled"),
                func.count().filter(campaign.status == "paused").label("paused"),
                func.count().filter(active, ~eligible).label("blocked"),
                func.min(delivery.available_at).filter(ready).label("oldest"),
            )
            .select_from(delivery)
            .join(campaign, campaign.id == delivery.campaign_id)
            # Literal predicates let even a generic plan use the partial index.
            .where(
                text("mail_deliveries.status = 'pending'"),
                campaign.status.in_(("active", "paused")),
            )
            .subquery()
        )
        sending = delivery.status == "sending"
        triage = (
            select(
                func.count().filter(sending).label("in_flight"),
                func.count().filter(sending, delivery.lease_until <= time).label("expired_leases"),
                func.count().filter(delivery.status == "unknown").label("unknown"),
            )
            .where(text("mail_deliveries.status IN ('sending', 'unknown')"))
            .subquery()
        )

        pulse = MailWorkerPulseModel
        compatible = (
            and_(pulse.sender_hash == sender_hash, pulse.verified_only == verified_only)
            if sender_hash is not None
            else false()
        )
        live = and_(pulse.seen_at >= cutoff, pulse.retired_at.is_(None))
        fleet = select(
            func.count().filter(live).label("live_workers"),
            func.count().filter(live, pulse.sender_hash.is_not(None)).label("dispatch_workers"),
            func.count().filter(live, compatible).label("compatible_workers"),
            func.count()
            .filter(live, compatible, pulse.polled_at >= cutoff)
            .label("polling_workers"),
            func.max(pulse.polled_at).filter(live, compatible).label("last_poll_at"),
            # Recent history stays visible after graceful shutdown.
            func.max(pulse.completed_at).filter(compatible).label("last_completion_at"),
        ).subquery()

        # These three aggregates each return one row. Evaluate them in one
        # statement so a delivery cannot count as both pending and in flight.
        row = (
            await self.session.execute(
                select(time.label("observed_at"), *pending.c, *triage.c, *fleet.c).select_from(
                    pending.join(triage, true()).join(fleet, true())
                )
            )
        ).one()
        oldest = int((row.observed_at - row.oldest).total_seconds()) if row.oldest else None
        return MailQueueFacts(
            observed_at=row.observed_at,
            ready=row.ready,
            scheduled=row.scheduled,
            paused=row.paused,
            blocked=row.blocked,
            in_flight=row.in_flight,
            expired_leases=row.expired_leases,
            unknown=row.unknown,
            oldest_ready_seconds=oldest,
            live_workers=row.live_workers,
            dispatch_workers=row.dispatch_workers,
            compatible_workers=row.compatible_workers,
            polling_workers=row.polling_workers,
            last_poll_at=row.last_poll_at,
            last_completion_at=row.last_completion_at,
        )
