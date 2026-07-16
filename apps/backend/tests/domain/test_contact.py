"""Contact value objects and aggregate: construction, transitions, events."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.contact import (
    Contact,
    ContactChannel,
    ContactChannelType,
    ContactStatus,
    ContactVerificationStatus,
    DecisionMakerFitAssessment,
    Department,
    JobTitle,
    PersonName,
    SeniorityLevel,
)
from app.domain.events import (
    ContactabilityChanged,
    ContactChannelAdded,
    ContactChannelVerified,
    ContactCreated,
    ContactInvalidated,
)
from app.domain.exceptions import (
    DomainError,
    DuplicateOperation,
    InvalidStateTransition,
    MissingEvidence,
)
from app.domain.values import Confidence, SourceReference

FIXED_AT = datetime(2026, 7, 1, tzinfo=UTC)


def make_source() -> SourceReference:
    return SourceReference(source="importyeti", reference="https://r/1", retrieved_at=FIXED_AT)


def make_channel(
    value: str = "maria@phg.com", channel_type: ContactChannelType = ContactChannelType.EMAIL
) -> ContactChannel:
    return ContactChannel(
        channel_type=channel_type,
        normalized_value=value,
        display_value=value,
        source_reference=make_source(),
    )


@pytest.fixture
def contact() -> Contact:
    return Contact.create_for_company(
        uuid4(), PersonName("Maria Chen"), JobTitle("Director of Supply Chain")
    )


class TestValueObjects:
    def test_person_name_normalizes_whitespace(self) -> None:
        assert PersonName("  Maria   Chen ").value == "Maria Chen"

    @pytest.mark.parametrize("raw", ["", "   ", "***", "-- --", "x" * 201])
    def test_person_name_invalid(self, raw: str) -> None:
        with pytest.raises(DomainError):
            PersonName(raw)

    def test_job_title_keeps_raw_and_normalizes(self) -> None:
        title = JobTitle("  Director,  Supply Chain ")
        assert title.raw == "Director, Supply Chain"
        assert title.normalized == "director, supply chain"

    def test_verified_channel_requires_verified_at(self) -> None:
        with pytest.raises(DomainError, match="verified_at"):
            ContactChannel(
                channel_type=ContactChannelType.EMAIL,
                normalized_value="a@b.com",
                display_value="a@b.com",
                source_reference=make_source(),
                verification_status=ContactVerificationStatus.SOURCE_VERIFIED,
            )

    def test_channel_confidence_range(self) -> None:
        with pytest.raises(DomainError):
            ContactChannel(
                channel_type=ContactChannelType.EMAIL,
                normalized_value="a@b.com",
                display_value="a@b.com",
                source_reference=make_source(),
                confidence=1.5,
            )

    def test_fit_assessment_validation_and_fingerprint(self) -> None:
        assessment = DecisionMakerFitAssessment(
            contact_id=uuid4(),
            company_id=uuid4(),
            role_fit_score=90.0,
            reachability_score=60.0,
            total_score=78.0,
            confidence=Confidence(0.7),
            department=Department.LOGISTICS,
            seniority=SeniorityLevel.DIRECTOR,
            reasons=("logistics director",),
            policy_version="mvp-decision-maker-policy-v1",
        )
        assert len(assessment.assessment_fingerprint) == 64
        with pytest.raises(DomainError):
            DecisionMakerFitAssessment(
                contact_id=uuid4(),
                company_id=uuid4(),
                role_fit_score=150.0,
                reachability_score=0.0,
                total_score=0.0,
                confidence=Confidence(0.5),
                department=Department.UNKNOWN,
                seniority=SeniorityLevel.UNKNOWN,
                reasons=("x",),
                policy_version="v",
            )
        with pytest.raises(MissingEvidence):
            DecisionMakerFitAssessment(
                contact_id=uuid4(),
                company_id=uuid4(),
                role_fit_score=50.0,
                reachability_score=50.0,
                total_score=50.0,
                confidence=Confidence(0.5),
                department=Department.UNKNOWN,
                seniority=SeniorityLevel.UNKNOWN,
                reasons=(),
                policy_version="v",
            )


class TestAggregate:
    def test_create_emits_event_and_holds_no_score(self, contact: Contact) -> None:
        events = contact.drain_events()
        assert any(isinstance(e, ContactCreated) for e in events)
        for forbidden in ("score", "priority", "opportunity_score"):
            assert not hasattr(contact, forbidden)

    def test_channel_dedup(self, contact: Contact) -> None:
        contact.add_channel(make_channel())
        with pytest.raises(DuplicateOperation):
            contact.add_channel(make_channel())

    def test_verify_channel_emits_events(self, contact: Contact) -> None:
        contact.add_channel(make_channel())
        contact.drain_events()
        contact.verify_channel(ContactChannelType.EMAIL, "maria@phg.com")
        events = contact.drain_events()
        assert any(isinstance(e, ContactChannelVerified) for e in events)
        assert any(isinstance(e, ContactabilityChanged) for e in events)
        assert contact.channels[0].verification_status is (
            ContactVerificationStatus.SOURCE_VERIFIED
        )

    def test_invalidated_channel_is_unusable_and_unverifiable(self, contact: Contact) -> None:
        contact.add_channel(make_channel())
        contact.invalidate_channel(ContactChannelType.EMAIL, "maria@phg.com", "hard bounce")
        assert contact.usable_channels == ()
        with pytest.raises(InvalidStateTransition):
            contact.verify_channel(ContactChannelType.EMAIL, "maria@phg.com")

    def test_activate_requires_substance(self) -> None:
        bare = Contact.create_for_company(uuid4(), PersonName("Nobody Known"))
        with pytest.raises(InvalidStateTransition):
            bare.activate()
        bare.add_channel(make_channel("nobody@x.com"))
        bare.activate()
        assert bare.status is ContactStatus.ACTIVE

    def test_activate_with_title_only(self, contact: Contact) -> None:
        contact.activate()  # has a title, no channels
        assert contact.status is ContactStatus.ACTIVE

    def test_mark_invalid_requires_reason_and_blocks_changes(self, contact: Contact) -> None:
        with pytest.raises(DomainError):
            contact.mark_invalid("  ")
        contact.mark_invalid("person left the company")
        assert contact.status is ContactStatus.INVALID
        assert any(isinstance(e, ContactInvalidated) for e in contact.drain_events())
        with pytest.raises(InvalidStateTransition):
            contact.update_title(JobTitle("New Role"))
        with pytest.raises(InvalidStateTransition):
            contact.activate()

    def test_deactivate_reactivate_cycle(self, contact: Contact) -> None:
        contact.activate()
        contact.deactivate()
        assert contact.status is ContactStatus.INACTIVE
        contact.reactivate()
        final_status: ContactStatus = contact.status  # widen past mypy narrowing
        assert final_status is ContactStatus.ACTIVE

    def test_events_peek_then_drain(self, contact: Contact) -> None:
        contact.add_channel(make_channel())
        peeked = contact.pending_events
        assert any(isinstance(e, ContactChannelAdded) for e in peeked)
        assert contact.pending_events == peeked  # peeking never clears
        assert contact.drain_events() == peeked
        assert contact.drain_events() == ()
