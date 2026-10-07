"""add import entity resolution foundation

Revision ID: d5b1e2f3a4b5
Revises: d5a1c2d3e4f5
Create Date: 2026-08-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d5b1e2f3a4b5"
down_revision: str | None = "d5a1c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("contacts_company_id_fkey", "contacts", type_="foreignkey")
    op.alter_column("contacts", "company_id", existing_type=sa.Uuid(), nullable=True)
    op.create_foreign_key(
        "contacts_company_id_fkey",
        "contacts",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_index("uq_companies_normalized_name", table_name="companies")
    op.create_index(
        "ix_companies_normalized_name", "companies", ["normalized_name"], unique=False
    )

    op.create_table(
        "import_resolutions",
        sa.Column("import_session_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("processed_rows", sa.Integer(), nullable=False),
        sa.Column("companies_created", sa.Integer(), nullable=False),
        sa.Column("companies_reused", sa.Integer(), nullable=False),
        sa.Column("company_reviews_required", sa.Integer(), nullable=False),
        sa.Column("contacts_created", sa.Integer(), nullable=False),
        sa.Column("contacts_reused", sa.Integer(), nullable=False),
        sa.Column("company_contacts_created", sa.Integer(), nullable=False),
        sa.Column("invalid_rows", sa.Integer(), nullable=False),
        sa.Column("failed_rows", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','partial_failed','failed')",
            name="ck_import_resolutions_status",
        ),
        sa.CheckConstraint("total_rows >= 0", name="ck_import_resolutions_total_rows"),
        sa.CheckConstraint(
            "processed_rows >= 0", name="ck_import_resolutions_processed_rows"
        ),
        sa.CheckConstraint(
            "processed_rows <= total_rows", name="ck_import_resolutions_processed_lte"
        ),
        sa.CheckConstraint(
            "companies_created >= 0", name="ck_import_resolutions_companies_created"
        ),
        sa.CheckConstraint(
            "companies_reused >= 0", name="ck_import_resolutions_companies_reused"
        ),
        sa.CheckConstraint(
            "company_reviews_required >= 0", name="ck_import_resolutions_reviews"
        ),
        sa.CheckConstraint(
            "contacts_created >= 0", name="ck_import_resolutions_contacts_created"
        ),
        sa.CheckConstraint(
            "contacts_reused >= 0", name="ck_import_resolutions_contacts_reused"
        ),
        sa.CheckConstraint(
            "company_contacts_created >= 0", name="ck_import_resolutions_links_created"
        ),
        sa.CheckConstraint("invalid_rows >= 0", name="ck_import_resolutions_invalid_rows"),
        sa.CheckConstraint("failed_rows >= 0", name="ck_import_resolutions_failed_rows"),
        sa.ForeignKeyConstraint(
            ["import_session_id"], ["import_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("import_session_id"),
    )
    op.create_index(
        "ix_import_resolutions_status_updated",
        "import_resolutions",
        ["status", "updated_at"],
        unique=False,
    )

    op.create_table(
        "company_external_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "external_id", name="uq_company_external_identity"),
    )
    op.create_index(
        "ix_company_external_identities_company",
        "company_external_identities",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_company_external_identities_source_external",
        "company_external_identities",
        ["source", "external_id"],
        unique=False,
    )

    op.create_table(
        "company_resolution_profiles",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("normalized_name", sa.String(length=240), nullable=False),
        sa.Column("normalized_domain", sa.String(length=255), nullable=True),
        sa.Column("normalized_address", sa.Text(), nullable=True),
        sa.Column("company_type", sa.String(length=100), nullable=True),
        sa.Column("normalized_phone", sa.String(length=40), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_import_row_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_import_row_id"], ["raw_import_rows.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("company_id"),
    )
    op.create_index(
        "ix_company_resolution_profiles_domain",
        "company_resolution_profiles",
        ["normalized_domain"],
        unique=False,
    )
    op.create_index(
        "ix_company_resolution_profiles_name_address",
        "company_resolution_profiles",
        ["normalized_name", "normalized_address"],
        unique=False,
    )

    op.create_table(
        "company_contacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("raw_title", sa.Text(), nullable=True),
        sa.Column("role_category", sa.String(length=40), nullable=False),
        sa.Column("seniority", sa.String(length=20), nullable=False),
        sa.Column(
            "is_department_contact", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_import_row_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role_category IN ('owner_founder','executive','procurement','supply_chain',"
            "'logistics','operations','import_export','warehouse','sales',"
            "'general_department','irrelevant','unknown')",
            name="ck_company_contacts_role_category",
        ),
        sa.CheckConstraint(
            "seniority IN ('c_level','vp','director','head','manager','specialist','unknown')",
            name="ck_company_contacts_seniority",
        ),
        sa.CheckConstraint(
            "status IN ('active','inactive','unknown')",
            name="ck_company_contacts_status",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_import_row_id"], ["raw_import_rows.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "contact_id", name="uq_company_contacts_employment"),
    )
    op.create_index(
        "ix_company_contacts_company", "company_contacts", ["company_id"], unique=False
    )
    op.create_index(
        "ix_company_contacts_contact", "company_contacts", ["contact_id"], unique=False
    )
    op.create_index(
        "ix_company_contacts_role",
        "company_contacts",
        ["company_id", "role_category", "status"],
        unique=False,
    )
    op.execute(
        sa.text(
            """
            INSERT INTO company_contacts (
                id, company_id, contact_id, raw_title, role_category, seniority,
                is_department_contact, status, first_seen_at, last_seen_at,
                source_import_row_id, created_at, updated_at
            )
            SELECT
                md5('company-contact-' || c.id::text)::uuid,
                c.company_id,
                c.id,
                c.title_raw,
                CASE c.department
                    WHEN 'procurement' THEN 'procurement'
                    WHEN 'supply_chain' THEN 'supply_chain'
                    WHEN 'logistics' THEN 'logistics'
                    WHEN 'operations' THEN 'operations'
                    WHEN 'executive' THEN 'executive'
                    WHEN 'sales_marketing' THEN 'sales'
                    WHEN 'hr' THEN 'irrelevant'
                    ELSE 'unknown'
                END,
                c.seniority,
                false,
                CASE WHEN c.status = 'inactive' THEN 'inactive' ELSE 'active' END,
                c.created_at,
                c.updated_at,
                NULL,
                c.created_at,
                c.updated_at
            FROM contacts c
            WHERE c.company_id IS NOT NULL
            ON CONFLICT (company_id, contact_id) DO NOTHING
            """
        )
    )

    op.create_table(
        "import_entity_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_session_id", sa.Uuid(), nullable=False),
        sa.Column("raw_import_row_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("candidate_entity_id", sa.Uuid(), nullable=True),
        sa.Column("decision", sa.String(length=30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "reason_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("review_status", sa.String(length=20), nullable=False),
        sa.Column("reviewed_by", sa.String(length=160), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('company','contact')",
            name="ck_import_entity_decisions_entity_type",
        ),
        sa.CheckConstraint(
            "decision IN ('auto_create','auto_merge','review_required','manual_merge',"
            "'keep_separate','rejected')",
            name="ck_import_entity_decisions_decision",
        ),
        sa.CheckConstraint(
            "review_status IN ('not_required','pending','reviewed')",
            name="ck_import_entity_decisions_review_status",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_import_entity_decisions_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["import_session_id"], ["import_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["raw_import_row_id"], ["raw_import_rows.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "import_session_id",
            "raw_import_row_id",
            "entity_type",
            name="uq_import_entity_decisions_row_type",
        ),
    )
    op.create_index(
        "ix_import_entity_decisions_review",
        "import_entity_decisions",
        ["import_session_id", "review_status", "entity_type"],
        unique=False,
    )
    op.create_index(
        "ix_import_entity_decisions_candidate",
        "import_entity_decisions",
        ["candidate_entity_id"],
        unique=False,
    )

    op.create_table(
        "import_processing_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_session_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("business_key", sa.String(length=64), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(length=160), nullable=True),
        sa.Column("lease_acquired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("last_error_summary", sa.Text(), nullable=True),
        sa.Column("recovery_count", sa.Integer(), nullable=False),
        sa.Column("last_recovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','leased','running','completed','failed','cancelled')",
            name="ck_import_processing_jobs_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_import_processing_jobs_attempts"
        ),
        sa.CheckConstraint(
            "max_attempts > 0", name="ck_import_processing_jobs_max_attempts"
        ),
        sa.CheckConstraint(
            "recovery_count >= 0", name="ck_import_processing_jobs_recovery"
        ),
        sa.ForeignKeyConstraint(
            ["import_session_id"], ["import_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_import_processing_jobs_active_business",
        "import_processing_jobs",
        ["business_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending','leased','running')"),
    )
    op.create_index(
        "ix_import_processing_jobs_claim",
        "import_processing_jobs",
        ["status", "available_at", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_import_processing_jobs_session",
        "import_processing_jobs",
        ["import_session_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_import_processing_jobs_lease_expiry",
        "import_processing_jobs",
        ["lease_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_import_processing_jobs_lease_expiry", table_name="import_processing_jobs")
    op.drop_index("ix_import_processing_jobs_session", table_name="import_processing_jobs")
    op.drop_index("ix_import_processing_jobs_claim", table_name="import_processing_jobs")
    op.drop_index(
        "uq_import_processing_jobs_active_business", table_name="import_processing_jobs"
    )
    op.drop_table("import_processing_jobs")
    op.drop_index("ix_import_entity_decisions_candidate", table_name="import_entity_decisions")
    op.drop_index("ix_import_entity_decisions_review", table_name="import_entity_decisions")
    op.drop_table("import_entity_decisions")
    op.drop_index("ix_company_contacts_role", table_name="company_contacts")
    op.drop_index("ix_company_contacts_contact", table_name="company_contacts")
    op.drop_index("ix_company_contacts_company", table_name="company_contacts")

    op.execute(
        sa.text(
            """
            UPDATE contacts c
            SET company_id = (
                SELECT company_id
                FROM company_contacts
                WHERE contact_id = c.id
                ORDER BY first_seen_at, created_at
                LIMIT 1
            )
            WHERE c.company_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM contacts WHERE company_id IS NULL) THEN
                    RAISE EXCEPTION
                        'Cannot downgrade D5b1 while unassigned contacts exist; assign them first';
                END IF;
            END $$
            """
        )
    )
    op.drop_table("company_contacts")
    op.drop_index(
        "ix_company_resolution_profiles_name_address",
        table_name="company_resolution_profiles",
    )
    op.drop_index(
        "ix_company_resolution_profiles_domain", table_name="company_resolution_profiles"
    )
    op.drop_table("company_resolution_profiles")
    op.drop_index(
        "ix_company_external_identities_source_external",
        table_name="company_external_identities",
    )
    op.drop_index(
        "ix_company_external_identities_company", table_name="company_external_identities"
    )
    op.drop_table("company_external_identities")
    op.drop_index("ix_import_resolutions_status_updated", table_name="import_resolutions")
    op.drop_table("import_resolutions")

    op.drop_index("ix_companies_normalized_name", table_name="companies")
    op.create_index(
        "uq_companies_normalized_name", "companies", ["normalized_name"], unique=True
    )
    op.drop_constraint("contacts_company_id_fkey", "contacts", type_="foreignkey")
    op.alter_column("contacts", "company_id", existing_type=sa.Uuid(), nullable=False)
    op.create_foreign_key(
        "contacts_company_id_fkey",
        "contacts",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="CASCADE",
    )
