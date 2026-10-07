"""ImportSession and RawImportRow domain ↔ persistence mapping."""

from app.database.models.bulk_import import ImportSessionModel, RawImportRowModel
from app.domain.bulk_import import (
    ImportSession,
    ImportSessionStatus,
    RawImportRow,
    RawImportRowStatus,
)


class BulkImportMapper:
    @staticmethod
    def session_to_model(session: ImportSession) -> ImportSessionModel:
        return ImportSessionModel(
            id=session.id,
            source=session.source,
            original_filename=session.original_filename,
            file_type=session.file_type,
            file_size_bytes=session.file_size_bytes,
            file_sha256=session.file_sha256,
            mapping_json=session.mapping_json,
            encoding=session.encoding,
            status=session.status.value,
            total_rows=session.total_rows,
            accepted_rows=session.accepted_rows,
            invalid_rows=session.invalid_rows,
            duplicate_rows=session.duplicate_rows,
            started_at=session.started_at,
            completed_at=session.completed_at,
            error_summary=session.error_summary,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

    @staticmethod
    def session_to_domain(model: ImportSessionModel) -> ImportSession:
        return ImportSession(
            id=model.id,
            source=model.source,
            original_filename=model.original_filename,
            file_type=model.file_type,
            file_size_bytes=model.file_size_bytes,
            file_sha256=model.file_sha256,
            mapping_json=model.mapping_json,
            encoding=model.encoding,
            status=ImportSessionStatus(model.status),
            total_rows=model.total_rows,
            accepted_rows=model.accepted_rows,
            invalid_rows=model.invalid_rows,
            duplicate_rows=model.duplicate_rows,
            started_at=model.started_at,
            completed_at=model.completed_at,
            error_summary=model.error_summary,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def row_to_model(row: RawImportRow) -> RawImportRowModel:
        return RawImportRowModel(
            id=row.id,
            import_session_id=row.import_session_id,
            row_number=row.row_number,
            raw_payload=row.raw_payload,
            row_hash=row.row_hash,
            status=row.status.value,
            error_codes=list(row.error_codes),
            created_at=row.created_at,
        )

    @staticmethod
    def row_to_domain(model: RawImportRowModel) -> RawImportRow:
        return RawImportRow(
            id=model.id,
            import_session_id=model.import_session_id,
            row_number=model.row_number,
            raw_payload=model.raw_payload,
            row_hash=model.row_hash,
            status=RawImportRowStatus(model.status),
            error_codes=tuple(model.error_codes),
            created_at=model.created_at,
        )
