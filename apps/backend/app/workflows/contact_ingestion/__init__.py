"""Contact ingestion workflow: the candidate → Contact seam (ADR-0022)."""

from app.workflows.contact_ingestion.workflow import (
    ContactIngestionAction,
    ContactIngestionOutcome,
    ContactIngestionWorkflow,
)

__all__ = ["ContactIngestionAction", "ContactIngestionOutcome", "ContactIngestionWorkflow"]
