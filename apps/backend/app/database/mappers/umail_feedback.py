"""Umail feedback domain ↔ persistence mapping."""

from app.database.models.umail_feedback import (
    ContactEngagementEventModel,
    UmailResultImportModel,
    UmailResultRowModel,
)
from app.domain.umail_feedback import (
    ContactEngagementEvent,
    ContactEngagementEventType,
    UmailResultImport,
    UmailResultImportStatus,
    UmailResultMatchStatus,
    UmailResultRow,
)


class UmailFeedbackMapper:
    @staticmethod
    def result_import_to_model(value: UmailResultImport) -> UmailResultImportModel:
        return UmailResultImportModel(
            id=value.id,
            source_filename=value.source_filename,
            file_sha256=value.file_sha256,
            mapping_version=value.mapping_version,
            mapping_snapshot_json=value.mapping_snapshot_json,
            status=value.status.value,
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
        )

    @staticmethod
    def result_import_to_domain(model: UmailResultImportModel) -> UmailResultImport:
        return UmailResultImport(
            id=model.id,
            source_filename=model.source_filename,
            file_sha256=model.file_sha256,
            mapping_version=model.mapping_version,
            mapping_snapshot_json=model.mapping_snapshot_json,
            status=UmailResultImportStatus(model.status),
            input_row_count=model.input_row_count,
            matched_count=model.matched_count,
            unmatched_count=model.unmatched_count,
            ambiguous_count=model.ambiguous_count,
            invalid_count=model.invalid_count,
            duplicate_count=model.duplicate_count,
            projected_event_count=model.projected_event_count,
            projected_suppression_count=model.projected_suppression_count,
            applied_event_count=model.applied_event_count,
            suppression_created_count=model.suppression_created_count,
            created_by=model.created_by,
            created_at=model.created_at,
            applied_at=model.applied_at,
            error_summary=model.error_summary,
        )

    @staticmethod
    def result_row_to_model(value: UmailResultRow) -> UmailResultRowModel:
        return UmailResultRowModel(
            id=value.id,
            result_import_id=value.result_import_id,
            row_number=value.row_number,
            raw_payload_json=value.raw_payload_json,
            export_batch_id=value.export_batch_id,
            export_row_id=value.export_row_id,
            normalized_email=value.normalized_email,
            campaign=value.campaign,
            canonical_event_type=(
                value.canonical_event_type.value if value.canonical_event_type else None
            ),
            occurred_at=value.occurred_at,
            bounce_type=value.bounce_type,
            message_id=value.message_id,
            match_status=value.match_status.value,
            matched_export_row_id=value.matched_export_row_id,
            match_method=value.match_method,
            error_codes_json=list(value.error_codes_json),
            row_fingerprint=value.row_fingerprint,
            created_at=value.created_at,
        )

    @staticmethod
    def result_row_to_domain(model: UmailResultRowModel) -> UmailResultRow:
        return UmailResultRow(
            id=model.id,
            result_import_id=model.result_import_id,
            row_number=model.row_number,
            raw_payload_json=model.raw_payload_json,
            export_batch_id=model.export_batch_id,
            export_row_id=model.export_row_id,
            normalized_email=model.normalized_email,
            campaign=model.campaign,
            canonical_event_type=(
                ContactEngagementEventType(model.canonical_event_type)
                if model.canonical_event_type
                else None
            ),
            occurred_at=model.occurred_at,
            bounce_type=model.bounce_type,
            message_id=model.message_id,
            match_status=UmailResultMatchStatus(model.match_status),
            matched_export_row_id=model.matched_export_row_id,
            match_method=model.match_method,
            error_codes_json=tuple(model.error_codes_json),
            row_fingerprint=model.row_fingerprint,
            created_at=model.created_at,
        )

    @staticmethod
    def event_to_model(value: ContactEngagementEvent) -> ContactEngagementEventModel:
        return ContactEngagementEventModel(
            id=value.id,
            result_import_id=value.result_import_id,
            result_row_id=value.result_row_id,
            export_batch_id=value.export_batch_id,
            export_row_id=value.export_row_id,
            company_id=value.company_id,
            contact_id=value.contact_id,
            event_type=value.event_type.value,
            occurred_at=value.occurred_at,
            campaign=value.campaign,
            provider=value.provider,
            event_fingerprint=value.event_fingerprint,
            metadata_json=value.metadata_json,
            created_at=value.created_at,
        )

    @staticmethod
    def event_to_domain(model: ContactEngagementEventModel) -> ContactEngagementEvent:
        return ContactEngagementEvent(
            id=model.id,
            result_import_id=model.result_import_id,
            result_row_id=model.result_row_id,
            export_batch_id=model.export_batch_id,
            export_row_id=model.export_row_id,
            company_id=model.company_id,
            contact_id=model.contact_id,
            event_type=ContactEngagementEventType(model.event_type),
            occurred_at=model.occurred_at,
            campaign=model.campaign,
            provider=model.provider,
            event_fingerprint=model.event_fingerprint,
            metadata_json=model.metadata_json,
            created_at=model.created_at,
        )
