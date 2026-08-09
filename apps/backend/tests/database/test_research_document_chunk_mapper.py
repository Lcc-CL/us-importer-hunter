from datetime import UTC, datetime
from uuid import uuid4

from app.database.mappers import ResearchDocumentChunkMapper
from app.domain.research import (
    ResearchDocument,
    ResearchDocumentSourceType,
    ResearchDocumentStatus,
    ResearchDocumentTrustLevel,
)
from app.services.research import ChunkingConfig, DeterministicDocumentChunker


def test_research_document_chunk_mapper_round_trip() -> None:
    document = ResearchDocument.create(
        company_id=uuid4(),
        research_run_id=uuid4(),
        source_url="https://acme.example/about",
        canonical_url="https://acme.example/about",
        final_url="https://acme.example/about",
        source_type=ResearchDocumentSourceType.ABOUT,
        title="About",
        content="# About\nAcme imports industrial fasteners from China.",
        fetched_at=datetime(2026, 8, 9, tzinfo=UTC),
        status=ResearchDocumentStatus.READY,
        trust_level=ResearchDocumentTrustLevel.FIRST_PARTY,
        cleaner_version="website-cleaner-v1",
    )
    chunk = DeterministicDocumentChunker(ChunkingConfig(20, 30, 5)).chunk(
        document
    ).chunks[0]

    restored = ResearchDocumentChunkMapper.to_domain(
        ResearchDocumentChunkMapper.to_model(chunk)
    )

    assert restored.id == chunk.id
    assert restored.company_id == document.company_id
    assert restored.content == chunk.content
    assert restored.heading_path == chunk.heading_path
    assert restored.metadata == chunk.metadata
