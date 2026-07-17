"""Email draft persistence against real PostgreSQL: full-chain round-trip
and the context-fingerprint unique backstop."""

from uuid import UUID, uuid4

import pytest

from app.domain.exceptions import DuplicateOperation
from app.domain.opportunity import Opportunity
from app.domain.outreach import EmailDraftStatus, Outreach
from app.domain.services import SenderProfile
from app.services.email import FakeEmailDraftGenerator
from app.workflows.email import EmailDraftAction, EmailDraftGenerationWorkflow
from tests.database.integration.conftest import UowFactory
from tests.database.integration.test_contact_db import persist_contact
from tests.workflows.test_email_draft import make_assessment

SENDER = SenderProfile(
    name="Alex Liu",
    company="Eastbridge Freight",
    value_proposition="We run weekly FCL consolidations from Shanghai to LA.",
)


async def seed_chain(uow_factory: UowFactory) -> tuple[Opportunity, UUID]:
    contact = await persist_contact(uow_factory)  # persists company + ACTIVE contact
    opportunity = Opportunity.create_for_company(contact.company_id, uuid4())
    opportunity.apply_assessment(make_assessment())
    opportunity.drain_events()
    async with uow_factory() as uow:
        await uow.opportunities.add(opportunity)
        await uow.commit()
    return opportunity, contact.id


class TestEmailDraftEndToEnd:
    async def test_generate_and_reload(self, uow_factory: UowFactory) -> None:
        opportunity, contact_id = await seed_chain(uow_factory)
        workflow = EmailDraftGenerationWorkflow(
            uow_factory=uow_factory, generator=FakeEmailDraftGenerator()
        )
        outcome = await workflow.handle(
            opportunity_id=opportunity.id, contact_id=contact_id, sender=SENDER
        )
        assert outcome.action is EmailDraftAction.GENERATED

        async with uow_factory() as uow:
            assert outcome.outreach_id is not None
            stored = await uow.outreaches.get_by_id(outcome.outreach_id)
        assert stored is not None
        draft = stored.drafts[0]
        assert draft.status is EmailDraftStatus.GENERATED
        assert draft.provider == "fake"
        assert draft.prompt_version == "first-outreach-v1"
        assert len(draft.context_fingerprint) == 64
        assert stored.drain_events() == ()  # reload never revives events

        replay = await workflow.handle(
            opportunity_id=opportunity.id, contact_id=contact_id, sender=SENDER
        )
        assert replay.action is EmailDraftAction.SKIPPED

    async def test_db_rejects_duplicate_context_prompt(self, uow_factory: UowFactory) -> None:
        """Bypass the aggregate guard by adding the same fingerprint to two
        separate model rows — the partial unique index is the backstop."""
        opportunity, contact_id = await seed_chain(uow_factory)
        outreach = Outreach.create(opportunity.id)
        outreach.attach_contact(contact_id)
        outreach.add_draft("S1", "B1", "first-outreach-v1", context_fingerprint="f" * 64)
        object.__setattr__(outreach.drafts[0], "context_fingerprint", "f" * 64)
        outreach.drain_events()
        async with uow_factory() as uow:
            await uow.outreaches.add(outreach)
            await uow.commit()

        # second outreach row for the same conversation cannot reuse the pair
        # (per-outreach index) — simulate by appending a manually forged draft
        async with uow_factory() as uow:
            loaded = await uow.outreaches.get_by_id(outreach.id)
            assert loaded is not None
            forged = loaded.add_draft(
                "S2", "B2", "first-outreach-v1", context_fingerprint="g" * 64
            )
            object.__setattr__(forged, "context_fingerprint", "f" * 64)
            await uow.outreaches.save(loaded)
            with pytest.raises(DuplicateOperation):
                await uow.commit()
