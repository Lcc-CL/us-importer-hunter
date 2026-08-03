"""SQLAlchemy repository implementations of the domain protocols
(app/domain/repositories.py).

Rules (ADR-0017):
- Accept and return domain aggregates — ORM models never cross this boundary.
- Aggregate-oriented operations only; no generic CRUD base.
- One AsyncSession per Unit of Work, injected via constructor.
"""

from app.database.repositories.bulk_import import SqlAlchemyBulkImportRepository
from app.database.repositories.company import SqlAlchemyCompanyRepository
from app.database.repositories.contact import SqlAlchemyContactRepository
from app.database.repositories.discovery_task import SqlAlchemyDiscoveryTaskRepository
from app.database.repositories.import_evidence import SqlAlchemyImportEvidenceRepository
from app.database.repositories.import_evidence_projection import (
    SqlAlchemyImportEvidenceProjectionReader,
)
from app.database.repositories.import_evidence_promotion import (
    SqlAlchemyImportEvidencePromotionRepository,
)
from app.database.repositories.import_resolution import (
    SqlAlchemyImportProcessingJobRepository,
    SqlAlchemyImportResolutionRepository,
)
from app.database.repositories.opportunity import SqlAlchemyOpportunityRepository
from app.database.repositories.outreach import SqlAlchemyOutreachRepository
from app.database.repositories.prospect_batch import SqlAlchemyProspectBatchRepository
from app.database.repositories.prospect_job import SqlAlchemyProspectJobRepository
from app.database.repositories.prospect_routing import SqlAlchemyProspectRoutingRepository
from app.database.repositories.research import SqlAlchemyResearchRunRepository
from app.database.repositories.task import SqlAlchemyTaskRepository
from app.database.repositories.umail_export import SqlAlchemyUmailExportRepository

__all__ = [
    "SqlAlchemyBulkImportRepository",
    "SqlAlchemyCompanyRepository",
    "SqlAlchemyImportEvidenceRepository",
    "SqlAlchemyImportEvidencePromotionRepository",
    "SqlAlchemyImportEvidenceProjectionReader",
    "SqlAlchemyImportProcessingJobRepository",
    "SqlAlchemyImportResolutionRepository",
    "SqlAlchemyContactRepository",
    "SqlAlchemyDiscoveryTaskRepository",
    "SqlAlchemyOpportunityRepository",
    "SqlAlchemyOutreachRepository",
    "SqlAlchemyProspectBatchRepository",
    "SqlAlchemyProspectJobRepository",
    "SqlAlchemyProspectRoutingRepository",
    "SqlAlchemyResearchRunRepository",
    "SqlAlchemyTaskRepository",
    "SqlAlchemyUmailExportRepository",
]
