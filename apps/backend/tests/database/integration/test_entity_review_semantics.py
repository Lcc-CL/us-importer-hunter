"""D5e2g.1 review decision semantics safety tests.

Covers the four human review actions on real PostgreSQL:

- DEFER is the absence of an API action: nothing is written and the decision
  stays pending across refresh.
- REJECT rejects only the row-to-candidate match; it never deletes raw rows,
  canonical companies/contacts, or employment links.
- KEEP_SEPARATE persists a separate canonical entity and, when the source has
  a stable external id, prevents the same candidate from recurring on
  re-import.
- MERGE persists and is idempotent.

Also covers department-mailbox safety and the routing-preview gate that keeps
companies blocked while entity reviews are pending.
"""

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import cast
from uuid import UUID

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.api.deps import get_uow_factory
from app.core.config import Settings
from app.database.models.bulk_import import RawImportRowModel
from app.database.models.company import CompanyModel
from app.database.models.contact import ContactModel
from app.database.models.import_resolution import (
    CompanyContactModel,
    ImportEntityDecisionModel,
)
from app.main import create_app
from app.workflows.import_resolution import (
    ImportEntityResolutionWorkflow,
    ImportProcessingJobCoordinator,
    ImportProcessingJobRunner,
)
from tests.database.integration.conftest import UowFactory

MAPPING = (
    '{"company_name":"company","external_company_id":"external_id",'
    '"website":"website","address":"address","company_type":"company_type",'
    '"contact_name":"contact","contact_email":"email","contact_title":"title",'
    '"product_description":"product","hs_code":"hs","shipment_date":"date",'
    '"origin_country":"origin","pol":"pol","pod":"pod"}'
)
DEFAULT_HEADER = (
    "company,external_id,website,address,company_type,contact,email,title,"
    "product,hs,date,origin,pol,pod"
)


async def make_client(uow_factory: UowFactory) -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(_env_file=None, app_env="development"))
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


def make_runner(uow_factory: UowFactory) -> ImportProcessingJobRunner:
    coordinator = ImportProcessingJobCoordinator(
        uow_factory,
        lease_ttl=timedelta(seconds=120),
        retry_delay=timedelta(0),
    )
    return ImportProcessingJobRunner(
        coordinator=coordinator,
        workflow=ImportEntityResolutionWorkflow(uow_factory),
    )


async def upload(
    client: AsyncClient,
    *,
    filename: str,
    rows: str,
    mapping: str = MAPPING,
    header: str = DEFAULT_HEADER,
    source: str = "netease_foreign_trade",
) -> str:
    response = await client.post(
        "/api/v1/import-sessions",
        data={"source": source, "mapping": mapping},
        files={
            "file": (
                filename,
                (f"{header}\n{rows}").encode(),
                "text/csv",
            )
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["session_id"])


async def submit_and_run(
    client: AsyncClient,
    runner: ImportProcessingJobRunner,
    session_id: str,
) -> dict[str, object]:
    submitted = await client.post(f"/api/v1/import-sessions/{session_id}/resolve")
    assert submitted.status_code == 202, submitted.text
    assert await runner.run_once(owner=f"worker-{session_id}") is True
    result = await client.get(f"/api/v1/import-sessions/{session_id}/resolution")
    assert result.status_code == 200, result.text
    return cast(dict[str, object], result.json())


async def decisions(client: AsyncClient, session_id: str) -> list[dict[str, object]]:
    response = await client.get(
        f"/api/v1/import-sessions/{session_id}/entity-decisions",
        params={"limit": 100},
    )
    assert response.status_code == 200, response.text
    return list(response.json()["decisions"])


async def review(
    client: AsyncClient,
    decision_id: str,
    action: str,
) -> dict[str, object]:
    response = await client.post(
        f"/api/v1/import-entity-decisions/{decision_id}/review",
        json={"action": action, "reviewed_by": "qa"},
    )
    assert response.status_code == 200, response.text
    return cast(dict[str, object], response.json())


async def test_defer_leaves_canonical_entities_and_pending_state_untouched(
    uow_factory: UowFactory,
) -> None:
    """DEFER has no API action: nothing is written and refresh keeps pending."""
    runner = make_runner(uow_factory)
    async for client in make_client(uow_factory):
        base_id = await upload(
            client,
            filename="defer-base.csv",
            rows=(
                "Atlas Hardware Inc,DEFER-BASE,atlas.example,100 Main St Austin TX,"
                "importer,Maria Chen,maria@atlas.example,Director Logistics,"
                "industrial hardware,8205.40,2026-07-01,China,Shanghai,Los Angeles\n"
            ),
        )
        await submit_and_run(client, runner, base_id)

        conflict_id = await upload(
            client,
            filename="defer-conflict.csv",
            rows=(
                "Atlas Hardware LLC,DEFER-CONFLICT,atlas.example,"
                "900 Ocean Dr Miami FL,warehouse,"
                "Pat Lee,pat@defer.example,Procurement Manager,"
                "furniture,9401,2026-07-20,Vietnam,Ho Chi Minh,Long Beach\n"
            ),
        )
        conflict = await submit_and_run(client, runner, conflict_id)
        assert conflict["company_reviews_required"] == 1
        pending = await decisions(client, conflict_id)
        assert len(pending) == 2  # one company review + one contact auto_create
        company_decision = next(
            item for item in pending if item["entity_type"] == "company"
        )
        assert company_decision["review_status"] == "pending"
        candidate_id = company_decision["candidate_entity_id"]

        async with uow_factory() as uow:
            assert uow._session is not None  # noqa: SLF001
            company_count = await uow._session.scalar(  # noqa: SLF001
                select(func.count()).select_from(CompanyModel)
            )
            raw_count = await uow._session.scalar(  # noqa: SLF001
                select(func.count()).select_from(RawImportRowModel)
            )

        # DEFER means "do nothing": there is no defer endpoint. Re-querying the
        # decision after a fresh UOW must return the exact same pending state.
        after_refresh = await decisions(client, conflict_id)
        refreshed = next(
            item for item in after_refresh if item["entity_type"] == "company"
        )
        assert refreshed["review_status"] == "pending"
        assert refreshed["decision"] == "review_required"
        assert refreshed["candidate_entity_id"] == candidate_id

        async with uow_factory() as uow:
            assert uow._session is not None  # noqa: SLF001
            assert (
                await uow._session.scalar(  # noqa: SLF001
                    select(func.count()).select_from(CompanyModel)
                )
                == company_count
            )
            assert (
                await uow._session.scalar(  # noqa: SLF001
                    select(func.count()).select_from(RawImportRowModel)
                )
                == raw_count
            )


async def test_reject_rejects_only_candidate_match_and_never_deletes_data(
    uow_factory: UowFactory,
) -> None:
    runner = make_runner(uow_factory)
    async for client in make_client(uow_factory):
        base_id = await upload(
            client,
            filename="reject-base.csv",
            rows=(
                "Atlas Hardware Inc,REJ-BASE,atlas.example,100 Main St Austin TX,"
                "importer,Maria Chen,maria@atlas.example,Director Logistics,"
                "industrial hardware,8205.40,2026-07-01,China,Shanghai,Los Angeles\n"
            ),
        )
        base = await submit_and_run(client, runner, base_id)
        assert base["company_reviews_required"] == 0

        conflict_id = await upload(
            client,
            filename="reject-conflict.csv",
            rows=(
                "Atlas Hardware LLC,REJ-CONFLICT,atlas.example,"
                "900 Ocean Dr Miami FL,warehouse,"
                "Pat Lee,pat@reject.example,Procurement Manager,"
                "furniture,9401,2026-07-20,Vietnam,Ho Chi Minh,Long Beach\n"
            ),
        )
        conflict = await submit_and_run(client, runner, conflict_id)
        assert conflict["company_reviews_required"] == 1
        company_decision = next(
            item
            for item in await decisions(client, conflict_id)
            if item["entity_type"] == "company"
        )

        async with uow_factory() as uow:
            assert uow._session is not None  # noqa: SLF001
            companies_before = await uow._session.scalar(  # noqa: SLF001
                select(func.count()).select_from(CompanyModel)
            )
            contacts_before = await uow._session.scalar(  # noqa: SLF001
                select(func.count()).select_from(ContactModel)
            )
            raw_before = await uow._session.scalar(  # noqa: SLF001
                select(func.count()).select_from(RawImportRowModel)
            )
            links_before = await uow._session.scalar(  # noqa: SLF001
                select(func.count()).select_from(CompanyContactModel)
            )

        rejected = await review(
            client, str(company_decision["decision_id"]), "reject"
        )
        assert rejected["decision"] == "rejected"
        assert rejected["review_status"] == "reviewed"
        assert rejected["candidate_entity_id"] is None

        after = await client.get(f"/api/v1/import-sessions/{conflict_id}/resolution")
        assert after.status_code == 200
        assert after.json()["company_reviews_required"] == 0

        # REJECT only records the decision; no source or canonical data changes.
        async with uow_factory() as uow:
            assert uow._session is not None  # noqa: SLF001
            assert (
                await uow._session.scalar(  # noqa: SLF001
                    select(func.count()).select_from(CompanyModel)
                )
                == companies_before
            )
            assert (
                await uow._session.scalar(  # noqa: SLF001
                    select(func.count()).select_from(ContactModel)
                )
                == contacts_before
            )
            assert (
                await uow._session.scalar(  # noqa: SLF001
                    select(func.count()).select_from(RawImportRowModel)
                )
                == raw_before
            )
            assert (
                await uow._session.scalar(  # noqa: SLF001
                    select(func.count()).select_from(CompanyContactModel)
                )
                == links_before
            )
            persisted = await uow._session.get(  # noqa: SLF001
                ImportEntityDecisionModel,
                UUID(str(company_decision["decision_id"])),
            )
            assert persisted is not None
            assert persisted.decision == "rejected"
            assert persisted.review_status == "reviewed"
            assert persisted.candidate_entity_id is None

        # Refresh: the rejected decision is stable and no longer pending.
        refreshed = await decisions(client, conflict_id)
        assert all(
            item["review_status"] in {"reviewed", "not_required"}
            for item in refreshed
        )


async def test_keep_separate_persists_and_prevents_recurring_candidate_on_reimport(
    uow_factory: UowFactory,
) -> None:
    runner = make_runner(uow_factory)
    async for client in make_client(uow_factory):
        base_id = await upload(
            client,
            filename="separate-base.csv",
            rows=(
                "Atlas Hardware Inc,SEP-BASE,atlas.example,100 Main St Austin TX,"
                "importer,Maria Chen,maria@atlas.example,Director Logistics,"
                "industrial hardware,8205.40,2026-07-01,China,Shanghai,Los Angeles\n"
            ),
        )
        await submit_and_run(client, runner, base_id)

        conflict_id = await upload(
            client,
            filename="separate-conflict.csv",
            rows=(
                "Atlas Hardware LLC,SEP-CONFLICT,atlas.example,"
                "900 Ocean Dr Miami FL,warehouse,"
                "Pat Lee,pat@separate.example,Procurement Manager,"
                "furniture,9401,2026-07-20,Vietnam,Ho Chi Minh,Long Beach\n"
            ),
        )
        conflict = await submit_and_run(client, runner, conflict_id)
        assert conflict["company_reviews_required"] == 1
        company_decision = next(
            item
            for item in await decisions(client, conflict_id)
            if item["entity_type"] == "company"
        )

        kept = await review(
            client, str(company_decision["decision_id"]), "keep_separate"
        )
        assert kept["decision"] == "keep_separate"
        assert kept["review_status"] == "reviewed"
        separate_id = UUID(str(kept["candidate_entity_id"]))

        # A fresh canonical company now exists and the decision persists.
        async with uow_factory() as uow:
            assert uow._session is not None  # noqa: SLF001
            separate_company = await uow._session.get(  # noqa: SLF001
                CompanyModel, separate_id
            )
            assert separate_company is not None
            assert separate_company.name == "Atlas Hardware LLC"
            persisted = await uow._session.get(  # noqa: SLF001
                ImportEntityDecisionModel,
                UUID(str(company_decision["decision_id"])),
            )
            assert persisted is not None
            assert persisted.decision == "keep_separate"
            assert persisted.candidate_entity_id == separate_id

        after_refresh = await decisions(client, conflict_id)
        assert all(
            item["review_status"] in {"reviewed", "not_required"}
            for item in after_refresh
        )

        # Re-importing the identical row reuses the separate company through the
        # stable external id; the same candidate is not proposed again.
        reimport_id = await upload(
            client,
            filename="separate-reimport.csv",
            rows=(
                "Atlas Hardware LLC,SEP-CONFLICT,atlas.example,"
                "900 Ocean Dr Miami FL,warehouse,"
                "Pat Lee,pat@separate.example,Procurement Director,"
                "furniture,9401,2026-07-20,Vietnam,Ho Chi Minh,Long Beach\n"
            ),
        )
        reimport = await submit_and_run(client, runner, reimport_id)
        assert reimport["company_reviews_required"] == 0
        assert reimport["companies_reused"] == 1


async def test_merge_is_persisted_and_idempotent(
    uow_factory: UowFactory,
) -> None:
    runner = make_runner(uow_factory)
    async for client in make_client(uow_factory):
        base_id = await upload(
            client,
            filename="merge-base.csv",
            rows=(
                "Atlas Hardware Inc,MERGE-BASE,atlas.example,100 Main St Austin TX,"
                "importer,Maria Chen,maria@atlas.example,Director Logistics,"
                "industrial hardware,8205.40,2026-07-01,China,Shanghai,Los Angeles\n"
            ),
        )
        await submit_and_run(client, runner, base_id)

        conflict_id = await upload(
            client,
            filename="merge-conflict.csv",
            rows=(
                "Atlas Hardware LLC,MERGE-CONFLICT,atlas.example,"
                "900 Ocean Dr Miami FL,warehouse,"
                "Pat Lee,pat@merge.example,Procurement Manager,"
                "furniture,9401,2026-07-20,Vietnam,Ho Chi Minh,Long Beach\n"
            ),
        )
        conflict = await submit_and_run(client, runner, conflict_id)
        assert conflict["company_reviews_required"] == 1
        company_decision = next(
            item
            for item in await decisions(client, conflict_id)
            if item["entity_type"] == "company"
        )
        decision_id = str(company_decision["decision_id"])
        candidate_id = company_decision["candidate_entity_id"]

        first = await review(client, decision_id, "merge")
        assert first["decision"] == "manual_merge"
        assert first["candidate_entity_id"] == candidate_id
        second = await review(client, decision_id, "merge")
        assert second["decision"] == "manual_merge"

        async with uow_factory() as uow:
            assert uow._session is not None  # noqa: SLF001
            count = await uow._session.scalar(  # noqa: SLF001
                select(func.count())
                .select_from(ImportEntityDecisionModel)
                .where(
                    ImportEntityDecisionModel.import_session_id
                    == UUID(conflict_id),
                    ImportEntityDecisionModel.raw_import_row_id
                    == UUID(str(company_decision["raw_import_row_id"])),
                    ImportEntityDecisionModel.entity_type == "company",
                )
            )
            assert count == 1

        after = await client.get(f"/api/v1/import-sessions/{conflict_id}/resolution")
        assert after.json()["company_reviews_required"] == 0


async def test_department_mailbox_is_never_merged_or_linked_as_person(
    uow_factory: UowFactory,
) -> None:
    runner = make_runner(uow_factory)
    netease_mapping = (
        '{"company_name":"公司名称","external_company_id":"外部ID",'
        '"website":"官网","address":"地址","company_type":"公司类型",'
        '"contact_name":"联系人姓名","contact_email":"联系人邮箱",'
        '"contact_title":"联系人职位","product_description":"主要进口产品",'
        '"hs_code":"HS code","shipment_date":"进口日期",'
        '"origin_country":"来源国","pol":"起运港","pod":"目的港"}'
    )
    async for client in make_client(uow_factory):
        session_id = await upload(
            client,
            filename="department-safety.csv",
            mapping=netease_mapping,
            header=(
                "公司名称,外部ID,官网,地址,公司类型,联系人姓名,联系人职位,"
                "联系人邮箱,主要进口产品,HS code,进口日期,来源国,起运港,目的港"
            ),
            rows=(
                "Delta Fitness,DELTA-1,delta.example,1 Port Ave Oakland CA,importer,"
                "Mia Wong,Procurement Director,mia@delta.example,"
                "fitness equipment,950691,2026-07-01,United States,Shanghai,Los Angeles\n"
                "Delta Fitness,,delta.example,1 Port Ave Oakland CA,importer,,"
                "Procurement,procurement@delta.example,"
                "fitness equipment,950691,2026-07-01,United States,Shanghai,Los Angeles\n"
            ),
        )
        result = await submit_and_run(client, runner, session_id)
        assert result["company_reviews_required"] == 0
        all_decisions = await decisions(client, session_id)
        department = next(
            item
            for item in all_decisions
            if item["entity_type"] == "contact"
            and cast(dict[str, str], item["source_facts"]).get("联系人邮箱")
            == "procurement@delta.example"
        )
        assert department["is_department_contact"] is True

        async with uow_factory() as uow:
            assert uow._session is not None  # noqa: SLF001
            department_links = list(
                (
                    await uow._session.execute(  # noqa: SLF001
                        select(CompanyContactModel).where(
                            CompanyContactModel.is_department_contact.is_(True)
                        )
                    )
                ).scalars()
            )
            assert len(department_links) == 1
            # The safety invariant is the department flag, not the role label:
            # a department mailbox is never treated as a personal decision maker.
            assert department_links[0].is_department_contact is True
            person_links = list(
                (
                    await uow._session.execute(  # noqa: SLF001
                        select(CompanyContactModel).where(
                            CompanyContactModel.is_department_contact.is_(False)
                        )
                    )
                ).scalars()
            )
            assert len(person_links) == 1
            person_contact = await uow._session.get(  # noqa: SLF001
                ContactModel, person_links[0].contact_id
            )
            assert person_contact is not None
            assert "procurement@delta.example" not in {
                channel.display_value
                for channel in person_contact.channels
            }


async def test_routing_preview_blocks_pending_entity_until_all_resolved(
    uow_factory: UowFactory,
) -> None:
    runner = make_runner(uow_factory)
    async for client in make_client(uow_factory):
        base_id = await upload(
            client,
            filename="routing-base.csv",
            rows=(
                "Atlas Fitness,ROUTE-BASE,atlas-fitness.example,"
                "100 Main St Austin TX,importer,"
                "Maria Chen,maria@atlas-fitness.example,Director Logistics,"
                "fitness equipment,950691,2026-07-01,United States,Shanghai,Los Angeles\n"
            ),
        )
        base = await submit_and_run(client, runner, base_id)
        assert base["company_reviews_required"] == 0

        conflict_id = await upload(
            client,
            filename="routing-conflict.csv",
            rows=(
                "Atlas Fitness LLC,ROUTE-CONFLICT,atlas-fitness.example,"
                "900 Ocean Dr Miami FL,warehouse,"
                "Pat Lee,pat@route-conflict.example,Procurement Manager,"
                "fitness equipment,950691,2026-07-01,United States,Shanghai,Los Angeles\n"
            ),
        )
        conflict = await submit_and_run(client, runner, conflict_id)
        assert conflict["company_reviews_required"] == 1
        company_decision = next(
            item
            for item in await decisions(client, conflict_id)
            if item["entity_type"] == "company"
        )

        payload = {
            "criteria": {
                "target_product_keywords": ["fitness", "gym equipment"],
                "target_hs_codes": ["950691"],
                "preferred_origin_countries": ["United States"],
                "preferred_pol": ["Shanghai"],
                "preferred_pod": ["Los Angeles"],
            },
            "campaign_name": "D5e2g1 routing gate",
        }

        blocked_preview = await client.post(
            f"/api/v1/import-sessions/{conflict_id}/routing-preview",
            json=payload,
        )
        assert blocked_preview.status_code == 200, blocked_preview.text
        blocked_body = blocked_preview.json()
        assert blocked_body["entity_pending_count"] == 1
        assert blocked_body["totals"]["blocked"] == 1
        blocked_companies = [
            company
            for company in blocked_body["companies"]
            if company["tier"] == "blocked"
        ]
        assert blocked_companies
        assert "UNRESOLVED_COMPANY_CONFLICT_BLOCKED" in blocked_companies[0][
            "reason_codes"
        ]

        merged = await review(client, str(company_decision["decision_id"]), "merge")
        assert merged["decision"] == "manual_merge"

        unblocked_preview = await client.post(
            f"/api/v1/import-sessions/{conflict_id}/routing-preview",
            json=payload,
        )
        assert unblocked_preview.status_code == 200, unblocked_preview.text
        unblocked_body = unblocked_preview.json()
        assert unblocked_body["entity_pending_count"] == 0
        assert unblocked_body["totals"]["blocked"] == 0
        assert unblocked_body["totals"]["A"] + unblocked_body["totals"]["B"] > 0
        assert unblocked_body["preview_valid"] is True
