"""Recipient holds and feedback under competing PostgreSQL transactions."""

import asyncio
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.database.models.contact_touch import ContactTouchModel
from app.database.models.mail_delivery import MailDeliveryModel
from app.database.models.umail_export import UmailExportBatchModel
from app.database.repositories.contact_touch import SqlAlchemyContactTouchRepository
from app.database.repositories.mail_delivery import MailDeliveryRepository
from app.database.uow import SqlAlchemyUnitOfWork
from app.domain.clock import utcnow
from app.domain.contact_touch import UmailTouchResult
from app.domain.mail_delivery import MailContent
from app.domain.prospect_routing import ProspectRouteReviewStatus
from app.domain.umail_export import UmailExportRow, UmailExportRowStatus
from app.shared.exceptions import ApplicationConflictError
from tests.database.integration.conftest import run_alembic
from tests.database.integration.test_mail_delivery import mail_engine as mail_engine
from tests.database.integration.test_umail_feedback_api import _seed_feedback_exports

WINDOW = timedelta(hours=168)


def export_row(email: str) -> UmailExportRow:
    return UmailExportRow.create(
        batch_id=uuid4(),
        position=1,
        company_id=uuid4(),
        contact_id=uuid4(),
        company_name="Example",
        company_website=None,
        contact_name="Buyer",
        first_name="Test",
        last_name="Buyer",
        contact_title=None,
        contact_role=None,
        contact_seniority=None,
        is_department_contact=False,
        email=email,
        phone=None,
        country=None,
        route_review_status=ProspectRouteReviewStatus.CONFIRMED,
        pre_score=60,
        route_reasons=("eligible",),
        status=UmailExportRowStatus.READY,
        exclusion_reason=None,
    )


async def test_smtp_and_umail_transactions_share_recipient_reservation(
    mail_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(mail_engine)
    target = export_row("recipient@example.test")
    assert target.email is not None
    smtp_id = uuid4()
    entered = asyncio.Event()
    finished = asyncio.Event()

    async def download() -> None:
        with pytest.raises(ApplicationConflictError, match="reserved or recently contacted"):
            async with sessions.begin() as session:
                entered.set()
                await SqlAlchemyContactTouchRepository(session).reserve_export(
                    (target, export_row("other@example.test")),
                    window=WINDOW,
                )
        finished.set()

    async with sessions.begin() as session:
        repo = SqlAlchemyContactTouchRepository(session)
        assert await repo.try_lock_recipient(target.email)
        assert not await repo.smtp_conflict(smtp_id, target.email, window=WINDOW)
        await repo.reserve_smtp(smtp_id, target.email, now=utcnow())
        competing = asyncio.create_task(download())
        await entered.wait()
        assert not finished.is_set()
    await asyncio.wait_for(competing, timeout=10)

    async with sessions.begin() as session:
        repo = SqlAlchemyContactTouchRepository(session)
        assert not await session.scalar(
            select(ContactTouchModel.source_id).where(ContactTouchModel.channel == "umail")
        )
        # An uncertain SMTP attempt has no automatic time-based release.
        await repo.finish_smtp([smtp_id], "unknown")
        await session.execute(update(ContactTouchModel).values(reserved_at=utcnow() - 2 * WINDOW))
        with pytest.raises(ApplicationConflictError, match="reserved or recently contacted"):
            await repo.reserve_export((target,), window=WINDOW)

    async with sessions.begin() as session:
        repo = SqlAlchemyContactTouchRepository(session)
        await repo.confirm_smtp_feedback(smtp_id, target.email)
        assert await repo.smtp_conflict(uuid4(), target.email, window=WINDOW)
        await session.execute(update(ContactTouchModel).values(confirmed_at=utcnow() - 2 * WINDOW))
        await repo.reserve_export((target,), window=WINDOW)
        await repo.reserve_export((target,), window=WINDOW)
        assert await repo.smtp_conflict(uuid4(), target.email, window=WINDOW)


async def test_umail_feedback_keeps_latest_timestamp_and_expires_old_download(
    mail_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(mail_engine)
    target = export_row("expired@example.test")
    assert target.email is not None
    async with sessions.begin() as session:
        repo = SqlAlchemyContactTouchRepository(session)
        await repo.reserve_export((target,), window=WINDOW)
        await session.execute(update(ContactTouchModel).values(reserved_at=utcnow() - 2 * WINDOW))
        with pytest.raises(ApplicationConflictError, match="expired"):
            await repo.reserve_export((target,), window=WINDOW)
        smtp_id = uuid4()
        assert not await repo.smtp_conflict(smtp_id, target.email, window=WINDOW)
        current = utcnow()
        await repo.record_export_results((UmailTouchResult(target.id, target.email, current),))
        await repo.record_export_results(
            (UmailTouchResult(target.id, target.email, current - 2 * WINDOW),)
        )
        assert await repo.smtp_conflict(smtp_id, target.email, window=WINDOW)
        assert await session.scalar(select(ContactTouchModel.confirmed_at)) == current
        with pytest.raises(ApplicationConflictError, match="send results"):
            await repo.reserve_export((target,), window=WINDOW)
        with pytest.raises(ApplicationConflictError, match="recently contacted"):
            await repo.reserve_export((replace(target, id=uuid4()),), window=WINDOW)


async def test_migration_recovers_existing_smtp_and_umail_activity(
    mail_engine: AsyncEngine,
) -> None:
    db_name = mail_engine.url.database
    assert db_name is not None
    await asyncio.to_thread(run_alembic, ["downgrade", "c5e12a4d62af"], db_name)
    sessions = async_sessionmaker(mail_engine)

    def make_uow() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(sessions)

    ids = await _seed_feedback_exports(make_uow)
    stamped = utcnow() - timedelta(hours=2)
    async with sessions.begin() as session:
        await session.execute(
            update(UmailExportBatchModel)
            .where(UmailExportBatchModel.id == ids["batch_alpha"])
            .values(status="downloaded", downloaded_at=stamped)
        )
        await MailDeliveryRepository(session).create(
            uuid4(),
            "Legacy SMTP",
            "x",
            "x",
            "sender@example.test",
            [
                MailContent(state, ids["company_exact"], f"{state}@example.test", "Sub", "Body")
                for state in ("accepted", "unknown", "pending")
            ],
        )
        for state in ("accepted", "unknown", "pending"):
            await session.execute(
                update(MailDeliveryModel)
                .where(MailDeliveryModel.source_key == state)
                .values(status=state, attempt=1)
            )
    await mail_engine.dispose()
    await asyncio.to_thread(run_alembic, ["upgrade", "head"], db_name)
    async with sessions.begin() as session:
        rows = await session.execute(
            select(
                ContactTouchModel.recipient,
                ContactTouchModel.state,
            ).where(ContactTouchModel.channel == "smtp")
        )
        assert dict(rows.tuples().all()) == {
            "accepted@example.test": "confirmed",
            "unknown@example.test": "unknown",
            "pending@example.test": "released",
        }
        hold = await session.get(ContactTouchModel, ("umail", ids["row_exact"]))
        assert hold is not None and hold.state == "reserved" and hold.reserved_at == stamped
        assert await session.get(ContactTouchModel, ("umail", ids["row_ambiguous-two"])) is None
