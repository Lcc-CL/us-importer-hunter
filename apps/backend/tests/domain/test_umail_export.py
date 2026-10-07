"""Domain and CSV-contract tests for D5d2a."""

import codecs
import csv
import io
import json
from uuid import uuid4

import pytest

from app.domain.exceptions import DomainError
from app.domain.prospect_routing import ProspectRouteReviewStatus
from app.domain.umail_export import SuppressionEntry, UmailExportRow, UmailExportRowStatus
from app.workflows.umail_export import render_umail_csv


def test_suppression_requires_exactly_one_normalized_target() -> None:
    entry = SuppressionEntry.create(
        email=" Buyer@Example.COM ",
        domain=None,
        company=None,
        reason="manual opt out",
        source="manual",
        created_by="reviewer",
    )
    assert entry.email == "buyer@example.com"
    assert entry.active is True
    inactive = entry.deactivate(deactivated_by="reviewer")
    assert inactive.active is False
    assert inactive.deactivated_at is not None

    with pytest.raises(DomainError):
        SuppressionEntry.create(
            email="buyer@example.com",
            domain="example.com",
            company=None,
            reason="bad",
            source="manual",
            created_by="reviewer",
        )


def test_csv_contract_is_bom_utf8_stable_and_formula_safe() -> None:
    batch_id = uuid4()
    row = UmailExportRow.create(
        batch_id=batch_id,
        position=1,
        company_id=uuid4(),
        contact_id=uuid4(),
        company_name="=IMPORTXML(\"https://bad\")",
        company_website="https://example.com/a,b",
        contact_name="Buyer\nName",
        first_name="Buyer",
        last_name="Name",
        contact_title="Director",
        contact_role="procurement",
        contact_seniority="director",
        is_department_contact=False,
        email="buyer@example.com",
        phone=None,
        country=None,
        route_review_status=ProspectRouteReviewStatus.CONFIRMED,
        pre_score=72.5,
        route_reasons=("target_product_match", "usable_contact"),
        status=UmailExportRowStatus.READY,
        exclusion_reason=None,
    )
    first = render_umail_csv((row,), campaign="+Summer Campaign")
    second = render_umail_csv((row,), campaign="+Summer Campaign")
    decoded = first[len(codecs.BOM_UTF8) :].decode("utf-8")
    records = list(csv.DictReader(io.StringIO(decoded)))

    assert first.startswith(codecs.BOM_UTF8)
    assert first == second
    assert "'=IMPORTXML" in decoded
    assert "'+Summer Campaign" in decoded
    assert '"https://example.com/a,b"' in decoded
    assert records[0] == {
        "email": "buyer@example.com",
        "first_name": "Buyer",
        "last_name": "Name",
        "company": "'=IMPORTXML(\"https://bad\")",
        "job_title": "Director",
        "role": "procurement",
        "website": "https://example.com/a,b",
        "phone": "",
        "country": "",
        "prospect_score": "72.50",
        "route_reasons": json.dumps(
            ["target_product_match", "usable_contact"], separators=(",", ":")
        ),
        "campaign": "'+Summer Campaign",
        "export_batch_id": str(batch_id),
        "export_row_id": str(row.id),
    }
