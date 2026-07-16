"""ContactNormalizer: raw claims → validated values, honest rejections."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.contact import Department, RawContactSnapshot, SeniorityLevel
from app.domain.exceptions import DomainError
from app.domain.values import SourceReference
from app.services.contact import ContactNormalizer

SOURCE = SourceReference(
    source="importyeti", reference="https://r/1", retrieved_at=datetime(2026, 7, 1, tzinfo=UTC)
)


def snapshot(**overrides: object) -> RawContactSnapshot:
    defaults: dict[str, object] = {
        "company_id": uuid4(),
        "raw_name": "  Maria   Chen ",
        "raw_title": "Director of Supply Chain",
        "raw_email": " Maria.Chen@PHG.com ",
        "raw_linkedin_url": "www.linkedin.com/in/MariaChen",
        "raw_phone": "+1 (313) 555-0142",
        "source_reference": SOURCE,
    }
    defaults.update(overrides)
    return RawContactSnapshot(**defaults)  # type: ignore[arg-type]


class TestNormalization:
    def test_full_candidate(self) -> None:
        candidate = ContactNormalizer().normalize(snapshot())
        assert candidate.name.value == "Maria Chen"
        assert candidate.title is not None and candidate.title.normalized == (
            "director of supply chain"
        )
        assert candidate.department is Department.SUPPLY_CHAIN
        assert candidate.seniority is SeniorityLevel.DIRECTOR
        assert candidate.email is not None
        assert candidate.email.normalized_value == "maria.chen@phg.com"
        assert candidate.linkedin is not None
        assert candidate.linkedin.normalized_value == "https://www.linkedin.com/in/mariachen"
        assert candidate.phone is not None
        assert candidate.phone.normalized_value == "+13135550142"
        assert candidate.dropped_notes == ()

    @pytest.mark.parametrize(
        ("title", "department", "seniority"),
        [
            ("VP Logistics", Department.LOGISTICS, SeniorityLevel.VP),
            ("Purchasing Manager", Department.PROCUREMENT, SeniorityLevel.MANAGER),
            ("CEO", Department.EXECUTIVE, SeniorityLevel.C_LEVEL),
            ("Head of Operations", Department.OPERATIONS, SeniorityLevel.HEAD),
            ("Marketing Specialist", Department.SALES_MARKETING, SeniorityLevel.SPECIALIST),
            ("Chief Wizard", Department.OTHER, SeniorityLevel.C_LEVEL),
        ],
    )
    def test_role_classification(
        self, title: str, department: Department, seniority: SeniorityLevel
    ) -> None:
        candidate = ContactNormalizer().normalize(snapshot(raw_title=title))
        assert candidate.department is department
        assert candidate.seniority is seniority

    def test_missing_title_is_unknown_not_other(self) -> None:
        candidate = ContactNormalizer().normalize(snapshot(raw_title=None))
        assert candidate.title is None
        assert candidate.department is Department.UNKNOWN
        assert candidate.seniority is SeniorityLevel.UNKNOWN


class TestChannelDrops:
    def test_bad_email_dropped_with_note(self) -> None:
        candidate = ContactNormalizer().normalize(snapshot(raw_email="not-an-email"))
        assert candidate.email is None
        assert any("email dropped" in note for note in candidate.dropped_notes)

    def test_non_linkedin_url_dropped_with_note(self) -> None:
        candidate = ContactNormalizer().normalize(
            snapshot(raw_linkedin_url="https://facebook.com/maria")
        )
        assert candidate.linkedin is None
        assert any("linkedin url dropped" in note for note in candidate.dropped_notes)

    def test_short_phone_dropped_with_note(self) -> None:
        candidate = ContactNormalizer().normalize(snapshot(raw_phone="12345"))
        assert candidate.phone is None
        assert any("phone dropped" in note for note in candidate.dropped_notes)


class TestRejection:
    def test_symbols_only_name_rejects(self) -> None:
        with pytest.raises(DomainError):
            ContactNormalizer().normalize(snapshot(raw_name="@@@ ---"))
