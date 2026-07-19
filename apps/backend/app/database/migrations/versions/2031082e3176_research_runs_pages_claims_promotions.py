"""research runs, pages, claims, promotions (v0.2 research agent)

Four new tables. No existing table is altered — the research agent produces
claims for human review and never writes Company or Opportunity state
(ADR-0025).

Constraints worth noting, all verified by tests:
- research_claims.source_page_position is part of a COMPOSITE foreign key to
  (research_pages.research_id, position), so "the cited page belongs to this
  run" is a database invariant rather than only an application check. It is
  DEFERRABLE INITIALLY DEFERRED: the aggregate is written in a single flush
  with no row-level ordering between the pages and claims collections, so the
  check runs at COMMIT. The invariant is fully enforced either way.
- research_claims.kind is restricted to the eight canonical signal kinds.
- research_claims.confidence is constrained to 0..1.
- research_promotions.edited_detail must be present exactly when the decision
  is 'edited', and absent otherwise.
- research_promotions.company_id is deliberately NOT a foreign key: a run must
  survive company deletion as an audit record of what was proposed and
  reviewed.

Downgrade drops the four tables in dependency order (promotions → claims →
pages → runs) and is exercised in tests via upgrade → downgrade → upgrade.


Revision ID: 2031082e3176
Revises: 4a91c2e8b730
Create Date: 2026-07-18 21:37:34.772723

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '2031082e3176'
down_revision: str | None = '4a91c2e8b730'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('research_runs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('company_name', sa.String(length=200), nullable=False),
    sa.Column('website', sa.String(length=2048), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('failure_code', sa.String(length=30), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('pages_fetched', sa.Integer(), nullable=False),
    sa.Column('pages_failed', sa.Integer(), nullable=False),
    sa.Column('claims_extracted', sa.Integer(), nullable=False),
    sa.Column('claims_validated', sa.Integer(), nullable=False),
    sa.Column('extractor_provider', sa.String(length=50), nullable=True),
    sa.Column('extractor_model', sa.String(length=100), nullable=True),
    sa.Column('prompt_version', sa.String(length=50), nullable=True),
    sa.Column('profile_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('warnings_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.CheckConstraint("status IN ('created', 'running', 'completed', 'partial', 'failed')", name='ck_research_runs_status_controlled'),
    sa.CheckConstraint('claims_validated <= claims_extracted', name='ck_research_runs_validated_within_extracted'),
    sa.CheckConstraint('pages_fetched >= 0 AND pages_failed >= 0 AND claims_extracted >= 0 AND claims_validated >= 0', name='ck_research_runs_counters_non_negative'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_research_runs_status', 'research_runs', ['status'], unique=False)
    op.create_index('ix_research_runs_website', 'research_runs', ['website'], unique=False)
    op.create_table('research_pages',
    sa.Column('research_id', sa.Uuid(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('final_url', sa.Text(), nullable=False),
    sa.Column('http_status', sa.Integer(), nullable=False),
    sa.Column('content_type', sa.String(length=100), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('content_chars', sa.Integer(), nullable=False),
    sa.Column('bytes_read', sa.Integer(), nullable=False),
    sa.Column('truncated', sa.Boolean(), nullable=False),
    sa.Column('discovery_reason', sa.String(length=50), nullable=False),
    sa.CheckConstraint('content_chars >= 0 AND bytes_read >= 0', name='ck_research_pages_counters_non_negative'),
    sa.CheckConstraint('http_status BETWEEN 100 AND 599', name='ck_research_pages_http_status_range'),
    sa.CheckConstraint('position >= 0', name='ck_research_pages_position_non_negative'),
    sa.ForeignKeyConstraint(['research_id'], ['research_runs.id'], name='fk_research_pages_run', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('research_id', 'position')
    )
    op.create_table('research_claims',
    sa.Column('research_id', sa.Uuid(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('detail', sa.Text(), nullable=False),
    sa.Column('evidence_snippet', sa.Text(), nullable=False),
    sa.Column('source_page_position', sa.Integer(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.CheckConstraint("kind IN ('import_activity', 'china_dependency', 'shipping_fit', 'cargo_value_potential', 'company_scale', 'growth_signal', 'logistics_complexity', 'pain_point')", name='ck_research_claims_kind_controlled'),
    sa.CheckConstraint('confidence >= 0 AND confidence <= 1', name='ck_research_claims_confidence_range'),
    sa.CheckConstraint('length(trim(detail)) > 0', name='ck_research_claims_detail_not_empty'),
    sa.CheckConstraint('length(trim(evidence_snippet)) > 0', name='ck_research_claims_snippet_not_empty'),
    sa.ForeignKeyConstraint(['research_id', 'source_page_position'], ['research_pages.research_id', 'research_pages.position'], name='fk_research_claims_source_page', ondelete='CASCADE', initially='DEFERRED', deferrable=True),
    sa.ForeignKeyConstraint(['research_id'], ['research_runs.id'], name='fk_research_claims_run', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('research_id', 'position')
    )
    op.create_index('ix_research_claims_kind', 'research_claims', ['kind'], unique=False)
    op.create_table('research_promotions',
    sa.Column('research_id', sa.Uuid(), nullable=False),
    sa.Column('claim_position', sa.Integer(), nullable=False),
    sa.Column('decision', sa.String(length=20), nullable=False),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('reviewer_name', sa.String(length=200), nullable=True),
    sa.Column('edited_detail', sa.Text(), nullable=True),
    sa.Column('company_id', sa.Uuid(), nullable=True),
    sa.Column('company_signal_position', sa.Integer(), nullable=True),
    sa.CheckConstraint("(decision = 'edited' AND edited_detail IS NOT NULL AND length(trim(edited_detail)) > 0) OR (decision <> 'edited' AND edited_detail IS NULL)", name='ck_research_promotions_edited_detail_consistent'),
    sa.CheckConstraint("decision IN ('accepted', 'rejected', 'edited')", name='ck_research_promotions_decision_controlled'),
    sa.ForeignKeyConstraint(['research_id', 'claim_position'], ['research_claims.research_id', 'research_claims.position'], name='fk_research_promotions_claim', ondelete='CASCADE', initially='DEFERRED', deferrable=True),
    sa.ForeignKeyConstraint(['research_id'], ['research_runs.id'], name='fk_research_promotions_run', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('research_id', 'claim_position')
    )
    op.create_index('ix_research_promotions_company_id', 'research_promotions', ['company_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_research_promotions_company_id', table_name='research_promotions')
    op.drop_table('research_promotions')
    op.drop_index('ix_research_claims_kind', table_name='research_claims')
    op.drop_table('research_claims')
    op.drop_table('research_pages')
    op.drop_index('ix_research_runs_website', table_name='research_runs')
    op.drop_index('ix_research_runs_status', table_name='research_runs')
    op.drop_table('research_runs')
