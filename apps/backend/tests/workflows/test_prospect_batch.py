"""D2a batch orchestration tests with deterministic, zero-network fakes."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest

from app.domain.company import Company
from app.domain.discovery import (
    DiscoveryCandidate,
    DiscoveryCandidateStatus,
    DiscoveryTask,
)
from app.domain.events import CompanyFactsChanged, ContactCandidateDiscovered
from app.domain.prospect_batch import ProspectBatch, ProspectBatchCompanyStatus
from app.domain.repositories import ProspectBatchUnitOfWork
from app.domain.research import (
    ExtractorIdentity,
    ResearchClaim,
    ResearchPage,
    ResearchProfile,
    ResearchRun,
)
from app.domain.services import SenderProfile
from app.domain.values import CompanyName, SourceReference, WebsiteUrl
from app.services.contact_discovery import (
    ContactSelection,
    DiscoveredContact,
    DiscoverySourceType,
    RankedContact,
)
from app.services.contact_discovery_runner import ContactDiscoveryRunOutcome
from app.shared.exceptions import ApplicationConflictError, InvalidInputError
from app.workflows.contact_ingestion import ContactIngestionAction, ContactIngestionOutcome
from app.workflows.decision_maker import (
    DecisionMakerSelectionAction,
    DecisionMakerSelectionOutcome,
)
from app.workflows.email import EmailDraftAction, EmailDraftOutcome
from app.workflows.opportunity import (
    OpportunityProcessingAction,
    OpportunityProcessingOutcome,
)
from app.workflows.prospect_batch import (
    CreateProspectBatchCommand,
    ProspectBatchWorkflow,
    RetryProspectCompanyCommand,
)
from app.workflows.research import (
    ResearchAction,
    ResearchOutcome,
    ResearchRequest,
)

NOW = datetime(2026, 7, 31, tzinfo=UTC)
SENDER = SenderProfile(
    name="Alex Morgan",
    company="Harbor Bridge Logistics",
    value_proposition="We simplify Asia-to-US inbound freight.",
)


class FakeCompanyRepository:
    def __init__(self, companies: dict[UUID, Company]) -> None:
        self.items = companies

    async def get_by_id(self, company_id: UUID) -> Company | None:
        return self.items.get(company_id)


class FakeDiscoveryTaskRepository:
    def __init__(self, tasks: dict[UUID, DiscoveryTask]) -> None:
        self.items = tasks

    async def get_by_id(self, task_id: UUID) -> DiscoveryTask | None:
        return self.items.get(task_id)


class FakeProspectBatchRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, ProspectBatch] = {}
        self.completed: set[tuple[UUID, UUID, str]] = set()

    async def get_by_id(self, batch_id: UUID) -> ProspectBatch | None:
        return self.items.get(batch_id)

    async def add(self, batch: ProspectBatch) -> None:
        self.items[batch.id] = batch

    async def save(self, batch: ProspectBatch) -> None:
        self.items[batch.id] = batch

    async def has_completed_pipeline(
        self,
        *,
        discovery_task_id: UUID,
        company_id: UUID,
        pipeline_version: str,
        exclude_batch_id: UUID | None = None,
    ) -> bool:
        del exclude_batch_id
        return (discovery_task_id, company_id, pipeline_version) in self.completed


class FakeResearchRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, ResearchRun] = {}

    async def get_by_id(self, research_id: UUID) -> ResearchRun | None:
        return self.items.get(research_id)


class FakeUnitOfWork:
    def __init__(
        self,
        *,
        companies: FakeCompanyRepository,
        discovery_tasks: FakeDiscoveryTaskRepository,
        prospect_batches: FakeProspectBatchRepository,
        research_runs: FakeResearchRepository,
    ) -> None:
        self.companies = companies
        self.discovery_tasks = discovery_tasks
        self.prospect_batches = prospect_batches
        self.research_runs = research_runs

    async def __aenter__(self) -> "FakeUnitOfWork":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class FakeResearchWorkflow:
    def __init__(self, repository: FakeResearchRepository) -> None:
        self.repository = repository
        self.calls: list[UUID] = []
        self.claim_companies: set[UUID] = set()
        self.fail_companies: set[UUID] = set()

    async def handle(self, request: ResearchRequest) -> ResearchOutcome:
        assert request.company_id is not None
        self.calls.append(request.company_id)
        if request.company_id in self.fail_companies:
            raise RuntimeError("research fixture failure")
        run = _research_run(
            request.company_id,
            with_claim=request.company_id in self.claim_companies,
        )
        self.repository.items[run.id] = run
        return ResearchOutcome(
            action=ResearchAction.COMPLETED,
            company_id=request.company_id,
            research_id=run.id,
            status=run.status,
            claims_extracted=run.claims_extracted,
            claims_validated=run.claims_validated,
        )


class FakeOpportunityWorkflow:
    def __init__(self) -> None:
        self.calls: list[UUID] = []
        self.decisions: dict[UUID, str] = {}

    async def handle(
        self,
        event: CompanyFactsChanged,
        *,
        user_id: UUID,
        user_lens_version: str | None = None,
    ) -> OpportunityProcessingOutcome:
        del user_id, user_lens_version
        company_id = event.company_id
        self.calls.append(company_id)
        decision = self.decisions.get(company_id, "qualified")
        return OpportunityProcessingOutcome(
            action=OpportunityProcessingAction.CREATED,
            company_id=company_id,
            opportunity_id=uuid4(),
            score=72.5,
            confidence=0.8,
            qualification_decision=decision,
            reasons=("deterministic fixture score",),
        )


class FakeContactDiscovery:
    def __init__(self) -> None:
        self.no_contact_companies: set[UUID] = set()

    async def discover(self, run: ResearchRun) -> ContactDiscoveryRunOutcome:
        if run.company_id in self.no_contact_companies:
            selection = ContactSelection(
                primary=None,
                alternatives=(),
                review_required=True,
                selection_reasons=("none found",),
            )
        else:
            contact = DiscoveredContact(
                name="Maria Chen",
                title="Director of Supply Chain",
                email="maria@example.com",
                phone="",
                source_url=run.website,
                source_type=DiscoverySourceType.NAMED,
                evidence_snippet="Maria Chen, Director of Supply Chain maria@example.com",
                confidence=0.9,
            )
            selection = ContactSelection(
                primary=RankedContact(contact=contact, score=0.9, reasons=("role fit",)),
                alternatives=(),
            )
        return ContactDiscoveryRunOutcome(
            selection=selection,
            pages_scanned=1,
            pages_failed=0,
        )


class FakeContactIngestion:
    async def handle(self, event: ContactCandidateDiscovered) -> ContactIngestionOutcome:
        candidate = event.candidate
        return ContactIngestionOutcome(
            action=ContactIngestionAction.CREATED,
            company_id=candidate.company_id,
            contact_id=uuid4(),
        )


class FakeDecisionMaker:
    async def handle(
        self, *, company_id: UUID, opportunity_id: UUID
    ) -> DecisionMakerSelectionOutcome:
        return DecisionMakerSelectionOutcome(
            action=DecisionMakerSelectionAction.SELECTED,
            company_id=company_id,
            opportunity_id=opportunity_id,
            selected_contact_id=uuid4(),
        )


class FakeEmailDraft:
    def __init__(self) -> None:
        self.calls = 0

    async def handle(
        self, *, opportunity_id: UUID, contact_id: UUID, sender: SenderProfile
    ) -> EmailDraftOutcome:
        del contact_id, sender
        self.calls += 1
        return EmailDraftOutcome(
            action=EmailDraftAction.GENERATED,
            opportunity_id=opportunity_id,
            outreach_id=uuid4(),
            draft_version=1,
            subject="A real review-only draft",
            body="Hello Maria,",
            status="generated",
        )


class Fixture:
    def __init__(self, specs: list[tuple[str, str | None]]) -> None:
        self.companies: dict[UUID, Company] = {}
        candidates: list[DiscoveryCandidate] = []
        task_id = uuid4()
        for position, (name, website) in enumerate(specs):
            domain_website = None
            if website and website != "not a valid url":
                domain_website = WebsiteUrl(website)
            company = Company.create(CompanyName(name), domain_website)
            source_url = f"https://evidence.example/{position}"
            company.add_source(
                SourceReference(
                    source="manual_csv",
                    reference=source_url,
                    retrieved_at=NOW,
                )
            )
            company.add_signal("import_activity: customs shipments recorded")
            self.companies[company.id] = company
            candidates.append(
                DiscoveryCandidate(
                    id=uuid4(),
                    position=position,
                    source="manual_csv",
                    source_url=source_url,
                    external_id=None,
                    company_name=name,
                    normalized_name=name.lower(),
                    website=website,
                    normalized_domain=None,
                    address=None,
                    region="US",
                    product_description=None,
                    import_evidence="BOL fixture",
                    raw_metadata_json="{}",
                    status=DiscoveryCandidateStatus.INGESTED,
                    company_id=company.id,
                    duplicate_of_id=None,
                    failure_reason=None,
                    created_at=NOW,
                )
            )

        task = DiscoveryTask.create(
            execution_task_id=task_id,
            original_prompt="帮我找 10 家北美五金进口商",
            requested_count=10,
            effective_count=10,
            parsed_region="North America",
            parsed_category="hardware",
            parsed_keywords=("hardware",),
            provider="manual_csv",
        )
        task.start()
        for candidate in candidates:
            task.add_candidate(candidate)
        task.complete()
        self.task = task
        self.batch_repository = FakeProspectBatchRepository()
        self.research_repository = FakeResearchRepository()
        self.uow = FakeUnitOfWork(
            companies=FakeCompanyRepository(self.companies),
            discovery_tasks=FakeDiscoveryTaskRepository({task.id: task}),
            prospect_batches=self.batch_repository,
            research_runs=self.research_repository,
        )
        self.research = FakeResearchWorkflow(self.research_repository)
        self.opportunity = FakeOpportunityWorkflow()
        self.contacts = FakeContactDiscovery()
        self.email = FakeEmailDraft()
        self.workflow = ProspectBatchWorkflow(
            uow_factory=cast(
                Callable[[], ProspectBatchUnitOfWork],
                lambda: self.uow,
            ),
            research=self.research,
            opportunity=self.opportunity,
            contact_discovery=self.contacts,
            contact_ingestion=FakeContactIngestion(),
            decision_maker=FakeDecisionMaker(),
            email_draft=self.email,
        )

    @property
    def company_ids(self) -> tuple[UUID, ...]:
        return tuple(self.companies)


def _research_run(company_id: UUID, *, with_claim: bool) -> ResearchRun:
    run = ResearchRun.start(
        "Fixture Company",
        "https://fixture.example",
        company_id=company_id,
    )
    run.mark_running()
    run.record_page(
        ResearchPage(
            position=0,
            url="https://fixture.example",
            final_url="https://fixture.example",
            http_status=200,
            content_type="text/html",
            fetched_at=NOW,
            content_chars=200,
        )
    )
    run.record_extraction(
        profile=ResearchProfile(),
        extractor=ExtractorIdentity(
            provider="fake",
            model="fake-research-v1",
            prompt_version="test-v1",
        ),
        proposed_count=1 if with_claim else 0,
    )
    if with_claim:
        run.record_claim(
            ResearchClaim(
                position=0,
                kind="shipping_fit",
                detail="Website mentions ocean freight",
                evidence_snippet="ocean freight",
                source_page_position=0,
                confidence=0.8,
            )
        )
    run.complete()
    return run


async def test_deduplicates_ids_and_caps_effective_count_at_five() -> None:
    fixture = Fixture(
        [(f"Company {index}", f"https://company-{index}.example") for index in range(6)]
    )
    ids = fixture.company_ids
    batch = await fixture.workflow.create(
        fixture.task.id,
        CreateProspectBatchCommand(
            company_ids=(ids[0], ids[0], *ids[1:]),
            limit=99,
            sender=SENDER,
        ),
    )

    assert batch.requested_count == 7
    assert batch.effective_count == 5
    assert [item.company_id for item in batch.companies] == list(ids[:5])


async def test_rejects_company_outside_discovery_task() -> None:
    fixture = Fixture([("Atlas", "https://atlas.example")])
    with pytest.raises(InvalidInputError, match="belong to this discovery task"):
        await fixture.workflow.create(
            fixture.task.id,
            CreateProspectBatchCommand(company_ids=(uuid4(),), sender=SENDER),
        )


async def test_preflight_isolates_missing_invalid_and_research_failure() -> None:
    fixture = Fixture(
        [
            ("Missing Website", None),
            ("Invalid Website", "not a valid url"),
            ("Research Failure", "https://research-failure.example"),
            ("Healthy", "https://healthy.example"),
        ]
    )
    ids = fixture.company_ids
    fixture.research.fail_companies.add(ids[2])
    batch = await fixture.workflow.create(
        fixture.task.id,
        CreateProspectBatchCommand(company_ids=ids, sender=SENDER),
    )
    by_id = {item.company_id: item for item in batch.companies}

    assert by_id[ids[0]].error_code == "WEBSITE_MISSING"
    assert by_id[ids[1]].error_code == "WEBSITE_INVALID"
    assert by_id[ids[2]].status is ProspectBatchCompanyStatus.FAILED
    assert by_id[ids[2]].error_code == "RESEARCH_FAILED"
    assert by_id[ids[3]].status is ProspectBatchCompanyStatus.COMPLETED
    assert fixture.research.calls == [ids[2], ids[3]]


async def test_research_claims_stop_at_human_review_without_auto_confirmation() -> None:
    fixture = Fixture([("Atlas", "https://atlas.example")])
    company_id = fixture.company_ids[0]
    fixture.research.claim_companies.add(company_id)
    batch = await fixture.workflow.create(
        fixture.task.id,
        CreateProspectBatchCommand(company_ids=(company_id,), sender=SENDER),
    )
    item = batch.companies[0]
    run = fixture.research_repository.items[cast(UUID, item.research_id)]

    assert item.status is ProspectBatchCompanyStatus.NEEDS_REVIEW
    assert item.current_stage.value == "awaiting_evidence_review"
    assert item.error_code == "EVIDENCE_REVIEW_REQUIRED"
    assert run.promotions == ()
    assert fixture.opportunity.calls == []
    assert fixture.email.calls == 0


async def test_no_contact_and_missing_sender_do_not_create_fake_drafts() -> None:
    fixture = Fixture(
        [
            ("No Contact", "https://no-contact.example"),
            ("No Sender", "https://no-sender.example"),
        ]
    )
    first, second = fixture.company_ids
    fixture.contacts.no_contact_companies.add(first)
    batch = await fixture.workflow.create(
        fixture.task.id,
        CreateProspectBatchCommand(company_ids=(first, second), sender=None),
    )
    by_id = {item.company_id: item for item in batch.companies}

    assert by_id[first].error_code == "CONTACT_NOT_FOUND"
    assert by_id[second].error_code == "SENDER_PROFILE_MISSING"
    assert by_id[first].draft_version is None
    assert by_id[second].draft_version is None
    assert fixture.email.calls == 0


async def test_completed_company_cannot_retry_and_review_gate_is_not_retryable() -> None:
    completed = Fixture([("Complete", "https://complete.example")])
    complete_batch = await completed.workflow.create(
        completed.task.id,
        CreateProspectBatchCommand(company_ids=completed.company_ids, sender=SENDER),
    )
    with pytest.raises(ApplicationConflictError, match="completed cannot be retried"):
        await completed.workflow.retry(
            complete_batch.id,
            completed.company_ids[0],
            RetryProspectCompanyCommand(sender=SENDER),
        )

    review = Fixture([("Review", "https://review.example")])
    review.research.claim_companies.add(review.company_ids[0])
    review_batch = await review.workflow.create(
        review.task.id,
        CreateProspectBatchCommand(company_ids=review.company_ids, sender=SENDER),
    )
    with pytest.raises(ApplicationConflictError, match="requires review, not retry"):
        await review.workflow.retry(
            review_batch.id,
            review.company_ids[0],
            RetryProspectCompanyCommand(sender=SENDER),
        )


async def test_retryable_failure_can_resume_and_complete() -> None:
    fixture = Fixture([("Retry", "https://retry.example")])
    company_id = fixture.company_ids[0]
    fixture.research.fail_companies.add(company_id)
    failed = await fixture.workflow.create(
        fixture.task.id,
        CreateProspectBatchCommand(company_ids=(company_id,), sender=SENDER),
    )
    assert failed.companies[0].error_code == "RESEARCH_FAILED"

    fixture.research.fail_companies.clear()
    retried = await fixture.workflow.retry(
        failed.id,
        company_id,
        RetryProspectCompanyCommand(sender=SENDER),
    )
    assert retried.status.value == "completed"
    assert retried.companies[0].status is ProspectBatchCompanyStatus.COMPLETED
