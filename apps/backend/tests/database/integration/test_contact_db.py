"""Contact persistence against real PostgreSQL: round-trips, channel
lookups, append-only fit assessments, fingerprint uniqueness."""

from datetime import UTC, datetime

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
from app.domain.exceptions import DuplicateOperation
from app.domain.values import Confidence, SourceReference
from tests.database.integration.conftest import UowFactory
from tests.database.integration.test_repositories import persist_company

SOURCE = SourceReference(
    source="importyeti", reference="https://r/1", retrieved_at=datetime(2026, 7, 1, tzinfo=UTC)
)


async def persist_contact(uow_factory: UowFactory) -> Contact:
    company = await persist_company(uow_factory)
    contact = Contact.create_for_company(
        company.id, PersonName("Maria Chen"), JobTitle("Director of Supply Chain")
    )
    contact.classify_role(Department.SUPPLY_CHAIN, SeniorityLevel.DIRECTOR)
    contact.add_source(SOURCE)
    contact.add_channel(
        ContactChannel(
            channel_type=ContactChannelType.EMAIL,
            normalized_value="maria@phg.com",
            display_value="Maria@PHG.com",
            source_reference=SOURCE,
        )
    )
    contact.add_channel(
        ContactChannel(
            channel_type=ContactChannelType.LINKEDIN,
            normalized_value="https://www.linkedin.com/in/mariachen",
            display_value="linkedin.com/in/MariaChen",
            source_reference=SOURCE,
        )
    )
    contact.verify_channel(ContactChannelType.EMAIL, "maria@phg.com")
    contact.activate()
    contact.drain_events()
    async with uow_factory() as uow:
        await uow.contacts.add(contact)
        await uow.commit()
    return contact


class TestContactRoundTrip:
    async def test_full_round_trip(self, uow_factory: UowFactory) -> None:
        contact = await persist_contact(uow_factory)
        async with uow_factory() as uow:
            loaded = await uow.contacts.get_by_id(contact.id)
        assert loaded is not None
        assert loaded.name == contact.name
        assert loaded.title == contact.title
        assert loaded.department is Department.SUPPLY_CHAIN
        assert loaded.seniority is SeniorityLevel.DIRECTOR
        assert loaded.status is ContactStatus.ACTIVE
        # reload orders channels by normalized_value — compare as sets
        assert set(loaded.channels) == set(contact.channels)
        assert loaded.sources == contact.sources
        assert loaded.drain_events() == ()  # reload never revives events

    async def test_channel_lookups(self, uow_factory: UowFactory) -> None:
        contact = await persist_contact(uow_factory)
        assert contact.company_id is not None
        async with uow_factory() as uow:
            by_email = await uow.contacts.find_by_email(contact.company_id, "maria@phg.com")
            by_linkedin = await uow.contacts.find_by_linkedin_url(
                contact.company_id, "https://www.linkedin.com/in/mariachen"
            )
            missing = await uow.contacts.find_by_email(contact.company_id, "nobody@x.com")
        assert by_email is not None and by_email.id == contact.id
        assert by_linkedin is not None and by_linkedin.id == contact.id
        assert missing is None

    async def test_invalidated_channel_excluded_from_lookup(
        self, uow_factory: UowFactory
    ) -> None:
        contact = await persist_contact(uow_factory)
        assert contact.company_id is not None
        async with uow_factory() as uow:
            loaded = await uow.contacts.get_by_id(contact.id)
            assert loaded is not None
            loaded.invalidate_channel(ContactChannelType.EMAIL, "maria@phg.com", "hard bounce")
            loaded.drain_events()
            await uow.contacts.save(loaded)
            await uow.commit()
        async with uow_factory() as uow:
            assert await uow.contacts.find_by_email(contact.company_id, "maria@phg.com") is None
            reloaded = await uow.contacts.get_by_id(contact.id)
        assert reloaded is not None
        email = next(
            c for c in reloaded.channels if c.channel_type is ContactChannelType.EMAIL
        )
        assert email.verification_status is ContactVerificationStatus.INVALID


class TestFitAssessments:
    def make_assessment(self, contact: Contact, total: float = 80.0) -> DecisionMakerFitAssessment:
        assert contact.company_id is not None
        return DecisionMakerFitAssessment(
            contact_id=contact.id,
            company_id=contact.company_id,
            role_fit_score=90.0,
            reachability_score=60.0,
            total_score=total,
            confidence=Confidence(0.7),
            department=contact.department,
            seniority=contact.seniority,
            reasons=("supply chain director",),
            policy_version="mvp-decision-maker-policy-v1",
        )

    async def test_append_only_persistence(self, uow_factory: UowFactory) -> None:
        contact = await persist_contact(uow_factory)
        async with uow_factory() as uow:
            await uow.contacts.record_fit_assessment(self.make_assessment(contact, 80.0))
            await uow.contacts.record_fit_assessment(self.make_assessment(contact, 85.0))
            await uow.commit()

    async def test_duplicate_fingerprint_rejected_by_db(self, uow_factory: UowFactory) -> None:
        contact = await persist_contact(uow_factory)
        same = self.make_assessment(contact)
        async with uow_factory() as uow:
            await uow.contacts.record_fit_assessment(same)
            await uow.commit()
        async with uow_factory() as uow:
            await uow.contacts.record_fit_assessment(same)
            with pytest.raises(DuplicateOperation):
                await uow.commit()
