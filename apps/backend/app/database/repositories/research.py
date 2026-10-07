"""Research run and durable document repositories."""

from hashlib import sha256
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.mappers import (
    ResearchDocumentChunkMapper,
    ResearchDocumentMapper,
    ResearchRunMapper,
)
from app.database.models.research import (
    ResearchDocumentChunkModel,
    ResearchDocumentModel,
    ResearchPageModel,
    ResearchRunModel,
)
from app.domain.research import (
    ResearchDocument,
    ResearchDocumentChunk,
    ResearchDocumentStatus,
    ResearchRun,
)


def _advisory_lock_key(value: str) -> int:
    return int.from_bytes(sha256(value.encode("utf-8")).digest()[:8], "big", signed=True)


class SqlAlchemyResearchDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_ingestion_scope(
        self, company_id: UUID, canonical_url: str, content_hash: str
    ) -> None:
        lock_values = {
            f"research-document:url:{company_id}:{canonical_url}",
            f"research-document:content:{company_id}:{content_hash}",
        }
        for lock_key in sorted(_advisory_lock_key(value) for value in lock_values):
            await self._session.execute(select(func.pg_advisory_xact_lock(lock_key)))

    async def get_by_id(self, document_id: UUID) -> ResearchDocument | None:
        model = await self._session.get(ResearchDocumentModel, document_id)
        return ResearchDocumentMapper.to_domain(model) if model else None

    async def get_current_for_url(
        self, company_id: UUID, canonical_url: str, *, for_update: bool = False
    ) -> ResearchDocument | None:
        statement = select(ResearchDocumentModel).where(
            ResearchDocumentModel.company_id == company_id,
            ResearchDocumentModel.canonical_url == canonical_url,
            ResearchDocumentModel.is_current.is_(True),
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self._session.execute(statement)
        model = result.scalar_one_or_none()
        return ResearchDocumentMapper.to_domain(model) if model else None

    async def find_current_content_root(
        self,
        company_id: UUID,
        content_hash: str,
        status: ResearchDocumentStatus,
        *,
        exclude_canonical_url: str,
    ) -> ResearchDocument | None:
        result = await self._session.execute(
            select(ResearchDocumentModel)
            .where(
                ResearchDocumentModel.company_id == company_id,
                ResearchDocumentModel.content_hash == content_hash,
                ResearchDocumentModel.status == status.value,
                ResearchDocumentModel.is_current.is_(True),
                ResearchDocumentModel.duplicate_of_document_id.is_(None),
                ResearchDocumentModel.canonical_url != exclude_canonical_url,
            )
            .order_by(ResearchDocumentModel.fetched_at, ResearchDocumentModel.id)
            .limit(1)
        )
        model = result.scalar_one_or_none()
        return ResearchDocumentMapper.to_domain(model) if model else None

    async def add(self, document: ResearchDocument) -> None:
        self._session.add(ResearchDocumentMapper.to_model(document))

    async def save(self, document: ResearchDocument) -> None:
        await self._session.merge(ResearchDocumentMapper.to_model(document))

    async def list_for_company(self, company_id: UUID) -> list[ResearchDocument]:
        result = await self._session.execute(
            select(ResearchDocumentModel)
            .where(ResearchDocumentModel.company_id == company_id)
            .order_by(
                ResearchDocumentModel.canonical_url,
                ResearchDocumentModel.fetched_at,
                ResearchDocumentModel.id,
            )
        )
        return [ResearchDocumentMapper.to_domain(model) for model in result.scalars().all()]


class SqlAlchemyResearchDocumentChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_chunking_scope(self, document_id: UUID, chunker_version: str) -> None:
        lock_key = _advisory_lock_key(
            f"research-document-chunks:{document_id}:{chunker_version}"
        )
        await self._session.execute(select(func.pg_advisory_xact_lock(lock_key)))

    async def list_for_document(
        self, document_id: UUID, chunker_version: str
    ) -> list[ResearchDocumentChunk]:
        result = await self._session.execute(
            select(ResearchDocumentChunkModel)
            .where(
                ResearchDocumentChunkModel.document_id == document_id,
                ResearchDocumentChunkModel.chunker_version == chunker_version,
            )
            .order_by(ResearchDocumentChunkModel.chunk_index)
        )
        return [
            ResearchDocumentChunkMapper.to_domain(model) for model in result.scalars().all()
        ]

    async def add_many(self, chunks: tuple[ResearchDocumentChunk, ...]) -> None:
        self._session.add_all(
            [ResearchDocumentChunkMapper.to_model(chunk) for chunk in chunks]
        )


class SqlAlchemyResearchRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, research_id: UUID) -> ResearchRun | None:
        model = await self._session.get(ResearchRunModel, research_id)
        return ResearchRunMapper.to_domain(model) if model else None

    async def add(self, run: ResearchRun) -> None:
        self._session.add(ResearchRunMapper.to_model(run))

    async def save(self, run: ResearchRun) -> None:
        await self._session.merge(ResearchRunMapper.to_model(run))

    async def link_page_document(
        self, research_id: UUID, page_position: int, document_id: UUID
    ) -> None:
        await self._session.execute(
            update(ResearchPageModel)
            .where(
                ResearchPageModel.research_id == research_id,
                ResearchPageModel.position == page_position,
            )
            .values(document_id=document_id)
        )

    async def list_for_company(self, company_id: UUID, *, limit: int = 20) -> list[ResearchRun]:
        result = await self._session.execute(
            select(ResearchRunModel)
            .where(ResearchRunModel.company_id == company_id)
            .order_by(ResearchRunModel.started_at.desc())
            .limit(limit)
        )
        return [ResearchRunMapper.to_domain(model) for model in result.scalars().all()]

    async def list_for_website(self, website: str, *, limit: int = 10) -> list[ResearchRun]:
        result = await self._session.execute(
            select(ResearchRunModel)
            .where(ResearchRunModel.website == website)
            .order_by(ResearchRunModel.started_at.desc())
            .limit(limit)
        )
        return [ResearchRunMapper.to_domain(model) for model in result.scalars().all()]
