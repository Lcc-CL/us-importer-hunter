"""FastAPI dependency providers.

Resources (engine, session factory, redis) live on ``app.state``; these
providers expose them to routes and services via dependency injection.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.database.uow import SqlAlchemyUnitOfWork
from app.domain.repositories import UnitOfWork
from app.domain.services import (
    DecisionMakerSelectionService,
    EmailDraftGenerator,
    OpportunityScoringService,
)
from app.services.contact import DeterministicDecisionMakerSelectionService
from app.services.email import FakeEmailDraftGenerator, OpenAIEmailDraftGenerator
from app.services.scoring import DeterministicOpportunityScoringService
from app.shared.exceptions import ProviderUnavailableError
from app.workflows.company_ingestion import CompanyIngestionWorkflow
from app.workflows.contact_ingestion import ContactIngestionWorkflow
from app.workflows.decision_maker import DecisionMakerSelectionWorkflow
from app.workflows.email import EmailDraftGenerationWorkflow
from app.workflows.mvp_prospect_analysis import (
    ApproveEmailDraftWorkflow,
    MvpProspectAnalysisWorkflow,
    MvpProspectQueryWorkflow,
    UowFactory,
)
from app.workflows.opportunity import OpportunityApplicationWorkflow


def get_request_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_request_settings)]


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a database session scoped to a single request."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session


def get_redis(request: Request) -> Redis:
    redis: Redis = request.app.state.redis
    return redis


DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]


def get_uow_factory(request: Request) -> UowFactory:
    session_factory = request.app.state.session_factory

    def factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return factory


UowFactoryDep = Annotated[UowFactory, Depends(get_uow_factory)]


def get_opportunity_scoring_service() -> OpportunityScoringService:
    return DeterministicOpportunityScoringService()


OpportunityScoringDep = Annotated[
    OpportunityScoringService, Depends(get_opportunity_scoring_service)
]


def get_decision_maker_selection_service() -> DecisionMakerSelectionService:
    return DeterministicDecisionMakerSelectionService()


DecisionMakerSelectionDep = Annotated[
    DecisionMakerSelectionService, Depends(get_decision_maker_selection_service)
]


def get_email_draft_generator(settings: SettingsDep) -> EmailDraftGenerator:
    if settings.email_generator_provider == "fake":
        return FakeEmailDraftGenerator()
    if settings.email_generator_provider == "openai":
        return OpenAIEmailDraftGenerator(
            api_key=settings.openai_api_key or None,
            model=settings.openai_model,
        )
    raise ProviderUnavailableError("configured email generator is unavailable")


EmailDraftGeneratorDep = Annotated[EmailDraftGenerator, Depends(get_email_draft_generator)]


def get_company_ingestion_workflow(uow_factory: UowFactoryDep) -> CompanyIngestionWorkflow:
    return CompanyIngestionWorkflow(uow_factory)


CompanyIngestionDep = Annotated[
    CompanyIngestionWorkflow, Depends(get_company_ingestion_workflow)
]


def get_opportunity_workflow(
    uow_factory: UowFactoryDep,
    scoring: OpportunityScoringDep,
) -> OpportunityApplicationWorkflow:
    return OpportunityApplicationWorkflow(uow_factory, scoring)


OpportunityWorkflowDep = Annotated[
    OpportunityApplicationWorkflow, Depends(get_opportunity_workflow)
]


def get_contact_ingestion_workflow(uow_factory: UowFactoryDep) -> ContactIngestionWorkflow:
    return ContactIngestionWorkflow(uow_factory)


ContactIngestionDep = Annotated[
    ContactIngestionWorkflow, Depends(get_contact_ingestion_workflow)
]


def get_decision_maker_workflow(
    uow_factory: UowFactoryDep,
    selection: DecisionMakerSelectionDep,
) -> DecisionMakerSelectionWorkflow:
    return DecisionMakerSelectionWorkflow(uow_factory, selection)


DecisionMakerWorkflowDep = Annotated[
    DecisionMakerSelectionWorkflow, Depends(get_decision_maker_workflow)
]


def get_email_draft_workflow(
    uow_factory: UowFactoryDep,
    generator: EmailDraftGeneratorDep,
) -> EmailDraftGenerationWorkflow:
    return EmailDraftGenerationWorkflow(uow_factory, generator)


EmailDraftWorkflowDep = Annotated[
    EmailDraftGenerationWorkflow, Depends(get_email_draft_workflow)
]


def get_mvp_prospect_analysis_workflow(
    company: CompanyIngestionDep,
    opportunity: OpportunityWorkflowDep,
    contact: ContactIngestionDep,
    decision_maker: DecisionMakerWorkflowDep,
    email: EmailDraftWorkflowDep,
) -> MvpProspectAnalysisWorkflow:
    return MvpProspectAnalysisWorkflow(
        company_ingestion=company,
        opportunity=opportunity,
        contact_ingestion=contact,
        decision_maker=decision_maker,
        email_draft=email,
    )


MvpProspectAnalysisDep = Annotated[
    MvpProspectAnalysisWorkflow, Depends(get_mvp_prospect_analysis_workflow)
]


def get_mvp_prospect_query_workflow(uow_factory: UowFactoryDep) -> MvpProspectQueryWorkflow:
    return MvpProspectQueryWorkflow(uow_factory)


MvpProspectQueryDep = Annotated[
    MvpProspectQueryWorkflow, Depends(get_mvp_prospect_query_workflow)
]


def get_approve_email_draft_workflow(uow_factory: UowFactoryDep) -> ApproveEmailDraftWorkflow:
    return ApproveEmailDraftWorkflow(uow_factory)


ApproveEmailDraftDep = Annotated[
    ApproveEmailDraftWorkflow, Depends(get_approve_email_draft_workflow)
]
