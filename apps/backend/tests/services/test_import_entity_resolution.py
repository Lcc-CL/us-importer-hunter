"""Deterministic D5b1 company/contact resolution policy tests."""

from uuid import uuid4

import pytest

from app.domain.import_resolution import (
    CompanyResolutionCandidate,
    ContactIdentityCandidate,
    ImportEntityDecisionKind,
    ImportRoleCategory,
)
from app.services.import_resolution import (
    DeterministicEntityMatcher,
    ProjectedImportRow,
    RawImportProjector,
)

MAPPING = {
    "company_name": "company",
    "external_company_id": "external_id",
    "website": "website",
    "address": "address",
    "company_type": "company_type",
    "contact_name": "contact",
    "contact_email": "email",
    "contact_title": "title",
}


def project(**fields: str) -> ProjectedImportRow:
    return RawImportProjector().project(
        {"fields": fields},
        mapping=MAPPING,
    )


def company_candidate(
    *, name: str = "atlas hardware", domain: str | None = "atlas.example"
) -> CompanyResolutionCandidate:
    return CompanyResolutionCandidate(
        company_id=uuid4(),
        canonical_name="Atlas Hardware Inc",
        normalized_name=name,
        normalized_domain=domain,
        normalized_address="100 main st austin tx",
        company_type="importer",
        normalized_phone="12125550100",
    )


def test_external_id_and_domain_rules_are_deterministic() -> None:
    matcher = DeterministicEntityMatcher()
    candidate = company_candidate()
    projected = project(
        company="Renamed Atlas",
        external_id="EXT-1",
        website="different.example",
    )
    external = matcher.match_company(
        projected,
        source="netease_foreign_trade",
        external_identities={("netease_foreign_trade", "EXT-1"): candidate.company_id},
        companies={candidate.company_id: candidate},
    )
    assert external.decision is ImportEntityDecisionKind.AUTO_MERGE
    assert external.candidate_entity_id == candidate.company_id

    domain = matcher.match_company(
        project(company="Atlas Hardware LLC", website="https://atlas.example"),
        source="netease_foreign_trade",
        external_identities={},
        companies={candidate.company_id: candidate},
    )
    assert domain.decision is ImportEntityDecisionKind.AUTO_MERGE

    name_address = matcher.match_company(
        project(
            company="Atlas Hardware Inc",
            website="different.example",
            address="100 Main St Austin TX",
        ),
        source="netease_foreign_trade",
        external_identities={},
        companies={candidate.company_id: candidate},
    )
    assert name_address.decision is ImportEntityDecisionKind.AUTO_MERGE


def test_domain_conflict_and_name_only_require_review() -> None:
    matcher = DeterministicEntityMatcher()
    candidate = company_candidate()
    conflict = matcher.match_company(
        project(
            company="Unrelated Furniture Group",
            website="atlas.example",
            address="999 Other Rd Miami FL",
            company_type="warehouse",
        ),
        source="netease_foreign_trade",
        external_identities={},
        companies={candidate.company_id: candidate},
    )
    assert conflict.decision is ImportEntityDecisionKind.REVIEW_REQUIRED
    assert "company_name_conflict" in conflict.reason_codes
    assert "company_address_conflict" in conflict.reason_codes

    similar = matcher.match_company(
        project(company="Atlas Hardware LLC", website="different.example"),
        source="netease_foreign_trade",
        external_identities={},
        companies={candidate.company_id: candidate},
    )
    assert similar.decision is ImportEntityDecisionKind.REVIEW_REQUIRED


def test_contact_global_email_department_and_unassigned_rules() -> None:
    matcher = DeterministicEntityMatcher()
    contact_id = uuid4()
    candidate = ContactIdentityCandidate(
        contact_id=contact_id,
        display_name="Maria Chen",
        normalized_name="maria chen",
        normalized_title="director of supply chain",
        emails=("maria@example.com",),
        linkedin_urls=(),
        company_ids=(uuid4(),),
    )
    by_email = matcher.match_contact(
        project(contact="M. Chen", email="MARIA@example.com"),
        company_id=uuid4(),
        contacts={contact_id: candidate},
        email_index={"maria@example.com": contact_id},
        linkedin_index={},
    )
    assert by_email.decision is ImportEntityDecisionKind.AUTO_MERGE
    assert by_email.candidate_entity_id == contact_id

    department = project(email="procurement@example.com")
    assert department.is_department_contact is True
    assert department.contact_name == "Procurement Department"
    assert department.role_category is ImportRoleCategory.UNKNOWN

    mismatch = project(
        company="Atlas Hardware",
        website="atlas.example",
        contact="Outside Buyer",
        email="buyer@outside.example",
    )
    assert "email_domain_mismatch" in mismatch.projection_warnings

    unassigned = matcher.match_contact(
        project(contact="No Company Person", email="person@outside.example"),
        company_id=None,
        contacts={},
        email_index={},
        linkedin_index={},
    )
    assert unassigned.decision is ImportEntityDecisionKind.AUTO_CREATE
    assert "unassigned_contact" in unassigned.reason_codes


@pytest.mark.parametrize(
    "email",
    [
        "info@company.example",
        "sales@company.example",
        "support@company.example",
        "admin@company.example",
        "office@company.example",
        "hello@company.example",
    ],
)
def test_department_shared_mailboxes_are_flagged_retained_and_not_personified(
    email: str,
) -> None:
    projected = project(
        company="Atlas Hardware",
        website="atlas.example",
        contact="Support Desk",
        email=email,
        title="Manager",
    )
    assert projected.is_department_contact is True
    assert projected.contact_name == "Support Desk"  # retained, not deleted
    assert projected.role_category is ImportRoleCategory.UNKNOWN
