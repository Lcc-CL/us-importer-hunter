"""D5b1 API, PostgreSQL identity reuse, review and compatibility tests."""

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import cast
from uuid import UUID

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.api.deps import get_uow_factory
from app.core.config import Settings
from app.database.models.company import CompanyModel
from app.database.models.contact import ContactChannelModel, ContactModel
from app.database.models.import_resolution import CompanyContactModel
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
    '"contact_name":"contact","contact_email":"email","contact_title":"title"}'
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
    source: str = "netease_foreign_trade",
) -> str:
    response = await client.post(
        "/api/v1/import-sessions",
        data={"source": source, "mapping": MAPPING},
        files={
            "file": (
                filename,
                (
                    "company,external_id,website,address,company_type,contact,email,title\n"
                    f"{rows}"
                ).encode(),
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


async def test_cross_file_company_contact_reuse_and_shared_contact_delete_safety(
    uow_factory: UowFactory,
) -> None:
    runner = make_runner(uow_factory)
    async for client in make_client(uow_factory):
        first_id = await upload(
            client,
            filename="first.csv",
            rows=(
                "Atlas Hardware Inc,ATLAS-1,atlas.example,100 Main St Austin TX,"
                "importer,Maria Chen,maria@shared.example,Director of Supply Chain\n"
            ),
        )
        first = await submit_and_run(client, runner, first_id)
        assert first["companies_created"] == 1
        assert first["contacts_created"] == 1
        first_decisions = await decisions(client, first_id)
        atlas_company_decision = next(
            item for item in first_decisions if item["entity_type"] == "company"
        )
        atlas_id = UUID(str(atlas_company_decision["candidate_entity_id"]))
        first_contact_decision = next(
            item for item in first_decisions if item["entity_type"] == "contact"
        )
        contact_id = UUID(str(first_contact_decision["candidate_entity_id"]))

        renamed_id = await upload(
            client,
            filename="renamed.csv",
            rows=(
                "Atlas Industrial Supply,ATLAS-1,new-atlas.example,500 Changed Rd Dallas TX,"
                "brand,,,\n"
            ),
        )
        renamed = await submit_and_run(client, runner, renamed_id)
        assert renamed["companies_reused"] == 1
        renamed_company = next(
            item for item in await decisions(client, renamed_id) if item["entity_type"] == "company"
        )
        assert UUID(str(renamed_company["candidate_entity_id"])) == atlas_id
        assert "external_identity_match" in cast(
            list[str], renamed_company["reason_codes"]
        )

        second_id = await upload(
            client,
            filename="second-company.csv",
            rows=(
                "Beta Tools,BETA-1,beta.example,200 Market St Seattle WA,importer,"
                "Maria Chen,maria@shared.example,VP Logistics\n"
            ),
        )
        second = await submit_and_run(client, runner, second_id)
        assert second["contacts_reused"] == 1
        assert second["company_contacts_created"] == 1
        second_company = next(
            item for item in await decisions(client, second_id) if item["entity_type"] == "company"
        )
        beta_id = UUID(str(second_company["candidate_entity_id"]))

    async with uow_factory() as uow:
        assert uow._session is not None  # noqa: SLF001 - integration compatibility assertion
        contact_count = await uow._session.scalar(  # noqa: SLF001
            select(func.count()).select_from(ContactModel)
        )
        link_count = await uow._session.scalar(  # noqa: SLF001
            select(func.count()).select_from(CompanyContactModel)
        )
        assert contact_count == 1
        assert link_count == 2
        await uow._session.execute(delete(CompanyModel).where(CompanyModel.id == atlas_id))  # noqa: SLF001
        await uow.commit()

    async with uow_factory() as uow:
        assert uow._session is not None  # noqa: SLF001
        persisted_contact = await uow._session.get(ContactModel, contact_id)  # noqa: SLF001
        assert persisted_contact is not None
        assert persisted_contact.company_id is None
        beta_link = await uow._session.scalar(  # noqa: SLF001
            select(CompanyContactModel).where(
                CompanyContactModel.company_id == beta_id,
                CompanyContactModel.contact_id == contact_id,
            )
        )
        assert beta_link is not None


async def test_domain_conflicts_and_manual_merge_keep_separate_reject_are_idempotent(
    uow_factory: UowFactory,
) -> None:
    runner = make_runner(uow_factory)
    async for client in make_client(uow_factory):
        base_id = await upload(
            client,
            filename="base.csv",
            rows=(
                "Atlas Hardware Inc,BASE-1,atlas.example,100 Main St Austin TX,importer,"
                "Maria Chen,maria.one@atlas.example,Director Logistics\n"
            ),
        )
        await submit_and_run(client, runner, base_id)

        conflict_id = await upload(
            client,
            filename="domain-conflict.csv",
            rows=(
                "Unrelated Furniture Group,CONFLICT-1,atlas.example,"
                "900 Ocean Dr Miami FL,warehouse,"
                "Pat Lee,pat@unrelated.example,Procurement Manager\n"
            ),
        )
        conflict = await submit_and_run(client, runner, conflict_id)
        assert conflict["company_reviews_required"] == 1
        conflict_decisions = await decisions(client, conflict_id)
        conflict_decision = next(
            item
            for item in conflict_decisions
            if item["entity_type"] == "company"
        )
        conflict_contact_decision = next(
            item for item in conflict_decisions if item["entity_type"] == "contact"
        )
        conflict_contact_id = UUID(str(conflict_contact_decision["candidate_entity_id"]))
        async with uow_factory() as uow:
            assert uow._session is not None  # noqa: SLF001
            staged_contact = await uow._session.get(  # noqa: SLF001
                ContactModel, conflict_contact_id
            )
            premature_link = await uow._session.scalar(  # noqa: SLF001
                select(CompanyContactModel).where(
                    CompanyContactModel.contact_id == conflict_contact_id
                )
            )
            assert staged_contact is not None
            assert staged_contact.company_id is None
            assert premature_link is None
        decision_id = str(conflict_decision["decision_id"])
        merged = await client.post(
            f"/api/v1/import-entity-decisions/{decision_id}/review",
            json={"action": "merge", "reviewed_by": "qa"},
        )
        assert merged.status_code == 200, merged.text
        repeated = await client.post(
            f"/api/v1/import-entity-decisions/{decision_id}/review",
            json={"action": "merge", "reviewed_by": "qa"},
        )
        assert repeated.status_code == 200
        after_merge = await client.get(
            f"/api/v1/import-sessions/{conflict_id}/resolution"
        )
        assert after_merge.json()["company_reviews_required"] == 0
        assert after_merge.json()["companies_reused"] == 1
        async with uow_factory() as uow:
            assert uow._session is not None  # noqa: SLF001
            confirmed_link = await uow._session.scalar(  # noqa: SLF001
                select(CompanyContactModel).where(
                    CompanyContactModel.contact_id == conflict_contact_id
                )
            )
            assert confirmed_link is not None

        renamed_after_review_id = await upload(
            client,
            filename="reviewed-external-id.csv",
            rows=(
                "Completely Renamed,CONFLICT-1,new-domain.example,500 Changed Rd Dallas TX,"
                "brand,,,\n"
            ),
        )
        renamed_after_review = await submit_and_run(
            client, runner, renamed_after_review_id
        )
        assert renamed_after_review["companies_reused"] == 1
        renamed_after_review_decision = next(
            item
            for item in await decisions(client, renamed_after_review_id)
            if item["entity_type"] == "company"
        )
        assert "external_identity_match" in cast(
            list[str], renamed_after_review_decision["reason_codes"]
        )

        separate_id = await upload(
            client,
            filename="name-similar.csv",
            rows=(
                "Atlas Hardware LLC,,different.example,700 Hill Rd Denver CO,importer,,,\n"
            ),
        )
        await submit_and_run(client, runner, separate_id)
        separate_decision = next(
            item
            for item in await decisions(client, separate_id)
            if item["entity_type"] == "company"
        )
        kept = await client.post(
            f"/api/v1/import-entity-decisions/{separate_decision['decision_id']}/review",
            json={"action": "keep_separate", "reviewed_by": "qa"},
        )
        assert kept.status_code == 200, kept.text
        assert kept.json()["decision"] == "keep_separate"

        contact_review_id = await upload(
            client,
            filename="contact-review.csv",
            rows=(
                "Atlas Hardware Inc,BASE-1,atlas.example,100 Main St Austin TX,importer,"
                "Maria Chen,maria.two@atlas.example,Director Logistics\n"
            ),
        )
        await submit_and_run(client, runner, contact_review_id)
        contact_decision = next(
            item
            for item in await decisions(client, contact_review_id)
            if item["entity_type"] == "contact"
        )
        assert contact_decision["decision"] == "review_required"
        rejected = await client.post(
            f"/api/v1/import-entity-decisions/{contact_decision['decision_id']}/review",
            json={"action": "reject", "reviewed_by": "qa"},
        )
        assert rejected.status_code == 200
        assert rejected.json()["decision"] == "rejected"

        contact_merge_id = await upload(
            client,
            filename="contact-merge.csv",
            rows=(
                "Atlas Hardware Inc,BASE-1,atlas.example,100 Main St Austin TX,importer,"
                "Maria Chen,maria.three@atlas.example,Director Logistics\n"
            ),
        )
        await submit_and_run(client, runner, contact_merge_id)
        contact_merge_decision = next(
            item
            for item in await decisions(client, contact_merge_id)
            if item["entity_type"] == "contact"
        )
        contact_merged = await client.post(
            f"/api/v1/import-entity-decisions/{contact_merge_decision['decision_id']}/review",
            json={"action": "merge", "reviewed_by": "qa"},
        )
        assert contact_merged.status_code == 200, contact_merged.text
        async with uow_factory() as uow:
            assert uow._session is not None  # noqa: SLF001
            merged_channel = await uow._session.get(  # noqa: SLF001
                ContactChannelModel,
                (
                    UUID(str(contact_merge_decision["candidate_entity_id"])),
                    "email",
                    "maria.three@atlas.example",
                ),
            )
            assert merged_channel is not None


async def test_department_unassigned_repeat_resolve_and_stale_recovery(
    uow_factory: UowFactory,
) -> None:
    runner = make_runner(uow_factory)
    async for client in make_client(uow_factory):
        session_id = await upload(
            client,
            filename="department-unassigned.csv",
            rows=(
                "Gamma Imports,GAMMA-1,gamma.example,1 Port Ave Oakland CA,importer,,"
                "procurement@gamma.example,Procurement\n"
                ",,,,,Solo Person,solo@outside.example,Buyer\n"
            ),
        )
        first_submission = await client.post(
            f"/api/v1/import-sessions/{session_id}/resolve"
        )
        assert first_submission.status_code == 202
        repeated_submission = await client.post(
            f"/api/v1/import-sessions/{session_id}/resolve"
        )
        assert repeated_submission.status_code == 202
        assert repeated_submission.json()["reused"] is True
        assert (
            repeated_submission.json()["processing_job_id"]
            == first_submission.json()["processing_job_id"]
        )
        assert await runner.run_once(owner="department-worker") is True
        result = await client.get(f"/api/v1/import-sessions/{session_id}/resolution")
        assert result.status_code == 200
        body = result.json()
        assert body["contacts_created"] == 2
        assert body["company_contacts_created"] == 1
        assert body["failed_rows"] == 1

    async with uow_factory() as uow:
        assert uow._session is not None  # noqa: SLF001
        department_link = await uow._session.scalar(  # noqa: SLF001
            select(CompanyContactModel).where(
                CompanyContactModel.is_department_contact.is_(True)
            )
        )
        unassigned = await uow._session.scalar(  # noqa: SLF001
            select(ContactModel).where(ContactModel.company_id.is_(None))
        )
        assert department_link is not None
        assert unassigned is not None

    async for client in make_client(uow_factory):
        stale_session_id = await upload(
            client,
            filename="stale.csv",
            rows="Stale Co,STALE-1,stale.example,1 Delay Rd Reno NV,importer,,,\n",
            source="netease_stale_test",
        )
        submitted = await client.post(
            f"/api/v1/import-sessions/{stale_session_id}/resolve"
        )
        assert submitted.status_code == 202
    coordinator = ImportProcessingJobCoordinator(
        uow_factory,
        lease_ttl=timedelta(milliseconds=1),
        retry_delay=timedelta(0),
    )
    leased = await coordinator.claim(owner="crashed-worker")
    assert leased is not None
    await coordinator.start(leased.id, owner="crashed-worker")
    await asyncio.sleep(0.01)
    recovered = await coordinator.recover_stale()
    assert recovered and recovered[0].status.value == "pending"
