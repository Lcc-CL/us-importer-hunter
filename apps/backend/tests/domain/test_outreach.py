"""Outreach aggregate: approval gate, send rules, terminal states."""

import dataclasses
from uuid import uuid4

import pytest

from app.domain.events import (
    OpportunityLost,
    OpportunityWon,
    OutreachApproved,
    OutreachReplied,
    OutreachSent,
)
from app.domain.exceptions import (
    DomainError,
    DuplicateOperation,
    InvalidStateTransition,
)
from app.domain.outreach import Outreach, OutreachStatus


@pytest.fixture
def outreach() -> Outreach:
    return Outreach.create(opportunity_id=uuid4())


def drafted(outreach: Outreach) -> Outreach:
    outreach.attach_contact(uuid4())
    outreach.add_draft("Cutting your CNSHA-USLAX costs", "Hi Maria, ...", "sales-v1")
    return outreach


def sent(outreach: Outreach) -> Outreach:
    drafted(outreach)
    outreach.approve_draft(1)
    outreach.mark_sent()
    return outreach


class TestDrafts:
    def test_versions_increment(self, outreach: Outreach) -> None:
        drafted(outreach)
        outreach.add_draft("Second angle", "Hi again ...", "sales-v1")
        assert [d.version for d in outreach.drafts] == [1, 2]

    def test_draft_content_is_immutable(self, outreach: Outreach) -> None:
        draft = drafted(outreach).drafts[0]
        with pytest.raises(dataclasses.FrozenInstanceError):
            draft.body = "tampered"  # type: ignore[misc]

    def test_blank_draft_rejected(self, outreach: Outreach) -> None:
        with pytest.raises(DomainError):
            outreach.add_draft("  ", "body", "sales-v1")


class TestApproval:
    def test_cannot_approve_without_draft(self, outreach: Outreach) -> None:
        with pytest.raises(InvalidStateTransition):
            outreach.approve_draft(1)

    def test_approve_emits_event(self, outreach: Outreach) -> None:
        drafted(outreach)
        outreach.approve_draft(1)
        assert outreach.status is OutreachStatus.APPROVED
        assert any(isinstance(e, OutreachApproved) for e in outreach.drain_events())

    def test_approve_unknown_version_rejected(self, outreach: Outreach) -> None:
        drafted(outreach)
        with pytest.raises(DomainError):
            outreach.approve_draft(99)

    def test_cannot_change_contact_after_approval(self, outreach: Outreach) -> None:
        drafted(outreach)
        outreach.approve_draft(1)
        with pytest.raises(InvalidStateTransition):
            outreach.attach_contact(uuid4())


class TestSending:
    def test_cannot_send_unapproved(self, outreach: Outreach) -> None:
        drafted(outreach)
        with pytest.raises(InvalidStateTransition):
            outreach.mark_sent()

    def test_send_emits_event(self, outreach: Outreach) -> None:
        sent(outreach)
        assert outreach.status is OutreachStatus.SENT
        assert outreach.sent_version == 1
        assert any(isinstance(e, OutreachSent) for e in outreach.drain_events())

    def test_cannot_send_same_version_twice(self, outreach: Outreach) -> None:
        sent(outreach)
        with pytest.raises(DuplicateOperation):
            outreach.mark_sent()


class TestReply:
    def test_reply_requires_send(self, outreach: Outreach) -> None:
        drafted(outreach)
        with pytest.raises(InvalidStateTransition):
            outreach.record_reply("positive")

    def test_reply_stops_follow_up(self, outreach: Outreach) -> None:
        sent(outreach)
        assert outreach.follow_up_active is True
        outreach.record_reply("positive")
        assert outreach.status is OutreachStatus.REPLIED
        assert outreach.follow_up_active is False
        assert any(isinstance(e, OutreachReplied) for e in outreach.drain_events())


class TestTerminal:
    def test_won_emits_opportunity_won(self, outreach: Outreach) -> None:
        sent(outreach)
        outreach.record_reply("positive")
        outreach.mark_won("signed 20 TEU/year")
        events = outreach.drain_events()
        won = [e for e in events if isinstance(e, OpportunityWon)]
        assert len(won) == 1
        assert won[0].opportunity_id == outreach.opportunity_id

    def test_lost_emits_opportunity_lost(self, outreach: Outreach) -> None:
        sent(outreach)
        outreach.mark_lost("stayed with incumbent forwarder")
        assert any(isinstance(e, OpportunityLost) for e in outreach.drain_events())

    def test_terminal_blocks_everything(self, outreach: Outreach) -> None:
        sent(outreach)
        outreach.mark_won("signed")
        with pytest.raises(InvalidStateTransition):
            outreach.add_draft("more", "body", "sales-v1")
        with pytest.raises(InvalidStateTransition):
            outreach.mark_lost("changed mind")
        with pytest.raises(InvalidStateTransition):
            outreach.record_reply("late reply")

    def test_close_requires_reason(self, outreach: Outreach) -> None:
        sent(outreach)
        with pytest.raises(DomainError):
            outreach.mark_won("  ")

    def test_cannot_close_before_any_send(self, outreach: Outreach) -> None:
        drafted(outreach)
        with pytest.raises(InvalidStateTransition):
            outreach.mark_lost("gave up early")
