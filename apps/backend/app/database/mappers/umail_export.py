"""Umail export domain ↔ persistence mapping."""

from app.database.models.umail_export import (
    SuppressionEntryModel,
    UmailExportBatchModel,
    UmailExportRowModel,
)
from app.domain.prospect_routing import ProspectRouteReviewStatus, ProspectTier
from app.domain.umail_export import (
    SuppressionEntry,
    UmailExportBatch,
    UmailExportBatchStatus,
    UmailExportRow,
    UmailExportRowStatus,
)


class UmailExportMapper:
    @staticmethod
    def suppression_to_model(entry: SuppressionEntry) -> SuppressionEntryModel:
        return SuppressionEntryModel(
            id=entry.id,
            email=entry.email,
            domain=entry.domain,
            company=entry.company,
            active=entry.active,
            reason=entry.reason,
            source=entry.source,
            created_by=entry.created_by,
            deactivated_by=entry.deactivated_by,
            deactivated_at=entry.deactivated_at,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )

    @staticmethod
    def suppression_to_domain(model: SuppressionEntryModel) -> SuppressionEntry:
        return SuppressionEntry(
            id=model.id,
            email=model.email,
            domain=model.domain,
            company=model.company,
            active=model.active,
            reason=model.reason,
            source=model.source,
            created_by=model.created_by,
            deactivated_by=model.deactivated_by,
            deactivated_at=model.deactivated_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def batch_to_model(batch: UmailExportBatch) -> UmailExportBatchModel:
        return UmailExportBatchModel(
            id=batch.id,
            routing_run_id=batch.routing_run_id,
            execution_generation=batch.execution_generation,
            campaign=batch.campaign,
            mapping_version=batch.mapping_version,
            selection_hash=batch.selection_hash,
            status=batch.status.value,
            total_rows=batch.total_rows,
            ready_count=batch.ready_count,
            suppressed_count=batch.suppressed_count,
            invalid_count=batch.invalid_count,
            duplicate_count=batch.duplicate_count,
            content_sha256=batch.content_sha256,
            downloaded_at=batch.downloaded_at,
            created_at=batch.created_at,
            updated_at=batch.updated_at,
        )

    @staticmethod
    def batch_to_domain(model: UmailExportBatchModel) -> UmailExportBatch:
        return UmailExportBatch(
            id=model.id,
            routing_run_id=model.routing_run_id,
            execution_generation=model.execution_generation,
            campaign=model.campaign,
            mapping_version=model.mapping_version,
            selection_hash=model.selection_hash,
            status=UmailExportBatchStatus(model.status),
            total_rows=model.total_rows,
            ready_count=model.ready_count,
            suppressed_count=model.suppressed_count,
            invalid_count=model.invalid_count,
            duplicate_count=model.duplicate_count,
            content_sha256=model.content_sha256,
            downloaded_at=model.downloaded_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def row_to_model(row: UmailExportRow) -> UmailExportRowModel:
        return UmailExportRowModel(
            id=row.id,
            batch_id=row.batch_id,
            position=row.position,
            company_id=row.company_id,
            contact_id=row.contact_id,
            company_name=row.company_name,
            company_website=row.company_website,
            contact_name=row.contact_name,
            first_name=row.first_name,
            last_name=row.last_name,
            contact_title=row.contact_title,
            contact_role=row.contact_role,
            contact_seniority=row.contact_seniority,
            is_department_contact=row.is_department_contact,
            email=row.email,
            phone=row.phone,
            country=row.country,
            route=row.route.value,
            route_review_status=row.route_review_status.value,
            pre_score=row.pre_score,
            route_reasons=list(row.route_reasons),
            status=row.status.value,
            exclusion_reason=row.exclusion_reason,
            row_fingerprint=row.row_fingerprint,
            created_at=row.created_at,
        )

    @staticmethod
    def row_to_domain(model: UmailExportRowModel) -> UmailExportRow:
        return UmailExportRow(
            id=model.id,
            batch_id=model.batch_id,
            position=model.position,
            company_id=model.company_id,
            contact_id=model.contact_id,
            company_name=model.company_name,
            company_website=model.company_website,
            contact_name=model.contact_name,
            first_name=model.first_name,
            last_name=model.last_name,
            contact_title=model.contact_title,
            contact_role=model.contact_role,
            contact_seniority=model.contact_seniority,
            is_department_contact=model.is_department_contact,
            email=model.email,
            phone=model.phone,
            country=model.country,
            route=ProspectTier(model.route),
            route_review_status=ProspectRouteReviewStatus(model.route_review_status),
            pre_score=model.pre_score,
            route_reasons=tuple(model.route_reasons),
            status=UmailExportRowStatus(model.status),
            exclusion_reason=model.exclusion_reason,
            row_fingerprint=model.row_fingerprint,
            created_at=model.created_at,
        )
