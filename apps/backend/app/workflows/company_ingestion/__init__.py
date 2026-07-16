"""Company ingestion workflow: the Discovery → Company seam (ADR-0019)."""

from app.workflows.company_ingestion.workflow import (
    CompanyIngestionWorkflow,
    IngestionOutcome,
    IngestionStatus,
)

__all__ = ["CompanyIngestionWorkflow", "IngestionOutcome", "IngestionStatus"]
