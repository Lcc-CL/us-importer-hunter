"""Opportunity aggregate: controlled score changes, stages, history."""

from uuid import uuid4

import pytest

from app.domain.events import (
    OpportunityAssessmentApplied,
    OpportunityDisqualified,
    OpportunityQualified,
)
from app.domain.exceptions import (
    DomainError,
    InvalidStateTransition,
    MissingEvidence,
)
from app.domain.opportunity import Opportunity, OpportunityStage
from app.domain.values import Evidence, OpportunityScore, Priority
from tests.domain.conftest import make_assessment


@pytest.fixture
def opportunity() -> Opportunity:
    return Opportunity.create_for_company(company_id=uuid4(), user_id=uuid4())


class TestAssessment:
    def test_apply_updates_score_and_stage(self, opportunity: Opportunity) -> None:
        opportunity.apply_assessment(make_assessment(82.0))
        assert opportunity.score == OpportunityScore(82.0)
        assert opportunity.priority is Priority.HIGH
        assert opportunity.stage is OpportunityStage.ASSESSED

    def test_emits_event_with_old_and_new_score(self, opportunity: Opportunity) -> None:
        opportunity.apply_assessment(make_assessment(60.0))
        opportunity.apply_assessment(make_assessment(85.0))
        drained = opportunity.drain_events()
        events = [e for e in drained if isinstance(e, OpportunityAssessmentApplied)]
        assert events[0].old_score is None
        assert events[1].old_score == OpportunityScore(60.0)
        assert events[1].new_score == OpportunityScore(85.0)

    def test_history_is_append_only(self, opportunity: Opportunity) -> None:
        opportunity.apply_assessment(make_assessment(60.0))
        opportunity.apply_assessment(make_assessment(85.0))
        assert len(opportunity.history) == 2
        assert opportunity.history[0].new_score == OpportunityScore(60.0)
        # the exposed history is a snapshot — mutating it changes nothing
        snapshot = opportunity.history
        assert isinstance(snapshot, tuple)
        assert len(opportunity.history) == 2

    def test_score_has_no_public_setter(self, opportunity: Opportunity) -> None:
        with pytest.raises(AttributeError):
            opportunity.score = OpportunityScore(99.0)  # type: ignore[misc]

    def test_cannot_assess_closed_opportunity(self, opportunity: Opportunity) -> None:
        opportunity.apply_assessment(make_assessment(30.0))
        opportunity.disqualify("volume too low")
        with pytest.raises(InvalidStateTransition):
            opportunity.apply_assessment(make_assessment(90.0))


class TestQualification:
    def test_requires_assessment_first(self, opportunity: Opportunity) -> None:
        with pytest.raises(InvalidStateTransition):
            opportunity.qualify()

    def test_requires_evidence(self, opportunity: Opportunity) -> None:
        opportunity.apply_assessment(make_assessment(82.0, evidence=()))
        with pytest.raises(MissingEvidence):
            opportunity.qualify()

    def test_qualify_with_evidence(self, opportunity: Opportunity, evidence: Evidence) -> None:
        opportunity.apply_assessment(make_assessment(82.0, evidence=(evidence,)))
        opportunity.qualify()
        assert opportunity.stage is OpportunityStage.QUALIFIED
        qualified = [e for e in opportunity.drain_events() if isinstance(e, OpportunityQualified)]
        assert len(qualified) == 1
        assert qualified[0].priority is Priority.HIGH

    def test_cannot_qualify_twice(self, opportunity: Opportunity, evidence: Evidence) -> None:
        opportunity.apply_assessment(make_assessment(82.0, evidence=(evidence,)))
        opportunity.qualify()
        with pytest.raises(InvalidStateTransition):
            opportunity.qualify()


class TestDisqualification:
    def test_requires_reason(self, opportunity: Opportunity) -> None:
        with pytest.raises(DomainError):
            opportunity.disqualify("  ")

    def test_disqualify_emits_event(self, opportunity: Opportunity) -> None:
        opportunity.disqualify("not an importer")
        assert opportunity.stage is OpportunityStage.DISQUALIFIED
        assert opportunity.stage_reason == "not an importer"
        events = opportunity.drain_events()
        assert any(isinstance(e, OpportunityDisqualified) for e in events)

    def test_cannot_disqualify_twice(self, opportunity: Opportunity) -> None:
        opportunity.disqualify("no volume")
        with pytest.raises(InvalidStateTransition):
            opportunity.disqualify("again")


class TestReopen:
    def test_reopen_restores_assessed_when_history_exists(self, opportunity: Opportunity) -> None:
        opportunity.apply_assessment(make_assessment(30.0))
        opportunity.disqualify("volume too low")
        opportunity.reopen("new shipment burst detected")
        assert opportunity.stage is OpportunityStage.ASSESSED
        assert opportunity.stage_reason is None

    def test_reopen_without_history_restores_identified(self, opportunity: Opportunity) -> None:
        opportunity.disqualify("bad fit")
        opportunity.reopen("re-targeting")
        assert opportunity.stage is OpportunityStage.IDENTIFIED

    def test_cannot_reopen_open_opportunity(self, opportunity: Opportunity) -> None:
        with pytest.raises(InvalidStateTransition):
            opportunity.reopen("why not")

    def test_reopen_requires_trigger(self, opportunity: Opportunity) -> None:
        opportunity.disqualify("bad fit")
        with pytest.raises(DomainError):
            opportunity.reopen("  ")
