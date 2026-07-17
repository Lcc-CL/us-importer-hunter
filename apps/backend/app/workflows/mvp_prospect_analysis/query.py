"""Read-only MVP prospect result assembly from domain repositories."""

from dataclasses import dataclass
from uuid import UUID

from app.domain.company import Company
from app.domain.contact import Contact, ContactStatus, DecisionMakerFitAssessment
from app.domain.opportunity import Opportunity
from app.domain.outreach import Outreach
from app.shared.exceptions import ResourceNotFoundError
from app.workflows.mvp_prospect_analysis.workflow import MVP_SYSTEM_USER_ID, UowFactory


@dataclass(frozen=True)
class ProspectQueryResult:
    company: Company
    opportunity: Opportunity | None
    contacts: tuple[Contact, ...]
    decision_maker_rankings: tuple[DecisionMakerFitAssessment, ...]
    outreaches: tuple[Outreach, ...]


class MvpProspectQueryWorkflow:
    def __init__(
        self, uow_factory: UowFactory, *, user_id: UUID = MVP_SYSTEM_USER_ID
    ) -> None:
        self._uow_factory = uow_factory
        self._user_id = user_id

    async def handle(self, company_id: UUID) -> ProspectQueryResult:
        async with self._uow_factory() as uow:
            company = await uow.companies.get_by_id(company_id)
            if company is None:
                raise ResourceNotFoundError(f"company {company_id} was not found")

            opportunity = await uow.opportunities.get_for_company_and_user(
                company_id, self._user_id
            )
            contacts = tuple(
                contact
                for contact in await uow.contacts.list_for_company(company_id)
                if contact.status not in (ContactStatus.INVALID, ContactStatus.INACTIVE)
            )
            assessments = await uow.contacts.list_fit_assessments_for_company(company_id)
            latest_by_contact: dict[UUID, DecisionMakerFitAssessment] = {}
            for assessment in assessments:
                latest_by_contact.setdefault(assessment.contact_id, assessment)
            rankings = tuple(
                sorted(
                    latest_by_contact.values(),
                    key=lambda item: (
                        -item.total_score,
                        -item.confidence.value,
                        str(item.contact_id),
                    ),
                )
            )
            outreaches = (
                tuple(await uow.outreaches.list_for_opportunity(opportunity.id))
                if opportunity is not None
                else ()
            )
            return ProspectQueryResult(
                company=company,
                opportunity=opportunity,
                contacts=contacts,
                decision_maker_rankings=rankings,
                outreaches=outreaches,
            )
