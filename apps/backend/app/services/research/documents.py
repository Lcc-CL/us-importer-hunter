"""Deterministic ResearchDocument ingestion and immutable refresh policy."""

import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from app.domain.repositories import ResearchDocumentRepository
from app.domain.research import (
    ResearchDocument,
    ResearchDocumentSourceType,
    ResearchDocumentStatus,
    ResearchDocumentTrustLevel,
    ResearchPage,
    research_document_content_hash,
)
from app.tools.website import CLEANER_VERSION, CleanedPage

_TRACKING_PARAM = re.compile(r"^(utm_|gclid$|fbclid$|mc_|ref$)", re.IGNORECASE)


class DocumentIngestionAction(StrEnum):
    CREATED = "created"
    REUSED = "reused"
    VERSIONED = "versioned"
    SKIPPED_NO_COMPANY = "skipped_no_company"
    SKIPPED_EMPTY = "skipped_empty"


@dataclass(frozen=True)
class ResearchDocumentIngestionInput:
    company_id: UUID | None
    research_run_id: UUID
    page: ResearchPage
    cleaned: CleanedPage
    thin_page_chars: int


@dataclass(frozen=True)
class ResearchDocumentIngestionResult:
    action: DocumentIngestionAction
    document: ResearchDocument | None


def canonicalize_document_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"} or parts.hostname is None:
        raise ValueError("research document URL must be absolute HTTP(S)")
    if parts.username is not None or parts.password is not None:
        raise ValueError("research document URL must not contain user info")

    host = parts.hostname.encode("idna").decode("ascii").lower()
    if ":" in host:
        host = f"[{host}]"
    port = parts.port
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        host = f"{host}:{port}"

    path = parts.path.rstrip("/")
    query_pairs = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not _TRACKING_PARAM.match(key)
    )
    return urlunsplit((scheme, host, path, urlencode(query_pairs, doseq=True), ""))


class ResearchDocumentIngestionService:
    async def ingest(
        self,
        repository: ResearchDocumentRepository,
        payload: ResearchDocumentIngestionInput,
    ) -> ResearchDocumentIngestionResult:
        if payload.company_id is None:
            return ResearchDocumentIngestionResult(
                action=DocumentIngestionAction.SKIPPED_NO_COMPANY,
                document=None,
            )
        content = payload.cleaned.text.strip()
        if not content:
            return ResearchDocumentIngestionResult(
                action=DocumentIngestionAction.SKIPPED_EMPTY,
                document=None,
            )

        canonical_url = canonicalize_document_url(payload.page.final_url)
        content_hash = research_document_content_hash(content)
        status, quarantine_reasons = _document_status(payload)
        await repository.lock_ingestion_scope(payload.company_id, canonical_url, content_hash)

        current = await repository.get_current_for_url(
            payload.company_id, canonical_url, for_update=True
        )
        if current is not None and current.content_hash == content_hash:
            return ResearchDocumentIngestionResult(
                action=DocumentIngestionAction.REUSED,
                document=current,
            )

        duplicate = await repository.find_current_content_root(
            payload.company_id,
            content_hash,
            status,
            exclude_canonical_url=canonical_url,
        )
        if current is not None:
            current.supersede(at=payload.page.fetched_at)
            await repository.save(current)

        document = ResearchDocument.create(
            company_id=payload.company_id,
            research_run_id=payload.research_run_id,
            source_url=payload.page.url,
            canonical_url=canonical_url,
            final_url=payload.page.final_url,
            source_type=_source_type(payload.page.discovery_reason),
            title=payload.cleaned.title,
            content=content,
            fetched_at=payload.page.fetched_at,
            status=status,
            trust_level=ResearchDocumentTrustLevel.FIRST_PARTY,
            cleaner_version=CLEANER_VERSION,
            supersedes_document_id=current.id if current else None,
            duplicate_of_document_id=duplicate.id if duplicate else None,
            metadata={
                "content_type": payload.page.content_type,
                "content_chars": payload.page.content_chars,
                "bytes_read": payload.page.bytes_read,
                "truncated": payload.page.truncated,
                "discovery_reason": payload.page.discovery_reason,
                "meta_description": payload.cleaned.meta_description,
                "quarantine_reasons": quarantine_reasons,
            },
        )
        await repository.add(document)
        return ResearchDocumentIngestionResult(
            action=(
                DocumentIngestionAction.VERSIONED
                if current is not None
                else DocumentIngestionAction.CREATED
            ),
            document=document,
        )


def _document_status(
    payload: ResearchDocumentIngestionInput,
) -> tuple[ResearchDocumentStatus, list[str]]:
    reasons: list[str] = []
    if payload.cleaned.injection_hits:
        reasons.append("prompt_injection_pattern")
    if payload.cleaned.is_thin(payload.thin_page_chars):
        reasons.append("thin_content")
    return (
        ResearchDocumentStatus.QUARANTINED if reasons else ResearchDocumentStatus.READY,
        reasons,
    )


def _source_type(discovery_reason: str) -> ResearchDocumentSourceType:
    category = discovery_reason.removeprefix("ranked:")
    mapping = {
        "homepage": ResearchDocumentSourceType.HOMEPAGE,
        "about": ResearchDocumentSourceType.ABOUT,
        "products": ResearchDocumentSourceType.PRODUCTS,
        "capabilities": ResearchDocumentSourceType.CAPABILITIES,
        "contact": ResearchDocumentSourceType.CONTACT,
        "news": ResearchDocumentSourceType.NEWS,
    }
    return mapping.get(category, ResearchDocumentSourceType.WEBSITE_OTHER)
