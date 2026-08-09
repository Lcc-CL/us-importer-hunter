from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.exceptions import DomainError, InvalidStateTransition
from app.domain.research import (
    MAX_RESEARCH_DOCUMENT_CHARS,
    ResearchDocument,
    ResearchDocumentSourceType,
    ResearchDocumentStatus,
    ResearchDocumentTrustLevel,
)


def make_document(*, content: str = "Acme imports tools from China.") -> ResearchDocument:
    return ResearchDocument.create(
        company_id=uuid4(),
        research_run_id=uuid4(),
        source_url="https://acme.example/about",
        canonical_url="https://acme.example/about",
        final_url="https://acme.example/about",
        source_type=ResearchDocumentSourceType.ABOUT,
        title="About Acme",
        content=content,
        fetched_at=datetime(2026, 8, 9, tzinfo=UTC),
        status=ResearchDocumentStatus.READY,
        trust_level=ResearchDocumentTrustLevel.FIRST_PARTY,
        cleaner_version="website-cleaner-v1",
        metadata={"truncated": False},
    )


def test_document_starts_as_current_immutable_content_version() -> None:
    document = make_document()

    assert document.is_current is True
    assert document.status is ResearchDocumentStatus.READY
    assert len(document.content_hash) == 64
    assert document.superseded_at is None


def test_supersede_preserves_content_and_identity() -> None:
    document = make_document()
    original_id = document.id
    original_content = document.content

    document.supersede(at=datetime(2026, 8, 10, tzinfo=UTC))

    assert document.id == original_id
    assert document.content == original_content
    assert document.status is ResearchDocumentStatus.SUPERSEDED
    assert document.is_current is False
    assert document.superseded_at == datetime(2026, 8, 10, tzinfo=UTC)


def test_supersede_is_not_repeatable() -> None:
    document = make_document()
    document.supersede(at=datetime(2026, 8, 10, tzinfo=UTC))

    with pytest.raises(InvalidStateTransition, match="already superseded"):
        document.supersede(at=datetime(2026, 8, 11, tzinfo=UTC))


@pytest.mark.parametrize("content", ["", " ", "x" * (MAX_RESEARCH_DOCUMENT_CHARS + 1)])
def test_content_must_be_non_empty_and_within_hard_limit(content: str) -> None:
    with pytest.raises(DomainError):
        make_document(content=content)


def test_metadata_is_defensively_copied() -> None:
    document = make_document()
    metadata = document.metadata
    metadata["truncated"] = True

    assert document.metadata["truncated"] is False
