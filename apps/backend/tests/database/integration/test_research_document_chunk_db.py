import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.uow import SqlAlchemyUnitOfWork
from app.domain.company import Company
from app.domain.exceptions import DuplicateOperation
from app.domain.research import (
    ResearchDocument,
    ResearchDocumentChunk,
    ResearchDocumentSourceType,
    ResearchDocumentStatus,
    ResearchDocumentTrustLevel,
    ResearchRun,
)
from app.domain.values import CompanyName, WebsiteUrl
from app.services.research import (
    ChunkingAction,
    ChunkingConfig,
    DeterministicDocumentChunker,
    ResearchDocumentChunkingService,
)
from tests.database.integration.conftest import UowFactory


def make_document(company_id: UUID, run_id: UUID) -> ResearchDocument:
    content = (
        "# About Acme\n"
        "Acme imports industrial fasteners from China every month.\n\n"
        "## Distribution\n"
        "The company operates warehouses in California and Texas."
    )
    return ResearchDocument.create(
        company_id=company_id,
        research_run_id=run_id,
        source_url="https://chunk-db.example/about",
        canonical_url="https://chunk-db.example/about",
        final_url="https://chunk-db.example/about",
        source_type=ResearchDocumentSourceType.ABOUT,
        title="About Acme",
        content=content,
        fetched_at=datetime(2026, 8, 9, tzinfo=UTC),
        status=ResearchDocumentStatus.READY,
        trust_level=ResearchDocumentTrustLevel.FIRST_PARTY,
        cleaner_version="website-cleaner-v1",
    )


async def seed_document(uow_factory: UowFactory) -> ResearchDocument:
    website = "https://chunk-db.example"
    company = Company.create(
        CompanyName(f"Chunk DB Company {uuid4()}"),
        WebsiteUrl(website),
    )
    run = ResearchRun.start(company.name.value, website, company_id=company.id)
    run.mark_running()
    run.complete()
    document = make_document(company.id, run.id)
    async with uow_factory() as uow:
        await uow.companies.add(company)
        await uow.research_runs.add(run)
        await uow.flush()
        await uow.research_documents.add(document)
        await uow.commit()
    return document


async def test_chunk_repository_create_read_and_idempotent_reuse(
    uow_factory: UowFactory,
) -> None:
    document = await seed_document(uow_factory)
    service = ResearchDocumentChunkingService(
        DeterministicDocumentChunker(ChunkingConfig(20, 30, 5))
    )
    async with uow_factory() as uow:
        created = await service.execute(uow.research_document_chunks, document)
        await uow.commit()
    async with uow_factory() as uow:
        reused = await service.execute(uow.research_document_chunks, document)
        await uow.commit()
    async with uow_factory() as uow:
        persisted = await uow.research_document_chunks.list_for_document(
            document.id, created.chunks[0].chunker_version
        )

    assert created.action is ChunkingAction.CREATED
    assert reused.action is ChunkingAction.REUSED
    assert [chunk.id for chunk in persisted] == [chunk.id for chunk in created.chunks]
    assert all(chunk.company_id == document.company_id for chunk in persisted)
    assert all(
        document.content[chunk.start_offset : chunk.end_offset] == chunk.content
        for chunk in persisted
    )


async def test_concurrent_chunking_creates_one_stable_sequence(test_db_url: str) -> None:
    engine = create_async_engine(test_db_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    def make_uow() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    document = await seed_document(make_uow)
    service = ResearchDocumentChunkingService(
        DeterministicDocumentChunker(ChunkingConfig(20, 30, 5))
    )

    async def persist() -> tuple[ChunkingAction, tuple[UUID, ...]]:
        async with make_uow() as uow:
            result = await service.execute(uow.research_document_chunks, document)
            await uow.commit()
        return result.action, tuple(chunk.id for chunk in result.chunks)

    try:
        first, second = await asyncio.gather(persist(), persist())
        async with make_uow() as uow:
            persisted = await uow.research_document_chunks.list_for_document(
                document.id, service.chunker.config.version
            )
        assert {first[0], second[0]} == {ChunkingAction.CREATED, ChunkingAction.REUSED}
        assert first[1] == second[1] == tuple(chunk.id for chunk in persisted)
        assert [chunk.chunk_index for chunk in persisted] == list(range(len(persisted)))
    finally:
        await engine.dispose()


async def test_historical_chunks_survive_parent_supersede(uow_factory: UowFactory) -> None:
    document = await seed_document(uow_factory)
    service = ResearchDocumentChunkingService()
    async with uow_factory() as uow:
        created = await service.execute(uow.research_document_chunks, document)
        await uow.commit()

    document.supersede(at=datetime(2026, 8, 9, 1, tzinfo=UTC))
    async with uow_factory() as uow:
        await uow.research_documents.save(document)
        skipped = await service.execute(uow.research_document_chunks, document)
        await uow.commit()
    async with uow_factory() as uow:
        persisted = await uow.research_document_chunks.list_for_document(
            document.id, created.chunks[0].chunker_version
        )

    assert skipped.action is ChunkingAction.SKIPPED_INELIGIBLE
    assert [chunk.id for chunk in persisted] == [chunk.id for chunk in created.chunks]


async def test_database_rejects_chunk_company_mismatch(uow_factory: UowFactory) -> None:
    document = await seed_document(uow_factory)
    valid = DeterministicDocumentChunker().chunk(document).chunks[0]
    mismatched = ResearchDocumentChunk(
        chunk_id=valid.id,
        document_id=valid.document_id,
        company_id=uuid4(),
        chunk_index=valid.chunk_index,
        content=valid.content,
        content_hash=valid.content_hash,
        token_count=valid.token_count,
        start_offset=valid.start_offset,
        end_offset=valid.end_offset,
        heading_path=valid.heading_path,
        metadata=valid.metadata,
        chunker_version=valid.chunker_version,
        tokenizer_profile=valid.tokenizer_profile,
        status=valid.status,
    )

    async with uow_factory() as uow:
        await uow.research_document_chunks.add_many((mismatched,))
        with pytest.raises(DuplicateOperation):
            await uow.commit()
