"""Stable retrieval units derived from immutable ResearchDocuments."""

from copy import deepcopy
from enum import StrEnum
from hashlib import sha256
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from app.domain.exceptions import DomainError
from app.domain.research.document import ResearchDocument


class ResearchDocumentChunkStatus(StrEnum):
    READY = "ready"


def research_document_chunk_content_hash(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()


def stable_research_document_chunk_id(
    *,
    document_id: UUID,
    chunker_version: str,
    start_offset: int,
    end_offset: int,
    content_hash: str,
) -> UUID:
    identity = ":".join(
        (
            "research-document-chunk",
            str(document_id),
            chunker_version,
            str(start_offset),
            str(end_offset),
            content_hash,
        )
    )
    return uuid5(NAMESPACE_URL, identity)


class ResearchDocumentChunk:
    def __init__(
        self,
        *,
        chunk_id: UUID,
        document_id: UUID,
        company_id: UUID,
        chunk_index: int,
        content: str,
        content_hash: str,
        token_count: int,
        start_offset: int,
        end_offset: int,
        heading_path: tuple[str, ...],
        metadata: dict[str, Any],
        chunker_version: str,
        tokenizer_profile: str,
        status: ResearchDocumentChunkStatus,
    ) -> None:
        chunker_version = chunker_version.strip()
        tokenizer_profile = tokenizer_profile.strip()
        if chunk_index < 0:
            raise DomainError("research document chunk index must be non-negative")
        if not content:
            raise DomainError("research document chunk content must not be empty")
        if research_document_chunk_content_hash(content) != content_hash:
            raise DomainError("research document chunk content hash does not match content")
        if token_count <= 0:
            raise DomainError("research document chunk token count must be positive")
        if start_offset < 0 or end_offset <= start_offset:
            raise DomainError("research document chunk offsets are invalid")
        if not chunker_version or not tokenizer_profile:
            raise DomainError("research document chunk requires versioned chunker and tokenizer")
        normalized_heading_path = tuple(
            heading.strip() for heading in heading_path if heading.strip()
        )
        expected_id = stable_research_document_chunk_id(
            document_id=document_id,
            chunker_version=chunker_version,
            start_offset=start_offset,
            end_offset=end_offset,
            content_hash=content_hash,
        )
        if chunk_id != expected_id:
            raise DomainError("research document chunk identity is not deterministic")

        self._id = chunk_id
        self._document_id = document_id
        self._company_id = company_id
        self._chunk_index = chunk_index
        self._content = content
        self._content_hash = content_hash
        self._token_count = token_count
        self._start_offset = start_offset
        self._end_offset = end_offset
        self._heading_path = normalized_heading_path
        self._metadata = deepcopy(metadata)
        self._chunker_version = chunker_version
        self._tokenizer_profile = tokenizer_profile
        self._status = status

    @classmethod
    def create(
        cls,
        *,
        document: ResearchDocument,
        chunk_index: int,
        content: str,
        token_count: int,
        start_offset: int,
        end_offset: int,
        heading_path: tuple[str, ...],
        metadata: dict[str, Any],
        chunker_version: str,
        tokenizer_profile: str,
    ) -> "ResearchDocumentChunk":
        if document.content[start_offset:end_offset] != content:
            raise DomainError("research document chunk offsets do not round-trip")
        content_hash = research_document_chunk_content_hash(content)
        return cls(
            chunk_id=stable_research_document_chunk_id(
                document_id=document.id,
                chunker_version=chunker_version,
                start_offset=start_offset,
                end_offset=end_offset,
                content_hash=content_hash,
            ),
            document_id=document.id,
            company_id=document.company_id,
            chunk_index=chunk_index,
            content=content,
            content_hash=content_hash,
            token_count=token_count,
            start_offset=start_offset,
            end_offset=end_offset,
            heading_path=heading_path,
            metadata=metadata,
            chunker_version=chunker_version,
            tokenizer_profile=tokenizer_profile,
            status=ResearchDocumentChunkStatus.READY,
        )

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def document_id(self) -> UUID:
        return self._document_id

    @property
    def company_id(self) -> UUID:
        return self._company_id

    @property
    def chunk_index(self) -> int:
        return self._chunk_index

    @property
    def content(self) -> str:
        return self._content

    @property
    def content_hash(self) -> str:
        return self._content_hash

    @property
    def token_count(self) -> int:
        return self._token_count

    @property
    def start_offset(self) -> int:
        return self._start_offset

    @property
    def end_offset(self) -> int:
        return self._end_offset

    @property
    def heading_path(self) -> tuple[str, ...]:
        return self._heading_path

    @property
    def metadata(self) -> dict[str, Any]:
        return deepcopy(self._metadata)

    @property
    def chunker_version(self) -> str:
        return self._chunker_version

    @property
    def tokenizer_profile(self) -> str:
        return self._tokenizer_profile

    @property
    def status(self) -> ResearchDocumentChunkStatus:
        return self._status
