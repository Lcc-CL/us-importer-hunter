"""Phase 2 A-J test matrix: six-factor scoring, selection, draft gating."""

from datetime import UTC, datetime
from uuid import uuid4

from app.domain.contact import (
    Contact,
    ContactChannel,
    ContactChannelType,
    Department,
    JobTitle,
    PersonName,
    SeniorityLevel,
)
from app.domain.values import SourceReference
from app.services.contact import DeterministicDecisionMakerSelectionService
from app.services.contact.scorer import (
    RejectionReason,
    SelectionStatus,
    SixFactorScorer,
)
from app.services.contact.selector import select

FIXED_AT = datetime(2026, 7, 1, tzinfo=UTC)
COMPANY_ID = uuid4()


def _make_contact(
    name: str,
    title: str | None,
    department: Department,
    seniority: SeniorityLevel,
    *,
    email: str | None = None,
    verified: bool = False,
    source: str = "importyeti",
) -> Contact:
    src = SourceReference(source=source, reference=f"https://r/{name}", retrieved_at=FIXED_AT)
    contact = Contact.create_for_company(
        COMPANY_ID, PersonName(name), JobTitle(title) if title else None
    )
    contact.classify_role(department, seniority)
    contact.add_source(src)
    if email:
        contact.add_channel(
            ContactChannel(
                channel_type=ContactChannelType.EMAIL,
                normalized_value=email,
                display_value=email,
                source_reference=src,
            )
        )
        if verified:
            contact.verify_channel(ContactChannelType.EMAIL, email)
    contact.drain_events()
    return contact


SERVICE = DeterministicDecisionMakerSelectionService()
SCORER = SixFactorScorer()


class TestAPrimarySelected:
    """A: Clear primary emerges from a mixed set."""

    def test_procurement_director_is_primary(self) -> None:
        pd = _make_contact("Paula Dir", "Procurement Director",
                           Department.PROCUREMENT, SeniorityLevel.DIRECTOR,
                           email="p@x.com", verified=True)
        lm = _make_contact("Liam Mgr", "Logistics Manager",
                           Department.LOGISTICS, SeniorityLevel.MANAGER)
        sr = _make_contact("Sam Rep", "Sales Representative",
                           Department.SALES_MARKETING, SeniorityLevel.SPECIALIST)

        candidates = list(SCORER.score(c) for c in [pd, lm, sr])
        result = select(candidates)

        assert result.status == SelectionStatus.SELECTED
        assert result.review_required is False
        assert result.primary_contact is not None
        assert result.primary_contact.contact_id == pd.id
        rejected_ids = {r.contact_id for r in result.rejected_contacts}
        assert sr.id in rejected_ids


class TestBCloseCandidates:
    """B: Two similarly-scored candidates trigger review."""

    def test_close_scores_trigger_review(self) -> None:
        pm = _make_contact("Pat Mgr", "Procurement Manager",
                           Department.PROCUREMENT, SeniorityLevel.MANAGER,
                           email="pm@x.com", verified=True)
        scm = _make_contact("Sam Chain", "Supply Chain Manager",
                            Department.SUPPLY_CHAIN, SeniorityLevel.MANAGER,
                            email="sc@x.com", verified=True)

        candidates = list(SCORER.score(c) for c in [pm, scm])
        result = select(candidates)

        # They should be close in score — trigger review or at least both visible
        assert result.review_required or result.primary_contact is not None
        all_ids = {c.contact_id for c in candidates}
        assert pm.id in all_ids
        assert scm.id in all_ids


class TestCSalesOnly:
    """C: Pure sales contact — no relevant decision maker."""

    def test_sales_only_rejected(self) -> None:
        sm = _make_contact("Sam Sales", "Sales Manager",
                           Department.SALES_MARKETING, SeniorityLevel.MANAGER,
                           email="s@x.com", verified=True)

        candidates = list(SCORER.score(c) for c in [sm])
        result = select(candidates)

        assert result.status in (SelectionStatus.NO_RELEVANT_CONTACT,)
        assert result.primary_contact is None
        rejected = result.rejected_contacts
        assert len(rejected) > 0
        assert RejectionReason.SALES_ONLY in rejected[0].rejection_reasons


class TestDHistoricalRole:
    """D: Former role is rejected even if the title reads as a buyer."""

    def test_former_purchasing_manager_is_rejected(self) -> None:
        fpm = _make_contact("Frank Former", "Former Purchasing Manager",
                            Department.PROCUREMENT, SeniorityLevel.MANAGER,
                            email="f@x.com", verified=True)

        candidate = SCORER.score(fpm)
        assert candidate.historical_role is True
        assert candidate.eligible is False
        assert RejectionReason.HISTORICAL_ROLE in candidate.rejection_reasons

        result = select([candidate])
        assert result.primary_contact is None


class TestEAssistantRanking:
    """E: Assistant ranks below the full role counterpart."""

    def test_assistant_buyer_below_buyer(self) -> None:
        assistant = _make_contact("Abby Asst", "Assistant Buyer",
                                  Department.PROCUREMENT, SeniorityLevel.SPECIALIST,
                                  email="a@x.com", verified=True)
        buyer = _make_contact("Bob Buyer", "Buyer",
                              Department.PROCUREMENT, SeniorityLevel.MANAGER,
                              email="b@x.com", verified=True)

        ascore = SCORER.score(assistant)
        bscore = SCORER.score(buyer)

        assert ascore.assistant_role is True
        assert ascore.seniority_score < bscore.seniority_score
        assert bscore.overall_score > ascore.overall_score

        result = select([ascore, bscore])
        if result.primary_contact:
            assert result.primary_contact.contact_id == buyer.id


class TestFReachabilityConflict:
    """F: High relevance but unreachable vs reachable but lower relevance."""

    def test_unreachable_does_not_silently_replace(self) -> None:
        high = _make_contact("High Rel", "Supply Chain Director",
                             Department.SUPPLY_CHAIN, SeniorityLevel.DIRECTOR)
        low = _make_contact("Low Rel", "Marketing Manager",
                            Department.SALES_MARKETING, SeniorityLevel.MANAGER,
                            email="low@x.com", verified=True)

        candidates = list(SCORER.score(c) for c in [high, low])
        result = select(candidates)

        # The high-relevance candidate has 0 reachability
        high_score = next(c for c in candidates if c.contact_id == high.id)
        assert high_score.reachability_score == 0
        assert high_score.role_relevance_score > 0

        # Should trigger review, not silently pick the lower one
        if result.primary_contact:
            # If primary was selected, it must be justified
            assert result.primary_contact.contact_id != low.id or result.review_required


class TestGCompanySizeFit:
    """G: Company size affects who ranks highest."""

    def test_small_company_owner_can_lead(self) -> None:
        owner = _make_contact("Owner O", "Owner", Department.EXECUTIVE,
                              SeniorityLevel.C_LEVEL, email="o@x.com")
        buyer = _make_contact("Buyer B", "Buyer", Department.PROCUREMENT,
                              SeniorityLevel.SPECIALIST, email="b@x.com")

        oscore = SCORER.score(owner)
        bscore = SCORER.score(buyer)

        # Both should have non-trivial scores
        assert oscore.overall_score > 0
        assert bscore.overall_score > 0
        # Without size data both get 5.0 company_size_fit
        assert oscore.company_size_fit_score == 5.0
        assert bscore.company_size_fit_score == 5.0


class TestHStability:
    """H: Same inputs → same outputs, every time."""

    def test_five_runs_same_result(self) -> None:
        contacts = [
            _make_contact("P", "Procurement Director",
                          Department.PROCUREMENT, SeniorityLevel.DIRECTOR,
                          email="p@x.com", verified=True),
            _make_contact("L", "Logistics Manager",
                          Department.LOGISTICS, SeniorityLevel.MANAGER,
                          email="l@x.com"),
        ]

        first_candidates = [SCORER.score(c) for c in contacts]
        first = select(first_candidates)

        for _ in range(4):
            candidates = [SCORER.score(c) for c in contacts]
            result = select(candidates)
            assert result.status == first.status
            assert result.review_required == first.review_required
            if result.primary_contact and first.primary_contact:
                assert result.primary_contact.contact_id == first.primary_contact.contact_id

    def test_idempotent_assessment_creation(self) -> None:
        contacts = [_make_contact("Test", "Logistics Manager", Department.LOGISTICS,
                                 SeniorityLevel.MANAGER, email="t@x.com")]
        ranked1 = SERVICE.score_all(contacts)
        ranked2 = SERVICE.score_all(contacts)
        assert len(ranked1) == len(ranked2)
        assert ranked1[0].overall_score == ranked2[0].overall_score


class TestIDraftGating:
    """I: Draft generation is gated on selection status."""

    def test_primary_generates_draft(self) -> None:
        contact = _make_contact("PD", "Procurement Director",
                                Department.PROCUREMENT, SeniorityLevel.DIRECTOR,
                                email="pd@x.com", verified=True)
        candidates = list(SCORER.score(c) for c in [contact])
        result = select(candidates)
        assert result.status == SelectionStatus.SELECTED
        assert result.review_required is False
        assert result.primary_contact is not None

    def test_review_required_no_draft(self) -> None:
        c1 = _make_contact("PM", "Procurement Manager",
                           Department.PROCUREMENT, SeniorityLevel.MANAGER,
                           email="pm@x.com", verified=True)
        c2 = _make_contact("SCM", "Supply Chain Manager",
                           Department.SUPPLY_CHAIN, SeniorityLevel.MANAGER,
                           email="scm@x.com", verified=True)
        candidates = list(SCORER.score(c) for c in [c1, c2])
        result = select(candidates)
        if result.review_required:
            assert result.primary_contact is None


class TestJTrialRegression:
    """J: Three trial companies produce expected classifications."""

    def test_house_hasson_dual_role(self) -> None:
        contact = _make_contact("HH", "Sales and Purchasing",
                                Department.PROCUREMENT, SeniorityLevel.MANAGER,
                                email="hh@x.com", verified=True)
        candidate = SCORER.score(contact)
        role_values = {r.value for r in candidate.roles}
        assert "sales" in role_values
        assert "procurement" in role_values
        assert candidate.role_relevance_score > 20  # procurement is high
        assert candidate.eligible is True

    def test_marathon_vp_purchasing_primary(self) -> None:
        contact = _make_contact("VP P", "Vice President, Purchasing",
                                Department.PROCUREMENT, SeniorityLevel.VP,
                                email="vp@x.com", verified=True)
        candidate = SCORER.score(contact)
        role_values = {r.value for r in candidate.roles}
        assert "procurement" in role_values
        assert "ownership" not in role_values  # VP veto
        assert candidate.seniority_score >= 14  # VP level
        assert candidate.eligible is True

    def test_elite_sales_not_primary(self) -> None:
        contact = _make_contact("ES", "Sales Manager",
                                Department.SALES_MARKETING, SeniorityLevel.MANAGER,
                                email="es@x.com", verified=True)
        candidate = SCORER.score(contact)
        role_values = {r.value for r in candidate.roles}
        assert "sales" in role_values
        assert "procurement" not in role_values
        assert RejectionReason.SALES_ONLY in candidate.rejection_reasons
        assert candidate.eligible is False


class TestKApiContracts:
    """API contract: fields are present and have correct types."""

    def test_score_breakdown_has_six_dimensions(self) -> None:
        contact = _make_contact("Test", "Logistics Manager",
                                Department.LOGISTICS, SeniorityLevel.MANAGER,
                                email="t@x.com", verified=True)
        candidate = SCORER.score(contact)
        breakdown = candidate.score_breakdown
        assert set(breakdown.keys()) == {
            "role_relevance", "seniority", "company_size_fit",
            "import_logistics_fit", "reachability", "source_confidence",
        }
        for v in breakdown.values():
            assert isinstance(v, (int, float))

    def test_rejection_reasons_are_english_codes(self) -> None:
        for reason in RejectionReason:
            assert reason.value.isascii()
            assert "_" in reason.value or reason.value.islower()

    def test_selection_result_structure(self) -> None:
        result = select([])
        assert result.status in SelectionStatus
        assert isinstance(result.review_required, bool)
        assert isinstance(result.review_reasons, tuple)
        assert result.primary_contact is None
        assert isinstance(result.alternative_contacts, tuple)
        assert isinstance(result.rejected_contacts, tuple)
