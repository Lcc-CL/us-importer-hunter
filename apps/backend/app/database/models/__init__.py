"""ORM models (SQLAlchemy 2.x declarative), grouped by aggregate.

Persistence-only: these classes never cross the repository boundary —
repositories accept and return domain aggregates (ADR-0017). Every model
module is imported here so Alembic autogenerate sees the full metadata.
"""

from app.database.models.calibration import (
    CalibrationEvaluationModel,
    CalibrationRunModel,
)
from app.database.models.company import (
    CompanyAliasModel,
    CompanyModel,
    CompanySignalModel,
    CompanySourceModel,
)
from app.database.models.contact import ContactModel
from app.database.models.discovery_task import DiscoveryCandidateModel, DiscoveryTaskModel
from app.database.models.import_evidence import (
    ImporterEntityMatchModel,
    ImporterEvidenceAggregateModel,
    ImporterEvidenceAggregateShipmentModel,
    ImportEvidenceCompanySignalModel,
    ImportEvidenceConflictModel,
    ImportEvidenceJobModel,
    ImportEvidencePromotionQualityAssessmentModel,
    ImportEvidenceQualityAssessmentModel,
    ImportEvidenceRawRecordModel,
    ImportEvidenceSignalModel,
    ImportEvidenceSignalPromotionModel,
    ImportEvidenceSnapshotModel,
    NormalizedShipmentModel,
)
from app.database.models.opportunity import (
    OpportunityAssessmentModel,
    OpportunityEvidenceModel,
    OpportunityModel,
)
from app.database.models.outreach import EmailDraftModel, OutcomeModel, OutreachModel
from app.database.models.prospect_batch import (
    ProspectBatchCompanyModel,
    ProspectBatchJobModel,
    ProspectBatchModel,
)
from app.database.models.research import (
    ResearchClaimModel,
    ResearchPageModel,
    ResearchPromotionModel,
    ResearchRunModel,
)
from app.database.models.task import TaskAttemptModel, TaskModel

__all__ = [
    "CompanyAliasModel",
    "CalibrationEvaluationModel",
    "CalibrationRunModel",
    "CompanyModel",
    "CompanySignalModel",
    "CompanySourceModel",
    "ContactModel",
    "DiscoveryCandidateModel",
    "DiscoveryTaskModel",
    "ImportEvidenceConflictModel",
    "ImportEvidenceCompanySignalModel",
    "ImportEvidenceJobModel",
    "ImportEvidenceRawRecordModel",
    "ImportEvidenceQualityAssessmentModel",
    "ImportEvidencePromotionQualityAssessmentModel",
    "ImportEvidenceSignalModel",
    "ImportEvidenceSnapshotModel",
    "ImportEvidenceSignalPromotionModel",
    "ImporterEntityMatchModel",
    "ImporterEvidenceAggregateModel",
    "ImporterEvidenceAggregateShipmentModel",
    "NormalizedShipmentModel",
    "EmailDraftModel",
    "OpportunityAssessmentModel",
    "OpportunityEvidenceModel",
    "OpportunityModel",
    "OutcomeModel",
    "OutreachModel",
    "ProspectBatchCompanyModel",
    "ProspectBatchJobModel",
    "ProspectBatchModel",
    "ResearchClaimModel",
    "ResearchPageModel",
    "ResearchPromotionModel",
    "ResearchRunModel",
    "TaskAttemptModel",
    "TaskModel",
]
