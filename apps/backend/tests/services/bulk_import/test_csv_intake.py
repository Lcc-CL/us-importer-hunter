import codecs
import tempfile
from typing import BinaryIO, cast
from uuid import uuid4

import pytest

from app.domain.bulk_import import RawImportRow, RawImportRowStatus
from app.services.bulk_import import (
    MAX_CSV_BYTES,
    MAX_CSV_ROWS,
    BulkCsvValidationError,
    StreamingCsvIntake,
)


def binary_file(content: bytes) -> BinaryIO:
    file = tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b")
    file.write(content)
    file.seek(0)
    return cast(BinaryIO, file)


def rows_from(content: bytes) -> tuple[str, list[RawImportRow]]:
    parser = StreamingCsvIntake()
    with binary_file(content) as file:
        preflight = parser.preflight(file, mapping={})
        batches = parser.iter_batches(file, session_id=uuid4(), preflight=preflight)
        rows = [row for batch in batches for row in batch]
    return preflight.encoding, rows


def test_utf8_sig_csv_is_streamed_and_preserves_original_fields() -> None:
    content = codecs.BOM_UTF8 + "公司名称,联系人\n海港工具,王采购\n".encode()

    encoding, rows = rows_from(content)

    assert encoding == "utf-8-sig"
    assert len(rows) == 1
    assert rows[0].status is RawImportRowStatus.ACCEPTED
    assert rows[0].raw_payload["fields"] == {"公司名称": "海港工具", "联系人": "王采购"}


def test_gb18030_csv_is_streamed() -> None:
    content = "公司名称,联系人\n宁波五金,张经理\n".encode("gb18030")

    encoding, rows = rows_from(content)

    assert encoding == "gb18030"
    assert rows[0].raw_payload["fields"]["公司名称"] == "宁波五金"


def test_duplicate_and_invalid_rows_are_all_saved_and_classified() -> None:
    content = b"company,email\nAtlas,a@example.com\nAtlas,a@example.com\n\nMissingOnly\n"

    _encoding, rows = rows_from(content)

    assert [row.status for row in rows] == [
        RawImportRowStatus.ACCEPTED,
        RawImportRowStatus.DUPLICATE,
        RawImportRowStatus.INVALID,
        RawImportRowStatus.INVALID,
    ]
    assert rows[1].error_codes == ("duplicate_row",)
    assert rows[2].error_codes == ("empty_row", "column_count_mismatch")
    assert rows[3].error_codes == ("column_count_mismatch",)
    assert rows[1].row_hash == rows[0].row_hash


def test_mapping_is_explicit_and_missing_optional_logical_fields_are_allowed() -> None:
    parser = StreamingCsvIntake()
    with binary_file("公司,邮箱\nAtlas,a@example.com\n".encode()) as file:
        preflight = parser.preflight(
            file,
            mapping={"company_name": "公司", "contact_email": "邮箱"},
        )
    assert preflight.headers == ("公司", "邮箱")

    with binary_file(b"company\nAtlas\n") as file:
        with pytest.raises(BulkCsvValidationError) as caught:
            parser.preflight(file, mapping={"company_name": "missing"})
    assert caught.value.code == "bulk_import_mapping_invalid"


def test_empty_and_header_only_files_are_rejected_before_session_creation() -> None:
    parser = StreamingCsvIntake()
    for content in (b"", b"company,email\n"):
        with binary_file(content) as file:
            with pytest.raises(BulkCsvValidationError) as caught:
                parser.preflight(file, mapping={})
        assert caught.value.code == "bulk_import_csv_empty"


def test_file_size_limit_is_enforced_without_loading_content() -> None:
    parser = StreamingCsvIntake()
    with tempfile.TemporaryFile(mode="w+b") as file:
        file.truncate(MAX_CSV_BYTES + 1)
        file.seek(0)
        with pytest.raises(BulkCsvValidationError) as caught:
            parser.preflight(file, mapping={})
    assert caught.value.code == "bulk_import_file_too_large"


def test_row_limit_is_enforced_before_session_creation() -> None:
    parser = StreamingCsvIntake()
    with tempfile.TemporaryFile(mode="w+b") as file:
        file.write(b"company\n")
        for index in range(MAX_CSV_ROWS + 1):
            file.write(f"Company {index}\n".encode())
        file.seek(0)
        with pytest.raises(BulkCsvValidationError) as caught:
            parser.preflight(file, mapping={})
    assert caught.value.code == "bulk_import_too_many_rows"
