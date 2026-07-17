"""MVP prospect facade: orchestration and partial-success semantics."""

from uuid import UUID

from app.domain.events import (
    CompanyDiscovered,
    CompanyFactsChanged,
    CompanyIngested,
    ContactCandidateDiscovered,
)
from app.domain.services import SenderProfile
from app.services.email import EmailGenerationError
from app.workflows.company_ingestion import IngestionOutcome, IngestionStatus
from app.workflows.contact_ingestion import ContactIngestionAction, ContactIngestionOutcome
from app.workflows.decision_maker import (
    DecisionMakerSelectionAction,
    DecisionMakerSelectionOutcome,
)
from app.workflows.email import EmailDraftAction, EmailDraftOutcome
from app.workflows.mvp_prospect_analysis import (
    MvpProspectAnalysisCommand,
    MvpProspectAnalysisWorkflow,
    OverallStatus,
    ProspectCompanyInput,
    ProspectContactInput,
    ProspectSourceInput,
    StageStatus,
)
from app.workflows.opportunity import OpportunityProcessingAction, OpportunityProcessingOutcome

REQUEST_ID = "11111111-1111-1111-1111-111111111111"
COMPANY_ID = UUID("22222222-2222-2222-2222-222222222222")
OPPORTUNITY_ID = UUID("33333333-3333-3333-3333-333333333333")
CONTACT_ID = UUID("44444444-4444-4444-4444-444444444444")
OUTREACH_ID = UUID("55555555-5555-5555-5555-555555555555")


class StubCompanyWorkflow:
    def __init__(
        self,
        outcome: IngestionOutcome,
        order: list[str],
        error: Exception | None = None,
    ) -> None:
        self.outcome = outcome
        self.order = order
        self.error = error
        self.calls = 0
        self.events: list[CompanyDiscovered] = []

    async def handle(self, event: CompanyDiscovered) -> IngestionOutcome:
        self.calls += 1
        self.events.append(event)
        self.order.append("company")
        if self.error:
            raise self.error
        return self.outcome


class StubOpportunityWorkflow:
    def __init__(
        self,
        outcome: OpportunityProcessingOutcome,
        order: list[str],
        error: Exception | None = None,
    ) -> None:
        self.outcome = outcome
        self.order = order
        self.error = error
        self.calls = 0

    async def handle(
        self,
        event: CompanyIngested | CompanyFactsChanged,
        *,
        user_id: UUID,
        user_lens_version: str | None = None,
    ) -> OpportunityProcessingOutcome:
        self.calls += 1
        self.order.append("opportunity")
        if self.error:
            raise self.error
        return self.outcome


class StubContactWorkflow:
    def __init__(
        self,
        outcome: ContactIngestionOutcome,
        order: list[str],
        error: Exception | None = None,
    ) -> None:
        self.outcome = outcome
        self.order = order
        self.error = error
        self.calls = 0

    async def handle(self, event: ContactCandidateDiscovered) -> ContactIngestionOutcome:
        self.calls += 1
        self.order.append("contact")
        if self.error:
            raise self.error
        return self.outcome


class StubDecisionWorkflow:
    def __init__(
        self,
        outcome: DecisionMakerSelectionOutcome,
        order: list[str],
        error: Exception | None = None,
    ) -> None:
        self.outcome = outcome
        self.order = order
        self.error = error
        self.calls = 0

    async def handle(
        self, *, company_id: UUID, opportunity_id: UUID
    ) -> DecisionMakerSelectionOutcome:
        self.calls += 1
        self.order.append("decision")
        if self.error:
            raise self.error
        return self.outcome


class StubEmailWorkflow:
    def __init__(
        self,
        outcome: EmailDraftOutcome,
        order: list[str],
        error: Exception | None = None,
    ) -> None:
        self.outcome = outcome
        self.order = order
        self.error = error
        self.calls = 0

    async def handle(
        self, *, opportunity_id: UUID, contact_id: UUID, sender: SenderProfile
    ) -> EmailDraftOutcome:
        self.calls += 1
        self.order.append("email")
        if self.error:
            raise self.error
        return self.outcome


def company_outcome(status: IngestionStatus = IngestionStatus.CREATED) -> IngestionOutcome:
    return IngestionOutcome(
        status=status,
        company_id=COMPANY_ID,
        event=CompanyIngested(
            company_id=COMPANY_ID,
            ingestion_result="created" if status is IngestionStatus.CREATED else "merged",
            source="importyeti",
        ),
    )


def opportunity_outcome(
    decision: str = "qualified",
) -> OpportunityProcessingOutcome:
    return OpportunityProcessingOutcome(
        action=OpportunityProcessingAction.CREATED,
        company_id=COMPANY_ID,
        opportunity_id=OPPORTUNITY_ID,
        score=81.0,
        confidence=0.8,
        data_completeness=0.9,
        qualification_decision=decision,
        recommended_action=(
            "prepare_outreach" if decision == "qualified" else "collect_more_data"
        ),
        reasons=("child scorer reason",),
    )


def contact_outcome(
    action: ContactIngestionAction = ContactIngestionAction.CREATED,
) -> ContactIngestionOutcome:
    return ContactIngestionOutcome(
        action=action,
        company_id=COMPANY_ID,
        contact_id=(
            None if action is ContactIngestionAction.REJECTED else CONTACT_ID
        ),
        notes=("child contact note",),
    )


def decision_outcome(
    action: DecisionMakerSelectionAction = DecisionMakerSelectionAction.SELECTED,
) -> DecisionMakerSelectionOutcome:
    return DecisionMakerSelectionOutcome(
        action=action,
        company_id=COMPANY_ID,
        opportunity_id=OPPORTUNITY_ID,
        selected_contact_id=(
            CONTACT_ID if action is DecisionMakerSelectionAction.SELECTED else None
        ),
        recommended_channel=(
            "email" if action is DecisionMakerSelectionAction.SELECTED else None
        ),
        confidence=0.9,
        reasons=("child selection reason",),
    )


def email_outcome(
    action: EmailDraftAction = EmailDraftAction.GENERATED,
) -> EmailDraftOutcome:
    return EmailDraftOutcome(
        action=action,
        opportunity_id=OPPORTUNITY_ID,
        outreach_id=OUTREACH_ID,
        draft_version=1,
        subject="Child-generated subject",
        body="Child-generated body",
        status="generated",
        notes=("child email note",),
    )


def command(
    *,
    with_contact: bool = True,
    generate_email: bool = True,
    multiple_sources: bool = False,
) -> MvpProspectAnalysisCommand:
    return MvpProspectAnalysisCommand(
        request_id=REQUEST_ID,
        company=ProspectCompanyInput(
            name="Pacific Home Goods",
            website="https://phg.example",
            sources=(
                (
                    ProspectSourceInput(
                        source="importyeti",
                        reference="https://www.importyeti.com/company/phg",
                    ),
                    ProspectSourceInput(
                        source="company_website",
                        reference="https://phg.example/about",
                    ),
                )
                if multiple_sources
                else ()
            ),
            source=None if multiple_sources else "importyeti",
        ),
        contact=(
            ProspectContactInput(
                name="Maria Chen",
                title="Director of Supply Chain",
                email="maria@phg.example",
                source="website",
            )
            if with_contact
            else None
        ),
        sender=SenderProfile(
            name="Alex",
            company="Harbor Logistics",
            value_proposition="Reliable Asia-US freight support.",
        ),
        generate_email=generate_email,
    )


def build_workflow(
    *,
    company: IngestionOutcome | None = None,
    opportunity: OpportunityProcessingOutcome | None = None,
    contact: ContactIngestionOutcome | None = None,
    decision: DecisionMakerSelectionOutcome | None = None,
    email: EmailDraftOutcome | None = None,
    company_error: Exception | None = None,
    email_error: Exception | None = None,
) -> tuple[
    MvpProspectAnalysisWorkflow,
    StubCompanyWorkflow,
    StubOpportunityWorkflow,
    StubContactWorkflow,
    StubDecisionWorkflow,
    StubEmailWorkflow,
    list[str],
]:
    order: list[str] = []
    company_stub = StubCompanyWorkflow(company or company_outcome(), order, company_error)
    opportunity_stub = StubOpportunityWorkflow(
        opportunity or opportunity_outcome(), order
    )
    contact_stub = StubContactWorkflow(contact or contact_outcome(), order)
    decision_stub = StubDecisionWorkflow(decision or decision_outcome(), order)
    email_stub = StubEmailWorkflow(email or email_outcome(), order, email_error)
    workflow = MvpProspectAnalysisWorkflow(
        company_stub,
        opportunity_stub,
        contact_stub,
        decision_stub,
        email_stub,
    )
    return (
        workflow,
        company_stub,
        opportunity_stub,
        contact_stub,
        decision_stub,
        email_stub,
        order,
    )


async def test_complete_chain_succeeds_in_order() -> None:
    workflow, *_, order = build_workflow()
    outcome = await workflow.handle(command())
    assert outcome.overall_status is OverallStatus.COMPLETED
    assert order == ["company", "opportunity", "contact", "decision", "email"]


async def test_multiple_real_sources_are_ingested_before_scoring() -> None:
    workflow, company_stub, *_rest, order = build_workflow()

    outcome = await workflow.handle(command(multiple_sources=True))

    assert outcome.overall_status is OverallStatus.COMPLETED
    assert company_stub.calls == 2
    assert order[:3] == ["company", "company", "opportunity"]
    assert [
        (event.result.snapshot.source.source, event.result.snapshot.source.reference)
        for event in company_stub.events
    ] == [
        ("importyeti", "https://www.importyeti.com/company/phg"),
        ("company_website", "https://phg.example/about"),
    ]
    assert outcome.email_draft.action is StageStatus.GENERATED


async def test_company_merge_continues() -> None:
    workflow, *_ = build_workflow(company=company_outcome(IngestionStatus.MERGED))
    outcome = await workflow.handle(command())
    assert outcome.company.action is StageStatus.MERGED
    assert outcome.email_draft.action is StageStatus.GENERATED


async def test_research_more_keeps_analysis_and_skips_email() -> None:
    workflow, *_, email_stub, order = build_workflow(
        opportunity=opportunity_outcome("research_more")
    )
    outcome = await workflow.handle(command())
    assert outcome.overall_status is OverallStatus.PARTIAL
    assert outcome.opportunity.action is StageStatus.RESEARCH_MORE
    assert email_stub.calls == 0
    assert order == ["company", "opportunity", "contact", "decision"]


async def test_missing_contact_returns_research_more() -> None:
    workflow, *_, contact_stub, decision_stub, email_stub, _order = build_workflow()
    outcome = await workflow.handle(command(with_contact=False))
    assert outcome.contact.action is StageStatus.RESEARCH_MORE
    assert outcome.decision_maker.action is StageStatus.RESEARCH_MORE
    assert contact_stub.calls == decision_stub.calls == email_stub.calls == 0


async def test_decision_maker_review_stops_email() -> None:
    workflow, *_, email_stub, _order = build_workflow(
        decision=decision_outcome(DecisionMakerSelectionAction.REVIEW)
    )
    outcome = await workflow.handle(command())
    assert outcome.decision_maker.action is StageStatus.REVIEW
    assert outcome.email_draft.action is StageStatus.SKIPPED
    assert email_stub.calls == 0


async def test_email_skip_is_completed_idempotent_result() -> None:
    workflow, *_ = build_workflow(email=email_outcome(EmailDraftAction.SKIPPED))
    outcome = await workflow.handle(command())
    assert outcome.overall_status is OverallStatus.COMPLETED
    assert outcome.email_draft.action is StageStatus.SKIPPED


async def test_provider_failure_returns_partial_and_preserves_upstream() -> None:
    workflow, *_ = build_workflow(
        email_error=EmailGenerationError("secret provider detail")
    )
    outcome = await workflow.handle(command())
    assert outcome.overall_status is OverallStatus.PARTIAL
    assert outcome.company.company_id == COMPANY_ID
    assert outcome.opportunity.opportunity_id == OPPORTUNITY_ID
    assert outcome.contact.contact_id == CONTACT_ID
    assert "secret provider detail" not in " ".join(outcome.email_draft.notes)


async def test_company_failure_stops_every_later_stage() -> None:
    workflow, _company, opportunity, contact, decision, email, order = build_workflow(
        company_error=RuntimeError("database broke")
    )
    outcome = await workflow.handle(command())
    assert outcome.overall_status is OverallStatus.FAILED
    assert order == ["company"]
    assert opportunity.calls == contact.calls == decision.calls == email.calls == 0


async def test_business_rejection_is_typed_not_exception() -> None:
    rejected = IngestionOutcome(
        status=IngestionStatus.REJECTED,
        company_id=None,
        notes=("unusable company name",),
    )
    workflow, *_ = build_workflow(company=rejected)
    outcome = await workflow.handle(command())
    assert outcome.overall_status is OverallStatus.REJECTED
    assert outcome.company.action is StageStatus.REJECTED


async def test_facade_maps_child_outcomes_without_recomputing_logic() -> None:
    workflow, *_ = build_workflow()
    outcome = await workflow.handle(command())
    assert outcome.opportunity.score == 81.0
    assert outcome.opportunity.reasons == ("child scorer reason",)
    assert outcome.decision_maker.reasons == ("child selection reason",)
    assert outcome.email_draft.subject == "Child-generated subject"
    assert outcome.email_draft.body == "Child-generated body"
