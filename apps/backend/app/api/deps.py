"""FastAPI dependency providers.

Resources (engine, session factory, redis) live on ``app.state``; these
providers expose them to routes and services via dependency injection.
"""

from collections.abc import AsyncIterator, Callable
from typing import Annotated, cast

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.database.repositories import SqlAlchemyImportEvidenceProjectionReader
from app.database.uow import SqlAlchemyUnitOfWork
from app.domain.discovery import CompanyDiscoveryProvider
from app.domain.repositories import (
    BulkImportUnitOfWork,
    DiscoveryTaskUnitOfWork,
    ProspectBatchUnitOfWork,
    UnitOfWork,
)
from app.domain.services import (
    DecisionMakerSelectionService,
    EmailDraftGenerator,
    ImportEvidenceProjectionReader,
    OpportunityScoringService,
)
from app.services.contact import DeterministicDecisionMakerSelectionService
from app.services.contact_discovery_runner import WebsiteContactDiscoveryService
from app.services.email import FakeEmailDraftGenerator, OpenAIEmailDraftGenerator
from app.services.research import (
    FakeResearchExtractor,
    OpenAIResearchExtractor,
    ResearchExtractor,
)
from app.services.scoring import DeterministicOpportunityScoringService
from app.shared.exceptions import ProviderUnavailableError
from app.tools.importyeti import ImportYetiCompanyDiscoveryProvider
from app.tools.website import FetchLimits, SafeFetcher, SiteScope
from app.workflows.bulk_import import BulkImportQueryWorkflow, BulkImportWorkflow
from app.workflows.company_ingestion import CompanyIngestionWorkflow
from app.workflows.contact_ingestion import ContactIngestionWorkflow
from app.workflows.decision_maker import DecisionMakerSelectionWorkflow
from app.workflows.discovery_task import DiscoveryTaskQueryWorkflow, DiscoveryTaskWorkflow
from app.workflows.email import EmailDraftGenerationWorkflow
from app.workflows.import_evidence import EvidenceFlowUnitOfWork, EvidenceToDraftWorkflow
from app.workflows.mvp_prospect_analysis import (
    ApproveEmailDraftWorkflow,
    MvpProspectAnalysisWorkflow,
    MvpProspectQueryWorkflow,
    UowFactory,
)
from app.workflows.opportunity import OpportunityApplicationWorkflow
from app.workflows.prospect_batch import (
    ProspectBatchQueryWorkflow,
    ProspectBatchSubmissionWorkflow,
    ProspectBatchWorkflow,
    ProspectJobQueryWorkflow,
)
from app.workflows.research import (
    ClaimPromotionWorkflow,
    ResearchLimits,
    ResearchWorkflow,
)


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


def get_bulk_import_workflow(uow_factory: UowFactoryDep) -> BulkImportWorkflow:
    return BulkImportWorkflow(cast(Callable[[], BulkImportUnitOfWork], uow_factory))


BulkImportWorkflowDep = Annotated[BulkImportWorkflow, Depends(get_bulk_import_workflow)]


def get_bulk_import_query_workflow(uow_factory: UowFactoryDep) -> BulkImportQueryWorkflow:
    return BulkImportQueryWorkflow(cast(Callable[[], BulkImportUnitOfWork], uow_factory))


BulkImportQueryDep = Annotated[
    BulkImportQueryWorkflow, Depends(get_bulk_import_query_workflow)
]


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


CompanyIngestionDep = Annotated[CompanyIngestionWorkflow, Depends(get_company_ingestion_workflow)]


def get_company_discovery_provider() -> CompanyDiscoveryProvider:
    return ImportYetiCompanyDiscoveryProvider()


CompanyDiscoveryProviderDep = Annotated[
    CompanyDiscoveryProvider, Depends(get_company_discovery_provider)
]


def get_discovery_task_workflow(
    uow_factory: UowFactoryDep,
    provider: CompanyDiscoveryProviderDep,
    company_ingestion: CompanyIngestionDep,
) -> DiscoveryTaskWorkflow:
    discovery_uow_factory = cast(Callable[[], DiscoveryTaskUnitOfWork], uow_factory)
    return DiscoveryTaskWorkflow(
        uow_factory=discovery_uow_factory,
        provider=provider,
        company_ingestion=company_ingestion,
    )


DiscoveryTaskWorkflowDep = Annotated[DiscoveryTaskWorkflow, Depends(get_discovery_task_workflow)]


def get_discovery_task_query_workflow(
    uow_factory: UowFactoryDep,
) -> DiscoveryTaskQueryWorkflow:
    return DiscoveryTaskQueryWorkflow(cast(Callable[[], DiscoveryTaskUnitOfWork], uow_factory))


DiscoveryTaskQueryDep = Annotated[
    DiscoveryTaskQueryWorkflow, Depends(get_discovery_task_query_workflow)
]


def get_import_evidence_projection_reader(
    request: Request,
) -> ImportEvidenceProjectionReader | None:
    session_factory = getattr(request.app.state, "session_factory", None)
    return (
        SqlAlchemyImportEvidenceProjectionReader(session_factory)
        if session_factory is not None
        else None
    )


ImportEvidenceProjectionReaderDep = Annotated[
    ImportEvidenceProjectionReader | None,
    Depends(get_import_evidence_projection_reader),
]


def get_opportunity_workflow(
    uow_factory: UowFactoryDep,
    scoring: OpportunityScoringDep,
    import_evidence_reader: ImportEvidenceProjectionReaderDep,
) -> OpportunityApplicationWorkflow:
    return OpportunityApplicationWorkflow(
        uow_factory,
        scoring,
        import_evidence_reader=import_evidence_reader,
    )


OpportunityWorkflowDep = Annotated[
    OpportunityApplicationWorkflow, Depends(get_opportunity_workflow)
]


def get_contact_ingestion_workflow(uow_factory: UowFactoryDep) -> ContactIngestionWorkflow:
    return ContactIngestionWorkflow(uow_factory)


ContactIngestionDep = Annotated[ContactIngestionWorkflow, Depends(get_contact_ingestion_workflow)]


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


EmailDraftWorkflowDep = Annotated[EmailDraftGenerationWorkflow, Depends(get_email_draft_workflow)]


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


MvpProspectQueryDep = Annotated[MvpProspectQueryWorkflow, Depends(get_mvp_prospect_query_workflow)]


def get_approve_email_draft_workflow(uow_factory: UowFactoryDep) -> ApproveEmailDraftWorkflow:
    return ApproveEmailDraftWorkflow(uow_factory)


ApproveEmailDraftDep = Annotated[
    ApproveEmailDraftWorkflow, Depends(get_approve_email_draft_workflow)
]


def get_evidence_to_draft_workflow(
    uow_factory: UowFactoryDep,
    opportunity: OpportunityWorkflowDep,
    decision_maker: DecisionMakerWorkflowDep,
    email: EmailDraftWorkflowDep,
) -> EvidenceToDraftWorkflow:
    evidence_factory = cast(Callable[[], EvidenceFlowUnitOfWork], uow_factory)
    return EvidenceToDraftWorkflow(
        evidence_factory,
        opportunity=opportunity,
        decision_maker=decision_maker,
        email_draft=email,
    )


EvidenceToDraftDep = Annotated[EvidenceToDraftWorkflow, Depends(get_evidence_to_draft_workflow)]


def get_research_extractor(settings: SettingsDep) -> ResearchExtractor:
    """Fake by default; the real extractor only on an explicit opt-in.

    A misconfigured `openai` selection raises instead of falling back to the
    Fake extractor — silently serving deterministic stub claims while the
    operator believes a model ran would corrupt the evidence trail (ADR-0027).
    """
    if settings.research_extractor_provider == "fake":
        return FakeResearchExtractor()
    if settings.research_extractor_provider == "openai":
        model = settings.resolved_research_model
        if not model:
            raise ProviderUnavailableError(
                "research extractor is set to openai but no model is configured"
            )
        return OpenAIResearchExtractor(
            model=model,
            api_key=settings.openai_api_key or None,
            base_url=settings.openai_base_url or None,
            prompt_version=settings.research_prompt_version,
            timeout_seconds=settings.research_extractor_timeout_seconds,
            max_input_chars=settings.research_extractor_max_input_chars,
        )
    if settings.research_extractor_provider == "deepseek":
        if not settings.deepseek_api_key.strip():
            raise ProviderUnavailableError(
                "research extractor is set to deepseek but DEEPSEEK_API_KEY is not configured"
            )
        if not settings.deepseek_model.strip():
            raise ProviderUnavailableError(
                "research extractor is set to deepseek but no model is configured"
            )
        return OpenAIResearchExtractor(
            model=settings.deepseek_model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url or None,
            provider="deepseek",
            # Structured extraction wants plain JSON output; reasoning traces
            # add cost and can leak into content on OpenAI-compatible gateways.
            extra_body={"thinking": {"type": "disabled"}},
            prompt_version=settings.research_prompt_version,
            timeout_seconds=settings.research_extractor_timeout_seconds,
            max_input_chars=settings.research_extractor_max_input_chars,
        )
    raise ProviderUnavailableError("configured research extractor is unavailable")


ResearchExtractorDep = Annotated[ResearchExtractor, Depends(get_research_extractor)]


def get_research_workflow(
    uow_factory: UowFactoryDep,
    extractor: ResearchExtractorDep,
    settings: SettingsDep,
) -> ResearchWorkflow:
    limits = ResearchLimits(
        max_pages=settings.research_max_pages,
        max_page_chars=settings.research_max_page_chars,
        total_budget_seconds=settings.research_total_budget_seconds,
        request_delay_seconds=settings.research_request_delay_seconds,
        user_agent=settings.research_user_agent,
    )

    def fetcher_factory(scope: SiteScope) -> SafeFetcher:
        return SafeFetcher(
            limits=FetchLimits(
                max_page_bytes=settings.research_max_page_bytes,
                max_decompressed_bytes=settings.research_max_decompressed_bytes,
                request_timeout_seconds=settings.research_request_timeout_seconds,
                max_redirects=settings.research_max_redirects,
                user_agent=settings.research_user_agent,
            ),
            scope=scope,
        )

    return ResearchWorkflow(
        uow_factory=uow_factory,
        extractor=extractor,
        fetcher_factory=fetcher_factory,
        limits=limits,
    )


ResearchWorkflowDep = Annotated[ResearchWorkflow, Depends(get_research_workflow)]


def get_claim_promotion_workflow(uow_factory: UowFactoryDep) -> ClaimPromotionWorkflow:
    return ClaimPromotionWorkflow(uow_factory=uow_factory)


ClaimPromotionDep = Annotated[ClaimPromotionWorkflow, Depends(get_claim_promotion_workflow)]


def get_prospect_batch_workflow(
    uow_factory: UowFactoryDep,
    research: ResearchWorkflowDep,
    opportunity: OpportunityWorkflowDep,
    contact_ingestion: ContactIngestionDep,
    decision_maker: DecisionMakerWorkflowDep,
    email: EmailDraftWorkflowDep,
    settings: SettingsDep,
) -> ProspectBatchWorkflow:
    contact_discovery = WebsiteContactDiscoveryService(
        fetch_limits=FetchLimits(
            max_page_bytes=settings.research_max_page_bytes,
            max_decompressed_bytes=settings.research_max_decompressed_bytes,
            request_timeout_seconds=settings.research_request_timeout_seconds,
            max_redirects=settings.research_max_redirects,
            user_agent=settings.research_user_agent,
        ),
        max_pages=settings.research_max_pages,
        max_page_chars=settings.research_max_page_chars,
    )
    return ProspectBatchWorkflow(
        uow_factory=cast(Callable[[], ProspectBatchUnitOfWork], uow_factory),
        research=research,
        opportunity=opportunity,
        contact_discovery=contact_discovery,
        contact_ingestion=contact_ingestion,
        decision_maker=decision_maker,
        email_draft=email,
    )


ProspectBatchWorkflowDep = Annotated[ProspectBatchWorkflow, Depends(get_prospect_batch_workflow)]


def get_prospect_batch_submission_workflow(
    uow_factory: UowFactoryDep,
    settings: SettingsDep,
) -> ProspectBatchSubmissionWorkflow:
    return ProspectBatchSubmissionWorkflow(
        cast(Callable[[], ProspectBatchUnitOfWork], uow_factory),
        max_attempts=settings.prospect_job_max_attempts,
    )


ProspectBatchSubmissionDep = Annotated[
    ProspectBatchSubmissionWorkflow,
    Depends(get_prospect_batch_submission_workflow),
]


def get_prospect_batch_query_workflow(
    uow_factory: UowFactoryDep,
) -> ProspectBatchQueryWorkflow:
    return ProspectBatchQueryWorkflow(cast(Callable[[], ProspectBatchUnitOfWork], uow_factory))


ProspectBatchQueryDep = Annotated[
    ProspectBatchQueryWorkflow, Depends(get_prospect_batch_query_workflow)
]


def get_prospect_job_query_workflow(
    uow_factory: UowFactoryDep,
) -> ProspectJobQueryWorkflow:
    return ProspectJobQueryWorkflow(cast(Callable[[], ProspectBatchUnitOfWork], uow_factory))


ProspectJobQueryDep = Annotated[ProspectJobQueryWorkflow, Depends(get_prospect_job_query_workflow)]
