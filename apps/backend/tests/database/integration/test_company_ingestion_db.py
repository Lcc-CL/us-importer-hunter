"""End-to-end ingestion against real PostgreSQL: claim → normalize →
dedup → create/merge → committed rows, through the real Unit of Work."""

from datetime import UTC, datetime
from uuid import uuid4

from app.domain.discovery import DiscoveryResult, RawCompanySnapshot, Signal
from app.domain.events import CompanyDiscovered
from app.domain.values import CompanyName, SourceReference
from app.workflows.company_ingestion import CompanyIngestionWorkflow, IngestionStatus
from tests.database.integration.conftest import UowFactory


def make_event(name_text: str, reference: str) -> CompanyDiscovered:
    snapshot = RawCompanySnapshot(
        name_text=name_text,
        source=SourceReference(
            source="importyeti",
            reference=reference,
            retrieved_at=datetime(2026, 7, 1, tzinfo=UTC),
        ),
        website_text="eastlineapparel.com",
    )
    return CompanyDiscovered(
        run_id=uuid4(),
        result=DiscoveryResult(
            snapshot=snapshot,
            signals=(Signal(kind="volume_trend", detail="growing"),),
        ),
    )


class TestIngestionEndToEnd:
    async def test_create_then_merge_through_real_uow(self, uow_factory: UowFactory) -> None:
        workflow = CompanyIngestionWorkflow(uow_factory=uow_factory)

        created = await workflow.handle(make_event("Eastline Apparel Group", "https://ref/1"))
        assert created.status is IngestionStatus.CREATED

        merged = await workflow.handle(make_event("EASTLINE APPAREL GROUP LLC", "https://ref/2"))
        assert merged.status is IngestionStatus.MERGED
        assert merged.company_id == created.company_id

        async with uow_factory() as uow:
            assert created.company_id is not None
            company = await uow.companies.get_by_id(created.company_id)
        assert company is not None
        assert CompanyName("EASTLINE APPAREL GROUP LLC") in company.aliases
        assert len(company.sources) == 2
        assert "volume_trend: growing" in company.signals

    async def test_find_by_website_host(self, uow_factory: UowFactory) -> None:
        workflow = CompanyIngestionWorkflow(uow_factory=uow_factory)
        created = await workflow.handle(make_event("Eastline Apparel Group", "https://ref/1"))
        async with uow_factory() as uow:
            found = await uow.companies.find_by_website_host("eastlineapparel.com")
            missing = await uow.companies.find_by_website_host("nobody.example")
        assert found is not None and found.id == created.company_id
        assert missing is None
