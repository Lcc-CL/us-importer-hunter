"""ResearchRun aggregate ↔ persistence mapping."""

from dataclasses import asdict
from typing import Any
from uuid import UUID

from app.database.models.research import (
    ResearchClaimModel,
    ResearchPageModel,
    ResearchPromotionModel,
    ResearchRunModel,
)
from app.domain.research import (
    ClaimRejectionReason,
    ExtractorIdentity,
    PromotionDecision,
    RejectedClaim,
    ResearchClaim,
    ResearchFailureCode,
    ResearchPage,
    ResearchProfile,
    ResearchPromotion,
    ResearchRun,
    ResearchRunStatus,
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
                    company_id=(
                        promotion.company_id
                        if isinstance(promotion.company_id, UUID)
                        else None
                    ),
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
        )
        run._status = ResearchRunStatus(model.status)
        run._failure_code = (
            ResearchFailureCode(model.failure_code) if model.failure_code else None
        )
        run._completed_at = model.completed_at
        run._pages_failed = model.pages_failed
        run._claims_extracted = model.claims_extracted
        run._warnings = list(model.warnings_json or [])
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
                company_id=promotion.company_id,
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
