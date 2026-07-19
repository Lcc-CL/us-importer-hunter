"""ORM models (SQLAlchemy 2.x declarative), grouped by aggregate.

Persistence-only: these classes never cross the repository boundary —
repositories accept and return domain aggregates (ADR-0017). Every model
module is imported here so Alembic autogenerate sees the full metadata.
"""

from app.database.models.company import (
    CompanyAliasModel,
    CompanyModel,
    CompanySignalModel,
    CompanySourceModel,
)
from app.database.models.contact import ContactModel
from app.database.models.opportunity import (
    OpportunityAssessmentModel,
    OpportunityEvidenceModel,
    OpportunityModel,
)
from app.database.models.outreach import EmailDraftModel, OutcomeModel, OutreachModel
from app.database.models.research import (
    ResearchClaimModel,
    ResearchPageModel,
    ResearchPromotionModel,
    ResearchRunModel,
)
from app.database.models.task import TaskAttemptModel, TaskModel

__all__ = [
    "CompanyAliasModel",
    "CompanyModel",
    "CompanySignalModel",
    "CompanySourceModel",
    "ContactModel",
    "EmailDraftModel",
    "OpportunityAssessmentModel",
    "OpportunityEvidenceModel",
    "OpportunityModel",
    "OutcomeModel",
    "OutreachModel",
    "ResearchClaimModel",
    "ResearchPageModel",
    "ResearchPromotionModel",
    "ResearchRunModel",
    "TaskAttemptModel",
    "TaskModel",
]
