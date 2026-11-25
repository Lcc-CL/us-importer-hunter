"""Serialize recipient admission across both channels inside their transactions."""

from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.contact_touch import ContactTouchModel
from app.database.models.umail_export import SuppressionEntryModel
from app.domain.clock import utcnow
from app.domain.contact_touch import UmailTouchResult
from app.domain.umail_export import UmailExportRow, UmailExportRowStatus
from app.domain.umail_export.models import normalize_suppression_company
from app.shared.exceptions import ApplicationConflictError

# Bound advisory lock usage for large imports. A shared bucket can delay
# unrelated mail, but business matching still compares the full address.
LOCK_NAMESPACE = 22082401
LOCK_BUCKET_MASK = 1023


def _active_since(cutoff: datetime) -> Select[tuple[ContactTouchModel]]:
    touch = ContactTouchModel
    stamp = func.greatest(touch.reserved_at, touch.confirmed_at)
    return select(touch).where(
        or_(
            touch.state == "unknown",
            and_(touch.channel == "smtp", touch.state == "reserved"),
            and_(touch.state.in_(("confirmed", "reserved")), stamp > cutoff),
        )
    )


class SqlAlchemyContactTouchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_recipients(self, emails: list[str]) -> None:
        if not emails:
            return
        await self._session.execute(
            text("""
                SELECT pg_advisory_xact_lock(:namespace, lock_key)
                FROM (
                    SELECT DISTINCT hashtext(recipient) & :mask AS lock_key
                    FROM unnest(CAST(:emails AS text[])) AS addresses(recipient)
                ) AS keys
                ORDER BY lock_key
            """),
            {"namespace": LOCK_NAMESPACE, "mask": LOCK_BUCKET_MASK, "emails": emails},
        )

    async def try_lock_recipient(self, email: str) -> bool:
        acquired = await self._session.scalar(
            select(
                func.pg_try_advisory_xact_lock(
                    LOCK_NAMESPACE,
                    func.hashtext(email).bitwise_and(LOCK_BUCKET_MASK),
                )
            )
        )
        return acquired is True

    async def smtp_conflict(
        self,
        delivery_id: UUID,
        email: str,
        *,
        window: timedelta,
    ) -> bool:
        current = await self._session.scalar(
            _active_since(utcnow() - window)
            .with_only_columns(ContactTouchModel.source_id)
            .where(
                ContactTouchModel.recipient == email,
                ~and_(
                    ContactTouchModel.channel == "smtp",
                    ContactTouchModel.source_id == delivery_id,
                    ContactTouchModel.state == "reserved",
                ),
            )
            .limit(1)
        )
        return current is not None

    async def reserve_smtp(self, delivery_id: UUID, email: str, *, now: datetime) -> None:
        await self._session.execute(
            insert(ContactTouchModel)
            .values(
                channel="smtp",
                source_id=delivery_id,
                recipient=email,
                state="reserved",
                reserved_at=now,
            )
            .on_conflict_do_update(
                index_elements=[ContactTouchModel.channel, ContactTouchModel.source_id],
                set_={"state": "reserved", "reserved_at": now},
                where=ContactTouchModel.state == "released",
            )
        )

    async def finish_smtp(
        self,
        delivery_ids: list[UUID],
        state: Literal["confirmed", "unknown", "released"],
    ) -> None:
        if not delivery_ids:
            return
        await self._session.execute(
            update(ContactTouchModel)
            .where(
                ContactTouchModel.channel == "smtp",
                ContactTouchModel.source_id.in_(delivery_ids),
                ContactTouchModel.state == "reserved",
            )
            .values(state=state, confirmed_at=utcnow() if state == "confirmed" else None)
        )

    async def confirm_smtp_feedback(self, delivery_id: UUID, email: str) -> None:
        statement = insert(ContactTouchModel).values(
            channel="smtp",
            source_id=delivery_id,
            recipient=email,
            state="confirmed",
            confirmed_at=utcnow(),
        )
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[ContactTouchModel.channel, ContactTouchModel.source_id],
                set_={
                    "state": "confirmed",
                    "confirmed_at": func.greatest(
                        ContactTouchModel.confirmed_at, statement.excluded.confirmed_at
                    ),
                },
            )
        )

    async def reserve_export(
        self,
        rows: tuple[UmailExportRow, ...],
        *,
        window: timedelta,
    ) -> None:
        targets = {
            row.id: row for row in rows if row.status is UmailExportRowStatus.READY and row.email
        }
        if not targets:
            return
        emails = sorted({row.email.strip().lower() for row in targets.values() if row.email})
        await self.lock_recipients(emails)
        now = utcnow()
        cutoff = now - window
        existing = {
            touch.source_id: touch
            for touch in await self._session.scalars(
                select(ContactTouchModel).where(
                    ContactTouchModel.channel == "umail", ContactTouchModel.source_id.in_(targets)
                )
            )
        }
        if any(
            touch.state != "reserved" or touch.reserved_at is None or touch.reserved_at <= cutoff
            for touch in existing.values()
        ):
            raise ApplicationConflictError(
                "This Umail export has expired or already has send results. Prepare a new batch."
            )
        other = await self._session.scalar(
            _active_since(cutoff)
            .with_only_columns(ContactTouchModel.source_id)
            .where(
                ContactTouchModel.recipient.in_(emails),
                ~and_(
                    ContactTouchModel.channel == "umail",
                    ContactTouchModel.source_id.in_(targets),
                ),
            )
            .limit(1)
        )
        if other is not None:
            raise ApplicationConflictError(
                "The CSV includes recipients reserved or recently contacted via SMTP or Umail."
            )
        await self._check_export_suppressions(tuple(targets.values()), emails)
        new_values = [
            {
                "channel": "umail",
                "source_id": row.id,
                "recipient": row.email.strip().lower(),
                "state": "reserved",
                "reserved_at": now,
            }
            for row in targets.values()
            if row.email and row.id not in existing
        ]
        if new_values:
            await self._session.execute(insert(ContactTouchModel), new_values)

    async def _check_export_suppressions(
        self,
        rows: tuple[UmailExportRow, ...],
        emails: list[str],
    ) -> None:
        entry = SuppressionEntryModel
        suppressed = await self._session.scalar(
            select(entry.id)
            .where(
                entry.active.is_(True),
                or_(
                    entry.email.in_(emails),
                    entry.domain.in_({email.rsplit("@", 1)[-1] for email in emails}),
                    entry.company.in_(
                        {normalize_suppression_company(r.company_name) for r in rows}
                    ),
                ),
            )
            .limit(1)
        )
        if suppressed is not None:
            raise ApplicationConflictError(
                "The CSV includes recipients added to suppression after the preview."
            )

    async def record_export_results(self, results: tuple[UmailTouchResult, ...]) -> None:
        latest: dict[UUID, UmailTouchResult] = {}
        for result in results:
            old = latest.get(result.export_row_id)
            if old is None or result.occurred_at > old.occurred_at:
                latest[result.export_row_id] = result
        if not latest:
            return
        items = tuple(latest.values())
        now = utcnow()
        # Acquire the same buckets in order before inserting. The count makes
        # the volatile lock CTE a prerequisite for projecting non-empty input.
        await self._session.execute(
            text("""
                WITH batch AS MATERIALIZED (
                    SELECT * FROM unnest(CAST(:ids AS uuid[]), CAST(:emails AS text[]),
                                         CAST(:stamps AS timestamptz[]))
                        AS rows(source_id, recipient, confirmed_at)
                ), acquired AS MATERIALIZED (
                    SELECT pg_advisory_xact_lock(:namespace, lock_key)
                    FROM (SELECT DISTINCT hashtext(recipient) & :mask AS lock_key FROM batch) keys
                    ORDER BY lock_key
                )
                INSERT INTO contact_touches
                    (channel, source_id, recipient, state, confirmed_at)
                SELECT 'umail', source_id, recipient, 'confirmed', confirmed_at FROM batch
                WHERE (SELECT count(*) FROM acquired) > 0
                ON CONFLICT (channel, source_id) DO UPDATE SET
                    state = 'confirmed',
                    confirmed_at = greatest(contact_touches.confirmed_at, excluded.confirmed_at)
            """),
            {
                "namespace": LOCK_NAMESPACE,
                "mask": LOCK_BUCKET_MASK,
                "ids": [item.export_row_id for item in items],
                "emails": [item.email for item in items],
                "stamps": [min(now, item.occurred_at) for item in items],
            },
        )
