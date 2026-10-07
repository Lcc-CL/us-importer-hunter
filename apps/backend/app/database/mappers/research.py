"""ResearchRun aggregate ↔ persistence mapping."""

from dataclasses import asdict
from typing import Any

from app.database.models.research import (
    ResearchClaimModel,
    ResearchDocumentChunkModel,
    ResearchDocumentModel,
    ResearchPageModel,
    ResearchPromotionModel,
    ResearchRunModel,
)
from app.domain.research import (
    ClaimRejectionReason,
    ExtractorIdentity,
    OutputLanguage,
    PromotionDecision,
    RejectedClaim,
    ResearchClaim,
    ResearchDocument,
    ResearchDocumentChunk,
    ResearchDocumentChunkStatus,
    ResearchDocumentSourceType,
    ResearchDocumentStatus,
    ResearchDocumentTrustLevel,
    ResearchFailureCode,
    ResearchPage,
    ResearchProfile,
    ResearchPromotion,
    ResearchRun,
    ResearchRunStatus,
)


class ResearchDocumentChunkMapper:
    @staticmethod
    def to_model(chunk: ResearchDocumentChunk) -> ResearchDocumentChunkModel:
        return ResearchDocumentChunkModel(
            id=chunk.id,
            document_id=chunk.document_id,
            company_id=chunk.company_id,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            content_hash=chunk.content_hash,
            token_count=chunk.token_count,
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
            heading_path=list(chunk.heading_path),
            metadata_json=chunk.metadata,
            chunker_version=chunk.chunker_version,
            tokenizer_profile=chunk.tokenizer_profile,
            status=chunk.status.value,
        )

    @staticmethod
    def to_domain(model: ResearchDocumentChunkModel) -> ResearchDocumentChunk:
        return ResearchDocumentChunk(
            chunk_id=model.id,
            document_id=model.document_id,
            company_id=model.company_id,
            chunk_index=model.chunk_index,
            content=model.content,
            content_hash=model.content_hash,
            token_count=model.token_count,
            start_offset=model.start_offset,
            end_offset=model.end_offset,
            heading_path=tuple(model.heading_path),
            metadata=model.metadata_json or {},
            chunker_version=model.chunker_version,
            tokenizer_profile=model.tokenizer_profile,
            status=ResearchDocumentChunkStatus(model.status),
        )


class ResearchDocumentMapper:
    @staticmethod
    def to_model(document: ResearchDocument) -> ResearchDocumentModel:
        return ResearchDocumentModel(
            id=document.id,
            company_id=document.company_id,
            research_run_id=document.research_run_id,
            source_url=document.source_url,
            canonical_url=document.canonical_url,
            final_url=document.final_url,
            source_type=document.source_type.value,
            title=document.title,
            content=document.content,
            content_hash=document.content_hash,
            fetched_at=document.fetched_at,
            status=document.status.value,
            trust_level=document.trust_level.value,
            cleaner_version=document.cleaner_version,
            supersedes_document_id=document.supersedes_document_id,
            duplicate_of_document_id=document.duplicate_of_document_id,
            is_current=document.is_current,
            superseded_at=document.superseded_at,
            metadata_json=document.metadata,
        )

    @staticmethod
    def to_domain(model: ResearchDocumentModel) -> ResearchDocument:
        return ResearchDocument(
            document_id=model.id,
            company_id=model.company_id,
            research_run_id=model.research_run_id,
            source_url=model.source_url,
            canonical_url=model.canonical_url,
            final_url=model.final_url,
            source_type=ResearchDocumentSourceType(model.source_type),
            title=model.title,
            content=model.content,
            content_hash=model.content_hash,
            fetched_at=model.fetched_at,
            status=ResearchDocumentStatus(model.status),
            trust_level=ResearchDocumentTrustLevel(model.trust_level),
            cleaner_version=model.cleaner_version,
            supersedes_document_id=model.supersedes_document_id,
            duplicate_of_document_id=model.duplicate_of_document_id,
            is_current=model.is_current,
            superseded_at=model.superseded_at,
            metadata=model.metadata_json or {},
        )


class ResearchRunMapper:
    @staticmethod
    def to_model(run: ResearchRun) -> ResearchRunModel:
        extractor = run.extractor
        return ResearchRunModel(
            id=run.id,
            company_id=run.company_id,
            company_name=run.company_name,
            website=run.website,
            status=run.status.value,
            failure_code=run.failure_code.value if run.failure_code else None,
            started_at=run.started_at,
            completed_at=run.completed_at,
            pages_fetched=run.pages_fetched,
            pages_failed=run.pages_failed,
            claims_extracted=run.claims_extracted,
            claims_validated=run.claims_validated,
            extractor_provider=extractor.provider if extractor else None,
            extractor_model=extractor.model if extractor else None,
            prompt_version=extractor.prompt_version if extractor else None,
            profile_json=asdict(run.profile),
            warnings_json=list(run.warnings),
            unknown_dimensions_json=list(run.unknown_dimensions),
            output_language=run.output_language.value,
            rejected_json=[
                {
                    "reason": rejection.reason.value,
                    "kind": rejection.kind,
                    "detail": rejection.detail,
                    "warning": rejection.warning,
                }
                for rejection in run.rejected_claims
            ],
            pages=[
                ResearchPageModel(
                    research_id=run.id,
                    position=page.position,
                    url=page.url,
                    final_url=page.final_url,
                    http_status=page.http_status,
                    content_type=page.content_type,
                    fetched_at=page.fetched_at,
                    content_chars=page.content_chars,
                    bytes_read=page.bytes_read,
                    truncated=page.truncated,
                    discovery_reason=page.discovery_reason,
                    document_id=page.document_id,
                )
                for page in run.pages
            ],
            claims=[
                ResearchClaimModel(
                    research_id=run.id,
                    position=claim.position,
                    kind=claim.kind,
                    detail=claim.detail,
                    evidence_snippet=claim.evidence_snippet,
                    source_page_position=claim.source_page_position,
                    confidence=claim.confidence,
                )
                for claim in run.claims
            ],
            promotions=[
                ResearchPromotionModel(
                    research_id=run.id,
                    claim_position=promotion.claim_position,
                    decision=promotion.decision.value,
                    reviewed_at=promotion.reviewed_at,
                    reviewer_name=promotion.reviewer_name,
                    edited_detail=promotion.edited_detail,
                    edited_kind=promotion.edited_kind,
                    company_id=promotion.company_id,
                    company_source_position=promotion.company_source_position,
                    company_signal_position=promotion.company_signal_position,
                )
                for promotion in run.promotions
            ],
        )

    @staticmethod
    def to_domain(model: ResearchRunModel) -> ResearchRun:
        run = ResearchRun(
            id=model.id,
            company_id=model.company_id,
            company_name=model.company_name,
            website=model.website,
            started_at=model.started_at,
            output_language=OutputLanguage.parse(model.output_language),
        )
        run._status = ResearchRunStatus(model.status)
        run._failure_code = (
            ResearchFailureCode(model.failure_code) if model.failure_code else None
        )
        run._completed_at = model.completed_at
        run._pages_failed = model.pages_failed
        run._claims_extracted = model.claims_extracted
        run._warnings = list(model.warnings_json or [])
        run._unknown_dimensions = list(model.unknown_dimensions_json or [])
        run._rejected = [
            RejectedClaim(
                reason=ClaimRejectionReason(entry["reason"]),
                kind=entry["kind"],
                detail=entry["detail"],
                warning=entry["warning"],
            )
            for entry in (model.rejected_json or [])
        ]
        run._profile = _profile_from_json(model.profile_json or {})
        if model.extractor_provider and model.extractor_model and model.prompt_version:
            run._extractor = ExtractorIdentity(
                provider=model.extractor_provider,
                model=model.extractor_model,
                prompt_version=model.prompt_version,
            )
        run._pages = [
            ResearchPage(
                position=page.position,
                url=page.url,
                final_url=page.final_url,
                http_status=page.http_status,
                content_type=page.content_type,
                fetched_at=page.fetched_at,
                content_chars=page.content_chars,
                bytes_read=page.bytes_read,
                truncated=page.truncated,
                discovery_reason=page.discovery_reason,
                document_id=page.document_id,
            )
            for page in model.pages
        ]
        run._claims = [
            ResearchClaim(
                position=claim.position,
                kind=claim.kind,
                detail=claim.detail,
                evidence_snippet=claim.evidence_snippet,
                source_page_position=claim.source_page_position,
                confidence=claim.confidence,
            )
            for claim in model.claims
        ]
        run._promotions = [
            ResearchPromotion(
                claim_position=promotion.claim_position,
                decision=PromotionDecision(promotion.decision),
                reviewed_at=promotion.reviewed_at,
                reviewer_name=promotion.reviewer_name,
                edited_detail=promotion.edited_detail,
                edited_kind=promotion.edited_kind,
                company_id=promotion.company_id,
                company_source_position=promotion.company_source_position,
                company_signal_position=promotion.company_signal_position,
            )
            for promotion in model.promotions
        ]
        return run


def _profile_from_json(payload: dict[str, Any]) -> ResearchProfile:
    return ResearchProfile(
        summary=payload.get("summary"),
        industry=payload.get("industry"),
        products=tuple(payload.get("products") or ()),
        locations=tuple(payload.get("locations") or ()),
        size_hint=payload.get("size_hint"),
        year_founded=payload.get("year_founded"),
        mentions_importing=payload.get("mentions_importing"),
    )
