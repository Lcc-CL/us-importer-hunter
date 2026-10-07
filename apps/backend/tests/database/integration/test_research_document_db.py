import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database.uow import SqlAlchemyUnitOfWork
from app.domain.company import Company
from app.domain.research import (
    ResearchDocument,
    ResearchDocumentSourceType,
    ResearchDocumentStatus,
    ResearchDocumentTrustLevel,
    ResearchPage,
    ResearchRun,
)
from app.domain.values import CompanyName, WebsiteUrl
from app.services.research import (
    ResearchDocumentIngestionInput,
    ResearchDocumentIngestionService,
)
from app.tools.website import clean_html
from tests.database.integration.conftest import UowFactory


async def seed_company_and_run(
    uow_factory: UowFactory,
    *,
    company_name: str = "Acme Research Documents",
    website: str = "https://acme-documents.example",
) -> tuple[UUID, UUID]:
    company = Company.create(CompanyName(company_name), WebsiteUrl(website))
    run = ResearchRun.start(company.name.value, website, company_id=company.id)
    run.mark_running()
    run.complete()
    async with uow_factory() as uow:
        await uow.companies.add(company)
        await uow.research_runs.add(run)
        await uow.commit()
    return company.id, run.id


async def seed_run_for_company(
    uow_factory: UowFactory,
    *,
    company_id: UUID,
    company_name: str,
    website: str,
) -> UUID:
    run = ResearchRun.start(company_name, website, company_id=company_id)
    run.mark_running()
    run.complete()
    async with uow_factory() as uow:
        await uow.research_runs.add(run)
        await uow.commit()
    return run.id


def make_document(company_id: UUID, run_id: UUID) -> ResearchDocument:
    return ResearchDocument.create(
        company_id=company_id,
        research_run_id=run_id,
        source_url="https://acme-documents.example/about",
        canonical_url="https://acme-documents.example/about",
        final_url="https://acme-documents.example/about",
        source_type=ResearchDocumentSourceType.ABOUT,
        title="About",
        content="Acme imports tools from China every month.",
        fetched_at=datetime(2026, 8, 9, tzinfo=UTC),
        status=ResearchDocumentStatus.READY,
        trust_level=ResearchDocumentTrustLevel.FIRST_PARTY,
        cleaner_version="website-cleaner-v1",
        metadata={"truncated": False},
    )


def ingestion_payload(
    company_id: UUID,
    run_id: UUID,
    *,
    url: str = "https://acme-documents.example/about",
    content: str = "Acme imports tools from China every month.",
) -> ResearchDocumentIngestionInput:
    html = f"<main><p>{content}</p></main>"
    cleaned = clean_html(html)
    return ResearchDocumentIngestionInput(
        company_id=company_id,
        research_run_id=run_id,
        page=ResearchPage(
            position=0,
            url=url,
            final_url=url,
            http_status=200,
            content_type="text/html",
            fetched_at=datetime(2026, 8, 9, tzinfo=UTC),
            content_chars=cleaned.char_count,
            bytes_read=len(html),
            discovery_reason="ranked:about",
        ),
        cleaned=cleaned,
        thin_page_chars=1,
    )


async def test_repository_create_read_and_list(uow_factory: UowFactory) -> None:
    company_id, run_id = await seed_company_and_run(uow_factory)
    document = make_document(company_id, run_id)
    async with uow_factory() as uow:
        await uow.research_documents.add(document)
        await uow.commit()

    async with uow_factory() as uow:
        restored = await uow.research_documents.get_by_id(document.id)
        listed = await uow.research_documents.list_for_company(company_id)

    assert restored is not None
    assert restored.content == document.content
    assert [item.id for item in listed] == [document.id]


async def test_ingestion_dedup_refresh_duplicate_and_history(uow_factory: UowFactory) -> None:
    company_id, first_run_id = await seed_company_and_run(uow_factory)
    second_run_id = await seed_run_for_company(
        uow_factory,
        company_id=company_id,
        company_name="Acme Research Documents",
        website="https://acme-documents.example",
    )
    service = ResearchDocumentIngestionService()
    async with uow_factory() as uow:
        first = await service.ingest(
            uow.research_documents, ingestion_payload(company_id, first_run_id)
        )
        await uow.commit()
    async with uow_factory() as uow:
        reused = await service.ingest(
            uow.research_documents, ingestion_payload(company_id, second_run_id)
        )
        await uow.commit()
    async with uow_factory() as uow:
        changed = await service.ingest(
            uow.research_documents,
            ingestion_payload(
                company_id,
                second_run_id,
                content="Acme now imports tools every week.",
            ),
        )
        await uow.commit()
    async with uow_factory() as uow:
        duplicate = await service.ingest(
            uow.research_documents,
            ingestion_payload(
                company_id,
                second_run_id,
                url="https://acme-documents.example/company",
                content="Acme now imports tools every week.",
            ),
        )
        await uow.commit()

    assert first.document is not None
    assert reused.document is not None and reused.document.id == first.document.id
    assert changed.document is not None
    assert changed.document.supersedes_document_id == first.document.id
    assert duplicate.document is not None
    assert duplicate.document.duplicate_of_document_id == changed.document.id

    async with uow_factory() as uow:
        documents = await uow.research_documents.list_for_company(company_id)
    current_about = [
        document
        for document in documents
        if document.canonical_url == "https://acme-documents.example/about"
        and document.is_current
    ]
    assert len(current_about) == 1
    assert len(documents) == 3
    assert any(document.status is ResearchDocumentStatus.SUPERSEDED for document in documents)


async def test_same_content_across_companies_is_not_linked(uow_factory: UowFactory) -> None:
    company_a, run_a = await seed_company_and_run(
        uow_factory, company_name="Company A Documents", website="https://company-a.example"
    )
    company_b, run_b = await seed_company_and_run(
        uow_factory, company_name="Company B Documents", website="https://company-b.example"
    )
    service = ResearchDocumentIngestionService()
    async with uow_factory() as uow:
        first = await service.ingest(
            uow.research_documents,
            ingestion_payload(
                company_a,
                run_a,
                url="https://company-a.example/about",
                content="Identical cleaned content.",
            ),
        )
        second = await service.ingest(
            uow.research_documents,
            ingestion_payload(
                company_b,
                run_b,
                url="https://company-b.example/about",
                content="Identical cleaned content.",
            ),
        )
        await uow.commit()

    assert first.document is not None and second.document is not None
    assert first.document.id != second.document.id
    assert second.document.duplicate_of_document_id is None


async def test_concurrent_same_url_same_content_creates_one_current_document(
    test_db_url: str,
) -> None:
    engine = create_async_engine(test_db_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    def make_uow() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    company_id, run_a = await seed_company_and_run(make_uow)
    company_name = "Concurrent Document Company"
    run_b_domain = ResearchRun.start(
        company_name,
        "https://acme-documents.example",
        company_id=company_id,
    )
    run_b_domain.mark_running()
    run_b_domain.complete()
    async with make_uow() as uow:
        await uow.research_runs.add(run_b_domain)
        await uow.commit()
    run_b = run_b_domain.id

    service = ResearchDocumentIngestionService()

    async def ingest(run_id: UUID) -> UUID:
        async with make_uow() as uow:
            result = await service.ingest(
                uow.research_documents,
                ingestion_payload(company_id, run_id),
            )
            await uow.commit()
        assert result.document is not None
        return result.document.id

    try:
        document_ids = await asyncio.gather(ingest(run_a), ingest(run_b))
        async with make_uow() as uow:
            documents = await uow.research_documents.list_for_company(company_id)
        current = [document for document in documents if document.is_current]
        assert len(current) == 1
        assert len(documents) == 1
        assert document_ids[0] == document_ids[1] == current[0].id
    finally:
        await engine.dispose()
