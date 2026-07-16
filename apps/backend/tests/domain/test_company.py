"""Company aggregate: behaviors, invariants, events."""

import pytest

from app.domain.company import Company
from app.domain.events import CompanyVerified
from app.domain.exceptions import DomainError, DuplicateOperation, MissingEvidence
from app.domain.values import CompanyName, SourceReference, WebsiteUrl


@pytest.fixture
def company() -> Company:
    return Company.create(CompanyName("Pacific Home Goods Inc."), WebsiteUrl("https://phg.com"))


class TestCreate:
    def test_create(self, company: Company) -> None:
        assert company.name == CompanyName("Pacific Home Goods Inc.")
        assert company.verified is False
        assert company.created_at.tzinfo is not None
        assert company.drain_events() == ()

    def test_no_score_and_no_sales_state(self, company: Company) -> None:
        """Judgments live in Opportunity; conversations in Outreach."""
        for forbidden in ("score", "priority", "stage", "crm_status", "drafts"):
            assert not hasattr(company, forbidden)


class TestRename:
    def test_old_name_becomes_alias(self, company: Company) -> None:
        company.rename(CompanyName("PHG Incorporated"))
        assert company.name == CompanyName("PHG Incorporated")
        assert CompanyName("Pacific Home Goods Inc.") in company.aliases

    def test_rename_to_same_name_rejected(self, company: Company) -> None:
        with pytest.raises(DuplicateOperation):
            company.rename(CompanyName("pacific home goods inc."))


class TestAliases:
    def test_add_alias(self, company: Company) -> None:
        company.add_alias(CompanyName("PACIFIC HOME GOODS"))
        assert company.aliases == (CompanyName("PACIFIC HOME GOODS"),)

    def test_alias_cannot_duplicate_canonical_name(self, company: Company) -> None:
        with pytest.raises(DuplicateOperation):
            company.add_alias(CompanyName("PACIFIC HOME GOODS INC."))

    def test_alias_cannot_repeat(self, company: Company) -> None:
        company.add_alias(CompanyName("PHG"))
        with pytest.raises(DuplicateOperation):
            company.add_alias(CompanyName("phg"))


class TestVerification:
    def test_requires_source_reference(self, company: Company) -> None:
        with pytest.raises(MissingEvidence):
            company.mark_verified()

    def test_verify_with_source_emits_event(
        self, company: Company, source_ref: SourceReference
    ) -> None:
        company.add_source(source_ref)
        company.mark_verified()
        events = company.drain_events()
        assert len(events) == 1
        assert isinstance(events[0], CompanyVerified)
        assert events[0].company_id == company.id

    def test_double_verification_rejected(
        self, company: Company, source_ref: SourceReference
    ) -> None:
        company.add_source(source_ref)
        company.mark_verified()
        with pytest.raises(DuplicateOperation):
            company.mark_verified()


class TestSignals:
    def test_add_signal(self, company: Company) -> None:
        company.add_signal("volume growing 3 quarters straight")
        assert company.signals == ("volume growing 3 quarters straight",)

    def test_blank_signal_rejected(self, company: Company) -> None:
        with pytest.raises(DomainError):
            company.add_signal("   ")


class TestEvents:
    def test_drain_is_safe_to_repeat(self, company: Company, source_ref: SourceReference) -> None:
        company.add_source(source_ref)
        company.mark_verified()
        assert len(company.drain_events()) == 1
        assert company.drain_events() == ()
