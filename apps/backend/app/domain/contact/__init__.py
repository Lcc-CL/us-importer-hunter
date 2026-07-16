"""Contact domain (Outreach context): independent aggregate root (ADR-0022)."""

from app.domain.contact.aggregate import Contact
from app.domain.contact.values import (
    ContactChannel,
    ContactChannelType,
    ContactMatch,
    ContactMatchKind,
    ContactStatus,
    ContactVerificationStatus,
    DecisionMakerFitAssessment,
    Department,
    JobTitle,
    PersonName,
    RawContactSnapshot,
    SeniorityLevel,
)

__all__ = [
    "Contact",
    "ContactChannel",
    "ContactChannelType",
    "ContactMatch",
    "ContactMatchKind",
    "ContactStatus",
    "ContactVerificationStatus",
    "DecisionMakerFitAssessment",
    "Department",
    "JobTitle",
    "PersonName",
    "RawContactSnapshot",
    "SeniorityLevel",
]
