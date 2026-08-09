from datetime import UTC, datetime
from uuid import uuid4

from app.database.mappers import ResearchDocumentMapper
from app.domain.research import (
    ResearchDocument,
    ResearchDocumentSourceType,
    ResearchDocumentStatus,
    ResearchDocumentTrustLevel,
)


def test_research_document_mapper_round_trip_is_lossless() -> None:
    document = ResearchDocument.create(
        company_id=uuid4(),
        research_run_id=uuid4(),
        source_url="https://acme.example/about?utm_source=test",
        canonical_url="https://acme.example/about",
        final_url="https://acme.example/about",
        source_type=ResearchDocumentSourceType.ABOUT,
        title="About Acme",
        content="Acme imports tools from China every month.",
        fetched_at=datetime(2026, 8, 9, tzinfo=UTC),
        status=ResearchDocumentStatus.READY,
        trust_level=ResearchDocumentTrustLevel.FIRST_PARTY,
        cleaner_version="website-cleaner-v1",
        metadata={"truncated": False, "quarantine_reasons": []},
    )

    restored = ResearchDocumentMapper.to_domain(ResearchDocumentMapper.to_model(document))

    assert restored.id == document.id
    assert restored.company_id == document.company_id
    assert restored.research_run_id == document.research_run_id
    assert restored.source_url == document.source_url
    assert restored.canonical_url == document.canonical_url
    assert restored.final_url == document.final_url
    assert restored.content == document.content
    assert restored.content_hash == document.content_hash
    assert restored.status is document.status
    assert restored.metadata == document.metadata


def test_superseded_document_mapper_preserves_history() -> None:
    document = ResearchDocument.create(
        company_id=uuid4(),
        research_run_id=uuid4(),
        source_url="https://acme.example/about",
        canonical_url="https://acme.example/about",
        final_url="https://acme.example/about",
        source_type=ResearchDocumentSourceType.ABOUT,
        title=None,
        content="Historical content.",
        fetched_at=datetime(2026, 8, 9, tzinfo=UTC),
        status=ResearchDocumentStatus.QUARANTINED,
        trust_level=ResearchDocumentTrustLevel.FIRST_PARTY,
        cleaner_version="website-cleaner-v1",
    )
    document.supersede(at=datetime(2026, 8, 10, tzinfo=UTC))

    restored = ResearchDocumentMapper.to_domain(ResearchDocumentMapper.to_model(document))

    assert restored.status is ResearchDocumentStatus.SUPERSEDED
    assert restored.is_current is False
    assert restored.superseded_at == datetime(2026, 8, 10, tzinfo=UTC)
