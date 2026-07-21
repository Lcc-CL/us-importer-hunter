"""Decision-maker policy: explainable, stable, honest about unknowns."""

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
from app.services.contact import (
    POLICY_VERSION,
    DeterministicDecisionMakerSelectionService,
)

FIXED_AT = datetime(2026, 7, 1, tzinfo=UTC)
COMPANY_ID = uuid4()


def make_contact(
    name: str,
    title: str | None,
    department: Department,
    seniority: SeniorityLevel,
    *,
    email: str | None = None,
    verified: bool = False,
    linkedin: str | None = None,
) -> Contact:
    source = SourceReference(source="importyeti", reference="https://r/1", retrieved_at=FIXED_AT)
    contact = Contact.create_for_company(
        COMPANY_ID, PersonName(name), JobTitle(title) if title else None
    )
    contact.classify_role(department, seniority)
    contact.add_source(source)
    if email:
        contact.add_channel(
            ContactChannel(
                channel_type=ContactChannelType.EMAIL,
                normalized_value=email,
                display_value=email,
                source_reference=source,
            )
        )
        if verified:
            contact.verify_channel(ContactChannelType.EMAIL, email)
    if linkedin:
        contact.add_channel(
            ContactChannel(
                channel_type=ContactChannelType.LINKEDIN,
                normalized_value=linkedin,
                display_value=linkedin,
                source_reference=source,
            )
        )
    contact.drain_events()
    return contact


SERVICE = DeterministicDecisionMakerSelectionService()


class TestRanking:
    async def test_logistics_director_beats_marketing_and_ceo(self) -> None:
        logistics = make_contact(
            "Lena Logistics", "Logistics Director", Department.LOGISTICS,
            SeniorityLevel.DIRECTOR, email="l@x.com",
        )
        ceo = make_contact(
            "Cathy CEO", "CEO", Department.EXECUTIVE, SeniorityLevel.C_LEVEL, email="c@x.com"
        )
        marketing = make_contact(
            "Mark Marketing", "Marketing Manager", Department.SALES_MARKETING,
            SeniorityLevel.MANAGER, email="m@x.com",
        )
        ranked = await SERVICE.rank([marketing, ceo, logistics])
        assert [a.contact_id for a in ranked] == [logistics.id, ceo.id, marketing.id]

    async def test_director_outranks_specialist_same_department(self) -> None:
        director = make_contact(
            "Dana Director", "Supply Chain Director", Department.SUPPLY_CHAIN,
            SeniorityLevel.DIRECTOR, email="d@x.com",
        )
        specialist = make_contact(
            "Sam Specialist", "Supply Chain Specialist", Department.SUPPLY_CHAIN,
            SeniorityLevel.SPECIALIST, email="s@x.com",
        )
        ranked = await SERVICE.rank([specialist, director])
        assert ranked[0].contact_id == director.id

    async def test_ranking_is_stable_and_deterministic(self) -> None:
        contacts = [
            make_contact(f"Person {i}", "Logistics Manager", Department.LOGISTICS,
                         SeniorityLevel.MANAGER, email=f"p{i}@x.com")
            for i in range(5)
        ]
        first = await SERVICE.rank(contacts)
        second = await SERVICE.rank(list(reversed(contacts)))
        assert [a.contact_id for a in first] == [a.contact_id for a in second]


class TestReachability:
    async def test_verified_email_beats_unverified(self) -> None:
        verified = make_contact(
            "Vera Verified", "Logistics Manager", Department.LOGISTICS,
            SeniorityLevel.MANAGER, email="v@x.com", verified=True,
        )
        unverified = make_contact(
            "Uma Unverified", "Logistics Manager", Department.LOGISTICS,
            SeniorityLevel.MANAGER, email="u@x.com",
        )
        ranked = await SERVICE.rank([unverified, verified])
        assert ranked[0].contact_id == verified.id
        assert ranked[0].reachability_score > ranked[1].reachability_score
        assert ranked[0].recommended_channel is ContactChannelType.EMAIL

    async def test_no_channels_is_low_reachability_not_invalid(self) -> None:
        unreachable = make_contact(
            "Nora NoChannel", "Logistics Director", Department.LOGISTICS,
            SeniorityLevel.DIRECTOR,
        )
        (assessment,) = await SERVICE.rank([unreachable])
        assert assessment.reachability_score == 0.0
        assert assessment.role_fit_score > 35.0  # logistics director: 38-40 in six-factor
        assert any("reachability=0" in reason for reason in assessment.reasons)

    async def test_unknown_department_is_not_negative(self) -> None:
        unknown = make_contact("Uma Unknown", None, Department.UNKNOWN, SeniorityLevel.UNKNOWN)
        (assessment,) = await SERVICE.rank([unknown])
        assert assessment.role_fit_score >= 0.0  # unknown is neutral, not negative
        assert assessment.confidence.value <= 0.6  # thin data → low confidence, not zero value
        assert any("role_relevance" in reason for reason in assessment.reasons)


class TestPolicyVersioning:
    async def test_assessments_carry_policy_version_and_evidence(self) -> None:
        contact = make_contact(
            "Lena Logistics", "Logistics Director", Department.LOGISTICS,
            SeniorityLevel.DIRECTOR, email="l@x.com",
        )
        (assessment,) = await SERVICE.rank([contact])
        assert assessment.policy_version == POLICY_VERSION == "mvp-decision-maker-policy-v2"
        assert assessment.evidence and assessment.evidence[0].sources
        assert len(assessment.assessment_fingerprint) == 64

    async def test_different_policy_versions_are_distinguishable(self) -> None:
        contact = make_contact(
            "Lena Logistics", "Logistics Director", Department.LOGISTICS,
            SeniorityLevel.DIRECTOR, email="l@x.com",
        )

        class StricterPolicy(DeterministicDecisionMakerSelectionService):
            @property
            def policy_version(self) -> str:
                return "mvp-decision-maker-policy-v3-test"

        (v1,) = await SERVICE.rank([contact])
        (v2,) = await StricterPolicy().rank([contact])
        assert v1.policy_version != v2.policy_version
        assert v1.assessment_fingerprint != v2.assessment_fingerprint
