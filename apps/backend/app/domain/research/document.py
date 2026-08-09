"""Durable, immutable versions of cleaned research source content."""

from copy import deepcopy
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from app.domain.clock import ensure_utc
from app.domain.exceptions import DomainError, InvalidStateTransition

MAX_RESEARCH_DOCUMENT_CHARS = 40_000


class ResearchDocumentStatus(StrEnum):
    READY = "ready"
    QUARANTINED = "quarantined"
    SUPERSEDED = "superseded"


class ResearchDocumentTrustLevel(StrEnum):
    FIRST_PARTY = "first_party"
    AUTHORITATIVE = "authoritative"
    DERIVED_TRUSTED = "derived_trusted"
    UNVERIFIED = "unverified"


class ResearchDocumentSourceType(StrEnum):
    HOMEPAGE = "homepage"
    ABOUT = "about"
    PRODUCTS = "products"
    CAPABILITIES = "capabilities"
    CONTACT = "contact"
    NEWS = "news"
    PDF = "pdf"
    TRADE_EVIDENCE_SNAPSHOT = "trade_evidence_snapshot"
    WEBSITE_OTHER = "website_other"


def research_document_content_hash(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()


class ResearchDocument:
    """One immutable cleaned-content version with mutable lifecycle metadata."""

    def __init__(
        self,
        *,
        document_id: UUID,
        company_id: UUID,
        research_run_id: UUID,
        source_url: str,
        canonical_url: str,
        final_url: str,
        source_type: ResearchDocumentSourceType,
        title: str | None,
        content: str,
        content_hash: str,
        fetched_at: datetime,
        status: ResearchDocumentStatus,
        trust_level: ResearchDocumentTrustLevel,
        cleaner_version: str,
        supersedes_document_id: UUID | None,
        duplicate_of_document_id: UUID | None,
        is_current: bool,
        superseded_at: datetime | None,
        metadata: dict[str, Any],
    ) -> None:
        source_url = source_url.strip()
        canonical_url = canonical_url.strip()
        final_url = final_url.strip()
        content = content.strip()
        cleaner_version = cleaner_version.strip()
        if not source_url or not canonical_url or not final_url:
            raise DomainError("research document requires source, canonical and final URLs")
        if not content:
            raise DomainError("research document content must not be empty")
        if len(content) > MAX_RESEARCH_DOCUMENT_CHARS:
            raise DomainError(
                f"research document content exceeds {MAX_RESEARCH_DOCUMENT_CHARS} characters"
            )
        if research_document_content_hash(content) != content_hash:
            raise DomainError("research document content hash does not match content")
        if not cleaner_version:
            raise DomainError("research document requires a cleaner version")
        if supersedes_document_id == document_id or duplicate_of_document_id == document_id:
            raise DomainError("research document cannot reference itself")
        if status is ResearchDocumentStatus.SUPERSEDED:
            if is_current or superseded_at is None:
                raise DomainError("superseded research document lifecycle is inconsistent")
        elif not is_current or superseded_at is not None:
            raise DomainError("active research document lifecycle is inconsistent")

        self._id = document_id
        self._company_id = company_id
        self._research_run_id = research_run_id
        self._source_url = source_url
        self._canonical_url = canonical_url
        self._final_url = final_url
        self._source_type = source_type
        self._title = title.strip() if title and title.strip() else None
        self._content = content
        self._content_hash = content_hash
        self._fetched_at = ensure_utc(fetched_at, field="fetched_at")
        self._status = status
        self._trust_level = trust_level
        self._cleaner_version = cleaner_version
        self._supersedes_document_id = supersedes_document_id
        self._duplicate_of_document_id = duplicate_of_document_id
        self._is_current = is_current
        self._superseded_at = (
            ensure_utc(superseded_at, field="superseded_at") if superseded_at else None
        )
        self._metadata = deepcopy(metadata)

    @classmethod
    def create(
        cls,
        *,
        company_id: UUID,
        research_run_id: UUID,
        source_url: str,
        canonical_url: str,
        final_url: str,
        source_type: ResearchDocumentSourceType,
        title: str | None,
        content: str,
        fetched_at: datetime,
        status: ResearchDocumentStatus,
        trust_level: ResearchDocumentTrustLevel,
        cleaner_version: str,
        supersedes_document_id: UUID | None = None,
        duplicate_of_document_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ResearchDocument":
        if status is ResearchDocumentStatus.SUPERSEDED:
            raise DomainError("a new research document cannot start superseded")
        normalized_content = content.strip()
        return cls(
            document_id=uuid4(),
            company_id=company_id,
            research_run_id=research_run_id,
            source_url=source_url,
            canonical_url=canonical_url,
            final_url=final_url,
            source_type=source_type,
            title=title,
            content=normalized_content,
            content_hash=research_document_content_hash(normalized_content),
            fetched_at=fetched_at,
            status=status,
            trust_level=trust_level,
            cleaner_version=cleaner_version,
            supersedes_document_id=supersedes_document_id,
            duplicate_of_document_id=duplicate_of_document_id,
            is_current=True,
            superseded_at=None,
            metadata=metadata or {},
        )

    def supersede(self, *, at: datetime) -> None:
        if not self._is_current or self._status is ResearchDocumentStatus.SUPERSEDED:
            raise InvalidStateTransition("research document is already superseded")
        self._status = ResearchDocumentStatus.SUPERSEDED
        self._is_current = False
        self._superseded_at = ensure_utc(at, field="superseded_at")

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def company_id(self) -> UUID:
        return self._company_id

    @property
    def research_run_id(self) -> UUID:
        return self._research_run_id

    @property
    def source_url(self) -> str:
        return self._source_url

    @property
    def canonical_url(self) -> str:
        return self._canonical_url

    @property
    def final_url(self) -> str:
        return self._final_url

    @property
    def source_type(self) -> ResearchDocumentSourceType:
        return self._source_type

    @property
    def title(self) -> str | None:
        return self._title

    @property
    def content(self) -> str:
        return self._content

    @property
    def content_hash(self) -> str:
        return self._content_hash

    @property
    def fetched_at(self) -> datetime:
        return self._fetched_at

    @property
    def status(self) -> ResearchDocumentStatus:
        return self._status

    @property
    def trust_level(self) -> ResearchDocumentTrustLevel:
        return self._trust_level

    @property
    def cleaner_version(self) -> str:
        return self._cleaner_version

    @property
    def supersedes_document_id(self) -> UUID | None:
        return self._supersedes_document_id

    @property
    def duplicate_of_document_id(self) -> UUID | None:
        return self._duplicate_of_document_id

    @property
    def is_current(self) -> bool:
        return self._is_current

    @property
    def superseded_at(self) -> datetime | None:
        return self._superseded_at

    @property
    def metadata(self) -> dict[str, Any]:
        return deepcopy(self._metadata)
