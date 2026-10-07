from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.exceptions import DomainError
from app.domain.research import (
    ResearchDocument,
    ResearchDocumentChunk,
    ResearchDocumentSourceType,
    ResearchDocumentStatus,
    ResearchDocumentTrustLevel,
)


def document() -> ResearchDocument:
    return ResearchDocument.create(
        company_id=uuid4(),
        research_run_id=uuid4(),
        source_url="https://acme.example/about",
        canonical_url="https://acme.example/about",
        final_url="https://acme.example/about",
        source_type=ResearchDocumentSourceType.ABOUT,
        title="About",
        content="# About\nAcme imports industrial fasteners.",
        fetched_at=datetime(2026, 8, 9, tzinfo=UTC),
        status=ResearchDocumentStatus.READY,
        trust_level=ResearchDocumentTrustLevel.FIRST_PARTY,
        cleaner_version="website-cleaner-v1",
    )


def test_chunk_identity_is_stable_and_offsets_round_trip() -> None:
    parent = document()
    start = parent.content.index("Acme")
    content = parent.content[start:]
    first = ResearchDocumentChunk.create(
        document=parent,
        chunk_index=0,
        content=content,
        token_count=5,
        start_offset=start,
        end_offset=len(parent.content),
        heading_path=("About",),
        metadata={"section_type": "about_section"},
        chunker_version="structure-recursive-v1:test",
        tokenizer_profile="unicode-lexical-v1",
    )
    second = ResearchDocumentChunk.create(
        document=parent,
        chunk_index=0,
        content=content,
        token_count=5,
        start_offset=start,
        end_offset=len(parent.content),
        heading_path=("About",),
        metadata={"section_type": "about_section"},
        chunker_version="structure-recursive-v1:test",
        tokenizer_profile="unicode-lexical-v1",
    )

    assert first.id == second.id
    assert parent.content[first.start_offset : first.end_offset] == first.content
    assert first.company_id == parent.company_id


def test_chunk_rejects_non_roundtrip_offsets() -> None:
    parent = document()

    with pytest.raises(DomainError, match="offsets do not round-trip"):
        ResearchDocumentChunk.create(
            document=parent,
            chunk_index=0,
            content="different content",
            token_count=2,
            start_offset=0,
            end_offset=5,
            heading_path=(),
            metadata={},
            chunker_version="structure-recursive-v1:test",
            tokenizer_profile="unicode-lexical-v1",
        )
