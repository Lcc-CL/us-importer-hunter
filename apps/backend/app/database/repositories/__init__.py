"""SQLAlchemy repository implementations of the domain protocols
(app/domain/repositories.py).

Rules (ADR-0017):
- Accept and return domain aggregates — ORM models never cross this boundary.
- Aggregate-oriented operations only; no generic CRUD base.
- One AsyncSession per Unit of Work, injected via constructor.
"""

from app.database.repositories.company import SqlAlchemyCompanyRepository
from app.database.repositories.contact import SqlAlchemyContactRepository
from app.database.repositories.opportunity import SqlAlchemyOpportunityRepository
from app.database.repositories.outreach import SqlAlchemyOutreachRepository
from app.database.repositories.task import SqlAlchemyTaskRepository

__all__ = [
    "SqlAlchemyCompanyRepository",
    "SqlAlchemyContactRepository",
    "SqlAlchemyOpportunityRepository",
    "SqlAlchemyOutreachRepository",
    "SqlAlchemyTaskRepository",
]
