import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from app.domain.repositories import ResearchDocumentChunkRepository
from app.domain.research import (
    ResearchDocument,
    ResearchDocumentChunk,
    ResearchDocumentSourceType,
    ResearchDocumentStatus,
    ResearchDocumentTrustLevel,
    research_document_content_hash,
)
from app.services.research import (
    ChunkingAction,
    ChunkingConfig,
    DeterministicDocumentChunker,
    DeterministicLocalTokenizer,
    ResearchDocumentChunkingService,
    render_chunk_visualization,
)

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "rag" / "chunking_documents.v0.json"
R1_FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "rag" / "ingestion_sources.v0.json"
RELEVANCE_TEMPLATE_PATH = (
    Path(__file__).parents[4]
    / "docs"
    / "learning"
    / "experiments"
    / "L03-chunking-relevance-template.jsonl"
)


class InMemoryChunkRepository:
    def __init__(self) -> None:
        self.chunks: list[ResearchDocumentChunk] = []

    async def lock_chunking_scope(self, document_id: UUID, chunker_version: str) -> None:
        return None

    async def list_for_document(
        self, document_id: UUID, chunker_version: str
    ) -> list[ResearchDocumentChunk]:
        return sorted(
            (
                chunk
                for chunk in self.chunks
                if chunk.document_id == document_id
                and chunk.chunker_version == chunker_version
            ),
            key=lambda chunk: chunk.chunk_index,
        )

    async def add_many(self, chunks: tuple[ResearchDocumentChunk, ...]) -> None:
        self.chunks.extend(chunks)


def fixture_cases() -> list[dict[str, object]]:
    loaded = json.loads(FIXTURE_PATH.read_text())
    assert isinstance(loaded, list)
    return loaded


def fixture_content(case: dict[str, object]) -> str:
    if "content" in case:
        return str(case["content"])
    return str(case.get("prefix", "")) + str(case["repeat_sentence"]) * int(
        str(case["repeat_count"])
    )


def make_document(
    content: str,
    *,
    document_id: UUID | None = None,
    company_id: UUID | None = None,
    source_type: ResearchDocumentSourceType = ResearchDocumentSourceType.ABOUT,
    status: ResearchDocumentStatus = ResearchDocumentStatus.READY,
    duplicate_of_document_id: UUID | None = None,
) -> ResearchDocument:
    normalized_content = content.strip()
    return ResearchDocument(
        document_id=document_id or uuid4(),
        company_id=company_id or uuid4(),
        research_run_id=uuid4(),
        source_url="https://acme.example/source",
        canonical_url="https://acme.example/source",
        final_url="https://acme.example/source",
        source_type=source_type,
        title=None,
        content=normalized_content,
        content_hash=research_document_content_hash(normalized_content),
        fetched_at=datetime(2026, 8, 9, tzinfo=UTC),
        status=status,
        trust_level=ResearchDocumentTrustLevel.FIRST_PARTY,
        cleaner_version="website-cleaner-v1",
        supersedes_document_id=None,
        duplicate_of_document_id=duplicate_of_document_id,
        is_current=True,
        superseded_at=None,
        metadata={},
    )


def document_from_case(case_id: str) -> ResearchDocument:
    case = next(item for item in fixture_cases() if item["id"] == case_id)
    return make_document(
        fixture_content(case),
        document_id=UUID(str(case["document_id"])),
        company_id=UUID(str(case["company_id"])),
        source_type=ResearchDocumentSourceType(str(case["source_type"])),
    )


def test_fixture_manifests_cover_r1_and_required_chunking_cases() -> None:
    assert len(json.loads(R1_FIXTURE_PATH.read_text())) == 10
    assert {case["id"] for case in fixture_cases()} == {
        "homepage",
        "about-page",
        "product-page",
        "blog-news",
        "long-paragraph",
        "heading-list",
        "very-short-sections",
        "oversized-section",
        "repeated-footer-nav",
        "text-pdf-pages",
    }


def test_human_relevance_template_uses_real_stable_candidate_ids_without_labels() -> None:
    chunker = DeterministicDocumentChunker()
    candidate_ids_by_company: dict[str, set[str]] = {}
    for case in fixture_cases():
        plan = chunker.chunk(document_from_case(str(case["id"])))
        candidate_ids_by_company.setdefault(str(case["company"]), set()).update(
            str(chunk.id) for chunk in plan.chunks
        )
    rows = [
        json.loads(line)
        for line in RELEVANCE_TEMPLATE_PATH.read_text().splitlines()
        if line.strip()
    ]

    assert len(rows) == 10
    for row in rows:
        assert set(row["candidate_chunk_ids"]) <= candidate_ids_by_company[row["company"]]
        assert row["human_relevant_chunk_ids"] == []
        assert row["notes"] == ""


def test_local_tokenizer_has_a_recorded_deterministic_profile() -> None:
    tokenizer = DeterministicLocalTokenizer()

    assert tokenizer.profile == "unicode-lexical-v1"
    assert tokenizer.count("Acme imports bolts.") == 4
    assert tokenizer.count("进口商。") == 4


def test_chunking_is_deterministic_stable_and_offset_accurate() -> None:
    document = document_from_case("product-page")
    chunker = DeterministicDocumentChunker(ChunkingConfig(20, 30, 5))
    first = chunker.chunk(document)
    second = chunker.chunk(document)

    assert [chunk.id for chunk in first.chunks] == [chunk.id for chunk in second.chunks]
    assert [chunk.chunk_index for chunk in first.chunks] == list(range(len(first.chunks)))
    assert all(
        document.content[chunk.start_offset : chunk.end_offset] == chunk.content
        for chunk in first.chunks
    )
    assert any("Products" in chunk.heading_path for chunk in first.chunks)


def test_complete_short_sections_merge_without_overlap() -> None:
    plan = DeterministicDocumentChunker(ChunkingConfig(100, 120, 10)).chunk(
        document_from_case("very-short-sections")
    )

    assert len(plan.chunks) == 1
    assert plan.chunks[0].metadata["overlap_tokens"] == 0
    assert len(plan.chunks[0].metadata["merged_heading_paths"]) >= 2
    assert plan.metrics.overlap_ratio == 0.0


def test_oversized_section_uses_sentence_safe_bounded_overlap_and_hard_max() -> None:
    plan = DeterministicDocumentChunker(ChunkingConfig(40, 55, 8)).chunk(
        document_from_case("oversized-section")
    )

    assert len(plan.chunks) > 2
    assert max(chunk.token_count for chunk in plan.chunks) <= 55
    assert all(chunk.content.rstrip().endswith(".") for chunk in plan.chunks[1:-1])
    assert plan.chunks[0].metadata["overlap_tokens"] == 0
    assert any(int(chunk.metadata["overlap_tokens"]) > 0 for chunk in plan.chunks[1:])
    assert all(int(chunk.metadata["overlap_tokens"]) <= 8 for chunk in plan.chunks)
    assert plan.metrics.overlap_ratio > 0


def test_boilerplate_and_duplicate_lines_are_removed_with_metrics() -> None:
    plan = DeterministicDocumentChunker().chunk(document_from_case("repeated-footer-nav"))
    combined = "\n".join(chunk.content for chunk in plan.chunks).casefold()

    assert "request a quote" not in combined
    assert "all rights reserved" not in combined
    assert combined.count("product card: stainless bolts") == 1
    assert plan.metrics.boilerplate_ratio > 0
    assert plan.metrics.duplicate_ratio > 0


def test_pdf_page_boundaries_are_preserved() -> None:
    plan = DeterministicDocumentChunker(ChunkingConfig(30, 50, 5)).chunk(
        document_from_case("text-pdf-pages")
    )

    assert [chunk.metadata["page_number"] for chunk in plan.chunks] == [1, 2]
    assert all(chunk.metadata["section_type"] == "pdf_page" for chunk in plan.chunks)


def test_visualization_exposes_boundaries_and_quality_ratios() -> None:
    plan = DeterministicDocumentChunker(ChunkingConfig(40, 55, 8)).chunk(
        document_from_case("oversized-section")
    )
    rendered = render_chunk_visualization(plan)

    assert "chunk_index\theading\ttoken_count\tstart_offset\tend_offset\toverlap" in rendered
    assert "duplicate_ratio=" in rendered
    assert "boilerplate_ratio=" in rendered
    assert "overlap_ratio=" in rendered


def test_cross_company_documents_never_share_chunk_identity() -> None:
    content = "# About\nShared company profile content."
    first = DeterministicDocumentChunker().chunk(
        make_document(content, company_id=uuid4())
    )
    second = DeterministicDocumentChunker().chunk(
        make_document(content, company_id=uuid4())
    )

    assert first.chunks[0].id != second.chunks[0].id
    assert first.chunks[0].company_id != second.chunks[0].company_id


async def test_persistence_service_is_idempotent() -> None:
    repository: ResearchDocumentChunkRepository = InMemoryChunkRepository()
    service = ResearchDocumentChunkingService(
        DeterministicDocumentChunker(ChunkingConfig(30, 45, 5))
    )
    document = document_from_case("about-page")

    created = await service.execute(repository, document)
    reused = await service.execute(repository, document)

    assert created.action is ChunkingAction.CREATED
    assert reused.action is ChunkingAction.REUSED
    assert [chunk.id for chunk in created.chunks] == [chunk.id for chunk in reused.chunks]
    persisted = await repository.list_for_document(
        document.id, created.chunks[0].chunker_version
    )
    assert len(persisted) == len(created.chunks)


async def test_quarantined_superseded_and_duplicate_documents_do_not_chunk() -> None:
    repository = InMemoryChunkRepository()
    service = ResearchDocumentChunkingService()
    quarantined = make_document(
        "Unsafe content.", status=ResearchDocumentStatus.QUARANTINED
    )
    superseded = make_document("Historical content.")
    superseded.supersede(at=datetime(2026, 8, 9, 1, tzinfo=UTC))
    duplicate = make_document(
        "Duplicate content.", duplicate_of_document_id=uuid4()
    )

    assert (await service.execute(repository, quarantined)).action is (
        ChunkingAction.SKIPPED_INELIGIBLE
    )
    assert (await service.execute(repository, superseded)).action is (
        ChunkingAction.SKIPPED_INELIGIBLE
    )
    assert (await service.execute(repository, duplicate)).action is (
        ChunkingAction.SKIPPED_DUPLICATE
    )
    assert repository.chunks == []
