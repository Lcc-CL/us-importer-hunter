"""Email draft workflow: qualified opportunity + selected contact → draft."""

from app.workflows.email.workflow import (
    EmailDraftAction,
    EmailDraftGenerationWorkflow,
    EmailDraftOutcome,
)

__all__ = ["EmailDraftAction", "EmailDraftGenerationWorkflow", "EmailDraftOutcome"]
