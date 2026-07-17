"""Repository integration tests against real PostgreSQL.

Every assertion goes through the repository/UnitOfWork public surface —
domain aggregates in, domain aggregates out.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.database.models.contact import ContactModel
from app.domain.company import Company
from app.domain.exceptions import DuplicateOperation
from app.domain.opportunity import Opportunity, OpportunityStage
from app.domain.outreach import OutcomeKind, Outreach, OutreachStatus
from app.domain.task import Task, TaskStatus
from app.domain.values import (
    CompanyName,
    IdempotencyKey,
    OpportunityScore,
    SourceReference,
    WebsiteUrl,
)
from tests.database.integration.conftest import UowFactory
from tests.domain.conftest import make_assessment


def make_source() -> SourceReference:
    return SourceReference(
        source="importyeti",
        reference="https://example.com/bol/1",
        retrieved_at=datetime(2026, 7, 1, tzinfo=UTC),
    )


async def persist_company(uow_factory: UowFactory) -> Company:
    company = Company.create(CompanyName("Pacific Home Goods Inc."), WebsiteUrl("https://phg.com"))
    company.add_source(make_source())
    company.mark_verified()
    company.drain_events()
    async with uow_factory() as uow:
        await uow.companies.add(company)
        await uow.commit()
    return company


class TestCompanyRepository:
    async def test_add_and_get_round_trip(self, uow_factory: UowFactory) -> None:
        company = await persist_company(uow_factory)
        async with uow_factory() as uow:
            loaded = await uow.companies.get_by_id(company.id)
        assert loaded is not None
        assert isinstance(loaded, Company)
        assert loaded.name == company.name
        assert loaded.sources == company.sources
        assert loaded.verified is True

    async def test_save_persists_rename_and_alias(self, uow_factory: UowFactory) -> None:
        company = await persist_company(uow_factory)
        async with uow_factory() as uow:
            loaded = await uow.companies.get_by_id(company.id)
            assert loaded is not None
            loaded.rename(CompanyName("PHG Incorporated"))
            await uow.companies.save(loaded)
            await uow.commit()
        async with uow_factory() as uow:
            reloaded = await uow.companies.get_by_id(company.id)
        assert reloaded is not None
        assert reloaded.name == CompanyName("PHG Incorporated")
        assert CompanyName("Pacific Home Goods Inc.") in reloaded.aliases

    async def test_find_by_normalized_name(self, uow_factory: UowFactory) -> None:
        company = await persist_company(uow_factory)
        async with uow_factory() as uow:
            found = await uow.companies.find_by_normalized_name(
                CompanyName("PACIFIC  HOME GOODS INC.")
            )
            missing = await uow.companies.find_by_normalized_name(CompanyName("Nobody Corp"))
        assert found is not None and found.id == company.id
        assert missing is None

    async def test_unique_normalized_name_enforced_by_db(self, uow_factory: UowFactory) -> None:
        await persist_company(uow_factory)
        duplicate = Company.create(CompanyName("PACIFIC HOME GOODS INC."))
        async with uow_factory() as uow:
            await uow.companies.add(duplicate)
            with pytest.raises(DuplicateOperation):
                await uow.commit()

    async def test_rollback_discards_changes(self, uow_factory: UowFactory) -> None:
        company = Company.create(CompanyName("Ghost Corp"))
        async with uow_factory() as uow:
            await uow.companies.add(company)
            await uow.rollback()
        async with uow_factory() as uow:
            assert await uow.companies.get_by_id(company.id) is None

    async def test_exit_without_commit_discards_changes(self, uow_factory: UowFactory) -> None:
        company = Company.create(CompanyName("Never Committed LLC"))
        async with uow_factory() as uow:
            await uow.companies.add(company)
            # no commit
        async with uow_factory() as uow:
            assert await uow.companies.exists(company.id) is False


class TestOpportunityRepository:
    async def test_round_trip_and_append_only_history(self, uow_factory: UowFactory) -> None:
        company = await persist_company(uow_factory)
        opportunity = Opportunity.create_for_company(company_id=company.id, user_id=uuid4())
        opportunity.apply_assessment(make_assessment(60.0))
        opportunity.drain_events()
        async with uow_factory() as uow:
            await uow.opportunities.add(opportunity)
            await uow.commit()

        # second assessment appends — first history row must survive untouched
        async with uow_factory() as uow:
            loaded = await uow.opportunities.get_by_id(opportunity.id)
            assert loaded is not None
            loaded.apply_assessment(make_assessment(85.0))
            loaded.drain_events()
            await uow.opportunities.save(loaded)
            await uow.commit()

        async with uow_factory() as uow:
            reloaded = await uow.opportunities.get_by_id(opportunity.id)
        assert reloaded is not None
        assert reloaded.score == OpportunityScore(85.0)
        assert len(reloaded.history) == 2
        assert reloaded.history[0].new_score == OpportunityScore(60.0)
        assert reloaded.history[1].new_score == OpportunityScore(85.0)
        assert reloaded.stage is OpportunityStage.ASSESSED

    async def test_get_for_company_and_user(self, uow_factory: UowFactory) -> None:
        company = await persist_company(uow_factory)
        user_id = uuid4()
        opportunity = Opportunity.create_for_company(company_id=company.id, user_id=user_id)
        opportunity.drain_events()
        async with uow_factory() as uow:
            await uow.opportunities.add(opportunity)
            await uow.commit()
        async with uow_factory() as uow:
            mine = await uow.opportunities.get_for_company_and_user(company.id, user_id)
            theirs = await uow.opportunities.get_for_company_and_user(company.id, uuid4())
        assert mine is not None and mine.id == opportunity.id
        assert theirs is None

    async def test_get_prefers_open_over_closed(self, uow_factory: UowFactory) -> None:
        company = await persist_company(uow_factory)
        user_id = uuid4()
        closed = Opportunity.create_for_company(company_id=company.id, user_id=user_id)
        closed.disqualify("not a fit")
        closed.drain_events()
        opened = Opportunity.create_for_company(company_id=company.id, user_id=user_id)
        opened.drain_events()
        async with uow_factory() as uow:
            await uow.opportunities.add(closed)
            await uow.opportunities.add(opened)
            await uow.commit()
        async with uow_factory() as uow:
            current = await uow.opportunities.get_for_company_and_user(company.id, user_id)
        assert current is not None and current.id == opened.id


class TestOutreachRepository:
    async def _persist_conversation(self, uow_factory: UowFactory) -> Outreach:
        company = await persist_company(uow_factory)
        opportunity = Opportunity.create_for_company(company_id=company.id, user_id=uuid4())
        contact_id = uuid4()
        async with uow_factory() as uow:
            await uow.opportunities.add(opportunity)
            assert uow._session is not None
            uow._session.add(
                ContactModel(
                    id=contact_id,
                    company_id=company.id,
                    name="Maria Chen",
                    normalized_name="maria chen",
                    title_raw="Director of Supply Chain",
                    department="supply_chain",
                    seniority="director",
                    status="active",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
            await uow.commit()

        outreach = Outreach.create(opportunity_id=opportunity.id)
        outreach.attach_contact(contact_id)
        outreach.add_draft("Cutting CNSHA-USLAX costs", "Hi Maria ...", "sales-v1")
        outreach.approve_draft(1, approved_by_name="Alex")
        outreach.mark_sent()
        outreach.record_reply("positive")
        outreach.drain_events()
        async with uow_factory() as uow:
            await uow.outreaches.add(outreach)
            await uow.commit()
        return outreach

    async def test_round_trip_conversation(self, uow_factory: UowFactory) -> None:
        outreach = await self._persist_conversation(uow_factory)
        async with uow_factory() as uow:
            loaded = await uow.outreaches.get_by_id(outreach.id)
        assert loaded is not None
        assert loaded.status is OutreachStatus.REPLIED
        assert loaded.drafts == outreach.drafts
        assert loaded.outcomes == outreach.outcomes
        assert loaded.follow_up_active is False

    async def test_save_appends_outcome_history(self, uow_factory: UowFactory) -> None:
        outreach = await self._persist_conversation(uow_factory)
        async with uow_factory() as uow:
            loaded = await uow.outreaches.get_by_id(outreach.id)
            assert loaded is not None
            loaded.mark_won("signed 20 TEU/year")
            loaded.drain_events()
            await uow.outreaches.save(loaded)
            await uow.commit()
        async with uow_factory() as uow:
            reloaded = await uow.outreaches.get_by_id(outreach.id)
        assert reloaded is not None
        assert reloaded.status is OutreachStatus.WON
        assert [o.kind for o in reloaded.outcomes] == [OutcomeKind.REPLY, OutcomeKind.WON]

    async def test_list_for_opportunity(self, uow_factory: UowFactory) -> None:
        outreach = await self._persist_conversation(uow_factory)
        async with uow_factory() as uow:
            conversations = await uow.outreaches.list_for_opportunity(outreach.opportunity_id)
        assert [o.id for o in conversations] == [outreach.id]


class TestTaskRepository:
    async def test_round_trip_with_attempt_history(self, uow_factory: UowFactory) -> None:
        task = Task.create("hunt importers", IdempotencyKey.from_parts("hunt", "u1"))
        task.start()
        task.fail("timeout")
        task.retry()
        task.complete()
        task.drain_events()
        async with uow_factory() as uow:
            await uow.tasks.add(task)
            await uow.commit()
        async with uow_factory() as uow:
            loaded = await uow.tasks.get_by_id(task.id)
        assert loaded is not None
        assert loaded.status is TaskStatus.COMPLETED
        assert loaded.attempt_history == task.attempt_history

    async def test_active_keys_feed_domain_idempotency(self, uow_factory: UowFactory) -> None:
        key = IdempotencyKey.from_parts("hunt", "user-1")
        active = Task.create("first hunt", key)
        async with uow_factory() as uow:
            await uow.tasks.add(active)
            await uow.commit()
        async with uow_factory() as uow:
            keys = await uow.tasks.active_keys()
        assert key in keys

    async def test_db_rejects_second_active_task_with_same_key(
        self, uow_factory: UowFactory
    ) -> None:
        key = IdempotencyKey.from_parts("hunt", "user-2")
        async with uow_factory() as uow:
            await uow.tasks.add(Task.create("first", key))
            await uow.commit()
        async with uow_factory() as uow:
            await uow.tasks.add(Task.create("second", key))
            with pytest.raises(DuplicateOperation):
                await uow.commit()

    async def test_finished_task_frees_the_key(self, uow_factory: UowFactory) -> None:
        key = IdempotencyKey.from_parts("hunt", "user-3")
        first = Task.create("first", key)
        first.start()
        first.complete()
        first.drain_events()
        async with uow_factory() as uow:
            await uow.tasks.add(first)
            await uow.commit()
        async with uow_factory() as uow:
            await uow.tasks.add(Task.create("second", key))
            await uow.commit()  # allowed: partial unique index covers active tasks only
            keys = await uow.tasks.active_keys()
        assert key in keys
