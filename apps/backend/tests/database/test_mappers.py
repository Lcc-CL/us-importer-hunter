"""Mapper round-trips: domain → persistence → domain must be lossless,
and reconstruction must never resurrect pending domain events."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.database.mappers import CompanyMapper, OpportunityMapper, OutreachMapper, TaskMapper
from app.domain.company import Company
from app.domain.opportunity import Opportunity, OpportunityStage
from app.domain.outreach import OutcomeKind, Outreach, OutreachStatus
from app.domain.task import Task, TaskStatus
from app.domain.values import (
    CompanyName,
    Evidence,
    IdempotencyKey,
    OpportunityScore,
    SourceReference,
    WebsiteUrl,
)
from tests.domain.conftest import make_assessment


@pytest.fixture
def source_ref() -> SourceReference:
    return SourceReference(
        source="importyeti",
        reference="https://example.com/bol/123",
        retrieved_at=datetime(2026, 7, 1, tzinfo=UTC),
    )


@pytest.fixture
def evidence(source_ref: SourceReference) -> Evidence:
    return Evidence(claim="~40 FCL from CNSHA in Q2", sources=(source_ref,))


def make_company(source_ref: SourceReference) -> Company:
    company = Company.create(CompanyName("Pacific Home Goods Inc."), WebsiteUrl("https://phg.com"))
    company.add_alias(CompanyName("PACIFIC HOME GOODS"))
    company.add_source(source_ref)
    company.add_signal("volume growing")
    company.mark_verified()
    return company


class TestCompanyMapper:
    def test_round_trip(self, source_ref: SourceReference) -> None:
        original = make_company(source_ref)
        original.drain_events()
        restored = CompanyMapper.to_domain(CompanyMapper.to_model(original))

        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.website == original.website
        assert restored.aliases == original.aliases
        assert restored.sources == original.sources
        assert restored.signals == original.signals
        assert restored.verified is True
        assert restored.created_at == original.created_at

    def test_pending_events_not_restored(self, source_ref: SourceReference) -> None:
        original = make_company(source_ref)
        assert len(original.drain_events()) == 1  # CompanyVerified was pending
        restored = CompanyMapper.to_domain(CompanyMapper.to_model(original))
        assert restored.drain_events() == ()


class TestOpportunityMapper:
    def test_round_trip_with_history(self, evidence: Evidence) -> None:
        original = Opportunity.create_for_company(company_id=uuid4(), user_id=uuid4())
        original.apply_assessment(make_assessment(60.0))
        original.apply_assessment(make_assessment(85.0, evidence=(evidence,)))
        original.qualify()
        original.drain_events()

        restored = OpportunityMapper.to_domain(OpportunityMapper.to_model(original))

        assert restored.id == original.id
        assert restored.company_id == original.company_id
        assert restored.user_id == original.user_id
        assert restored.stage is OpportunityStage.QUALIFIED
        assert restored.score == OpportunityScore(85.0)
        assert restored.confidence == original.confidence
        assert restored.priority == original.priority
        assert restored.history == original.history  # value objects preserved exactly

    def test_events_not_restored(self) -> None:
        original = Opportunity.create_for_company(company_id=uuid4(), user_id=uuid4())
        original.apply_assessment(make_assessment(50.0))
        # OpportunityCreated + OpportunityAssessmentApplied were pending
        assert len(original.drain_events()) == 2
        restored = OpportunityMapper.to_domain(OpportunityMapper.to_model(original))
        assert restored.drain_events() == ()


class TestOutreachMapper:
    def test_round_trip_full_conversation(self) -> None:
        original = Outreach.create(opportunity_id=uuid4())
        original.attach_contact(uuid4())
        original.add_draft("Subject A", "Body A", "sales-v1")
        original.add_draft("Subject B", "Body B", "sales-v1")
        original.approve_draft(2, approved_by_name="Alex")
        original.mark_sent()
        original.record_reply("positive")
        original.drain_events()

        restored = OutreachMapper.to_domain(OutreachMapper.to_model(original))

        assert restored.id == original.id
        assert restored.opportunity_id == original.opportunity_id
        assert restored.contact_id == original.contact_id
        assert restored.status is OutreachStatus.REPLIED
        assert restored.drafts == original.drafts
        assert restored.approved_version == 2
        assert restored.sent_version == 2
        assert restored.follow_up_active is False
        assert restored.outcomes == original.outcomes
        assert restored.outcomes[0].kind is OutcomeKind.REPLY
        assert restored.drain_events() == ()


class TestTaskMapper:
    def test_round_trip_with_attempts(self) -> None:
        original = Task.create("hunt importers", IdempotencyKey.from_parts("hunt", "u1"))
        original.start()
        original.fail("timeout")
        original.retry()
        original.complete()
        original.drain_events()

        restored = TaskMapper.to_domain(TaskMapper.to_model(original))

        assert restored.id == original.id
        assert restored.goal == original.goal
        assert restored.idempotency_key == original.idempotency_key
        assert restored.status is TaskStatus.COMPLETED
        assert restored.attempts == 2
        assert restored.max_retries == original.max_retries
        assert restored.started_at == original.started_at
        assert restored.finished_at == original.finished_at
        assert restored.attempt_history == original.attempt_history
        assert restored.drain_events() == ()
