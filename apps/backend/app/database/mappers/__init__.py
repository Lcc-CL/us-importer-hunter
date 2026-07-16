"""Explicit mappers: domain aggregate ↔ persistence model (ADR-0017).

Mapping lives here and only here — never inside aggregates or API
schemas. Reconstruction sets aggregate private state directly (the
mapper is the one sanctioned peer of the domain's internals) and always
leaves the pending-event buffer empty: loading an aggregate must never
replay history as new events.
"""

from app.database.mappers.company import CompanyMapper
from app.database.mappers.contact import ContactMapper, FitAssessmentMapper
from app.database.mappers.opportunity import OpportunityMapper
from app.database.mappers.outreach import OutreachMapper
from app.database.mappers.task import TaskMapper

__all__ = [
    "CompanyMapper",
    "ContactMapper",
    "FitAssessmentMapper",
    "OpportunityMapper",
    "OutreachMapper",
    "TaskMapper",
]
