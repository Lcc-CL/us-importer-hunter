"""Outreach domain (Outreach context): the pursuit conversation aggregate."""

from app.domain.outreach.aggregate import (
    TERMINAL_STATUSES,
    EmailDraft,
    Outcome,
    OutcomeKind,
    Outreach,
    OutreachStatus,
)

__all__ = [
    "TERMINAL_STATUSES",
    "EmailDraft",
    "Outcome",
    "OutcomeKind",
    "Outreach",
    "OutreachStatus",
]
