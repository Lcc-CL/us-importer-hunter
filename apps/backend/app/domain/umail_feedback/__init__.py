"""Auditable offline Umail result import and engagement events."""

from app.domain.umail_feedback.models import (
    UMAIL_RESULT_MAPPING_VERSION,
    ContactEngagementEvent,
    ContactEngagementEventType,
    FeedbackExportSnapshot,
    UmailResultImport,
    UmailResultImportStatus,
    UmailResultMatchStatus,
    UmailResultRow,
)

__all__ = [
    "UMAIL_RESULT_MAPPING_VERSION",
    "ContactEngagementEvent",
    "ContactEngagementEventType",
    "FeedbackExportSnapshot",
    "UmailResultImport",
    "UmailResultImportStatus",
    "UmailResultMatchStatus",
    "UmailResultRow",
]
