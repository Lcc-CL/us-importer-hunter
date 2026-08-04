"""Typed HTTP contracts for offline Umail result feedback."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel

from app.domain.umail_feedback import (
    ContactEngagementEventType,
    UmailResultImport,
    UmailResultImportStatus,
    UmailResultMatchStatus,
    UmailResultRow,
)
from app.workflows.umail_feedback import (
    UmailFeedbackStatistics,
    UmailResultApplyOutcome,
    UmailResultRowPage,
    UmailResultSubmission,
)


class UmailResultApplyRequest(BaseModel):
    confirmed: Literal[True]


class UmailResultImportResponse(BaseModel):
    result_import_id: UUID
    source_filename: str
    file_sha256: str
    mapping_version: str
    mapping_snapshot: dict[str, str]
    status: UmailResultImportStatus
    input_row_count: int
    matched_count: int
    unmatched_count: int
    ambiguous_count: int
    invalid_count: int
    duplicate_count: int
    projected_event_count: int
    projected_suppression_count: int
    applied_event_count: int
    suppression_created_count: int
    created_by: str
    created_at: datetime
    applied_at: datetime | None
    error_summary: str | None
    reused: bool
    system_sent_email: bool = False

    @classmethod
    def from_domain(cls, value: UmailResultImport, *, reused: bool) -> Self:
        return cls(
            result_import_id=value.id,
            source_filename=value.source_filename,
            file_sha256=value.file_sha256,
            mapping_version=value.mapping_version,
            mapping_snapshot=value.mapping_snapshot_json,
            status=value.status,
            input_row_count=value.input_row_count,
            matched_count=value.matched_count,
            unmatched_count=value.unmatched_count,
            ambiguous_count=value.ambiguous_count,
            invalid_count=value.invalid_count,
            duplicate_count=value.duplicate_count,
            projected_event_count=value.projected_event_count,
            projected_suppression_count=value.projected_suppression_count,
            applied_event_count=value.applied_event_count,
            suppression_created_count=value.suppression_created_count,
            created_by=value.created_by,
            created_at=value.created_at,
            applied_at=value.applied_at,
            error_summary=value.error_summary,
            reused=reused,
            system_sent_email=False,
        )

    @classmethod
    def from_submission(cls, value: UmailResultSubmission) -> Self:
        return cls.from_domain(value.result_import, reused=value.reused)

    @classmethod
    def from_apply(cls, value: UmailResultApplyOutcome) -> Self:
        return cls.from_domain(value.result_import, reused=value.reused)


class UmailResultRowResponse(BaseModel):
    result_row_id: UUID
    row_number: int
    export_batch_id: UUID | None
    export_row_id: UUID | None
    normalized_email: str | None
    campaign: str | None
    canonical_event_type: ContactEngagementEventType | None
    occurred_at: datetime | None
    bounce_type: str | None
    message_id: str | None
    match_status: UmailResultMatchStatus
    matched_export_row_id: UUID | None
    match_method: str | None
    error_codes: list[str]
    row_fingerprint: str
    suppression_impact: bool

    @classmethod
    def from_domain(cls, value: UmailResultRow) -> Self:
        return cls(
            result_row_id=value.id,
            row_number=value.row_number,
            export_batch_id=value.export_batch_id,
            export_row_id=value.export_row_id,
            normalized_email=value.normalized_email,
            campaign=value.campaign,
            canonical_event_type=value.canonical_event_type,
            occurred_at=value.occurred_at,
            bounce_type=value.bounce_type,
            message_id=value.message_id,
            match_status=value.match_status,
            matched_export_row_id=value.matched_export_row_id,
            match_method=value.match_method,
            error_codes=list(value.error_codes_json),
            row_fingerprint=value.row_fingerprint,
            suppression_impact=value.canonical_event_type
            in {
                ContactEngagementEventType.HARD_BOUNCED,
                ContactEngagementEventType.UNSUBSCRIBED,
                ContactEngagementEventType.COMPLAINED,
            },
        )


class UmailResultRowListResponse(BaseModel):
    result_import_id: UUID
    page: int
    limit: int
    total: int
    rows: list[UmailResultRowResponse]

    @classmethod
    def from_page(cls, result_import_id: UUID, page: UmailResultRowPage) -> Self:
        return cls(
            result_import_id=result_import_id,
            page=page.page,
            limit=page.limit,
            total=page.total,
            rows=[UmailResultRowResponse.from_domain(row) for row in page.rows],
        )


class EngagementRateStatisticsResponse(BaseModel):
    total_events: int
    event_counts: dict[str, int]
    delivered_rate: float
    reply_rate: float
    hard_bounce_rate: float
    unsubscribe_rate: float
    complaint_rate: float


class CompanyEngagementStatisticsResponse(BaseModel):
    company_id: UUID
    company_name: str
    event_counts: dict[str, int]


class UmailFeedbackStatisticsResponse(BaseModel):
    result_import_id: UUID
    total_result_rows: int
    matched_rate: float
    rates: EngagementRateStatisticsResponse
    campaign_statistics: dict[str, dict[str, int]]
    route_statistics: dict[str, dict[str, int]]
    company_statistics: list[CompanyEngagementStatisticsResponse]

    @classmethod
    def from_domain(cls, value: UmailFeedbackStatistics) -> Self:
        return cls(
            result_import_id=value.result_import_id,
            total_result_rows=value.total_result_rows,
            matched_rate=value.matched_rate,
            rates=EngagementRateStatisticsResponse(
                total_events=value.rates.total_events,
                event_counts=value.rates.event_counts,
                delivered_rate=value.rates.delivered_rate,
                reply_rate=value.rates.reply_rate,
                hard_bounce_rate=value.rates.hard_bounce_rate,
                unsubscribe_rate=value.rates.unsubscribe_rate,
                complaint_rate=value.rates.complaint_rate,
            ),
            campaign_statistics=value.campaign_statistics,
            route_statistics=value.route_statistics,
            company_statistics=[
                CompanyEngagementStatisticsResponse(
                    company_id=company.company_id,
                    company_name=company.company_name,
                    event_counts=company.event_counts,
                )
                for company in value.company_statistics
            ],
        )
