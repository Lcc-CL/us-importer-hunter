"""Natural-language prompt → provider candidates → canonical companies."""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from app.domain.discovery import (
    CompanyDiscoveryProvider,
    CompanyDiscoveryQuery,
    DiscoveryCandidate,
    DiscoveryCandidateStatus,
    DiscoveryResult,
    DiscoveryTask,
    RawCompanySnapshot,
)
from app.domain.discovery.provider import limit_candidates
from app.domain.events import CompanyDiscovered
from app.domain.repositories import DiscoveryTaskUnitOfWork
from app.domain.task import Task
from app.domain.values import IdempotencyKey, SourceReference
from app.services.discovery import PreparedCandidate, parse_discovery_prompt, prepare_candidates
from app.workflows.company_ingestion import CompanyIngestionWorkflow, IngestionStatus


@dataclass(frozen=True)
class CreateDiscoveryTaskCommand:
    prompt: str


class DiscoveryTaskWorkflow:
    def __init__(
        self,
        *,
        uow_factory: Callable[[], DiscoveryTaskUnitOfWork],
        provider: CompanyDiscoveryProvider,
        company_ingestion: CompanyIngestionWorkflow,
    ) -> None:
        self._uow_factory = uow_factory
        self._provider = provider
        self._company_ingestion = company_ingestion

    async def handle(
        self,
        command: CreateDiscoveryTaskCommand,
        *,
        provider: CompanyDiscoveryProvider | None = None,
    ) -> DiscoveryTask:
        parsed = parse_discovery_prompt(command.prompt)
        selected_provider = provider or self._provider
        execution_task, _ = await self._create_tasks(
            parsed.original_prompt,
            requested_count=parsed.requested_count,
            effective_count=parsed.effective_count,
            region=parsed.region,
            category=parsed.category,
            keywords=parsed.keywords,
            provider=selected_provider.provider_name,
        )
        await self._start_tasks(execution_task.id)

        query = CompanyDiscoveryQuery(
            original_prompt=parsed.original_prompt,
            requested_count=parsed.requested_count,
            effective_count=parsed.effective_count,
            region=parsed.region,
            category=parsed.category,
            keywords=parsed.keywords,
        )
        try:
            search_result = await selected_provider.search(query)
        except Exception as exc:  # provider boundary: persist terminal failure, never hang
            await self._fail_tasks(execution_task.id, str(exc) or type(exc).__name__)
            return await self._require_task(execution_task.id)

        candidates = limit_candidates(search_result.candidates, limit=parsed.effective_count)
        prepared = prepare_candidates(candidates)
        await self._persist_candidates(execution_task.id, prepared)

        task = await self._require_task(execution_task.id)
        for item in task.candidates:
            if item.duplicate_of_id is not None:
                continue
            await self._ingest_candidate(execution_task.id, item)

        failures = tuple(failure.reason for failure in search_result.failures)
        await self._complete_tasks(execution_task.id, failures)
        return await self._require_task(execution_task.id)

    async def _create_tasks(
        self,
        prompt: str,
        *,
        requested_count: int,
        effective_count: int,
        region: str,
        category: str,
        keywords: tuple[str, ...],
        provider: str,
    ) -> tuple[Task, DiscoveryTask]:
        digest = hashlib.sha256(f"{provider}|{prompt}".encode()).hexdigest()
        async with self._uow_factory() as uow:
            task = Task.create(
                prompt,
                IdempotencyKey(f"discovery:{digest}"),
                active_keys=await uow.tasks.active_keys(),
            )
            discovery = DiscoveryTask.create(
                execution_task_id=task.id,
                original_prompt=prompt,
                requested_count=requested_count,
                effective_count=effective_count,
                parsed_region=region,
                parsed_category=category,
                parsed_keywords=keywords,
                provider=provider,
            )
            await uow.tasks.add(task)
            await uow.flush()
            await uow.discovery_tasks.add(discovery)
            await uow.commit()
            return task, discovery

    async def _start_tasks(self, task_id: UUID) -> None:
        async with self._uow_factory() as uow:
            execution = await uow.tasks.get_by_id(task_id)
            discovery = await uow.discovery_tasks.get_by_id(task_id)
            assert execution is not None and discovery is not None
            execution.start()
            discovery.start()
            await uow.tasks.save(execution)
            await uow.discovery_tasks.save(discovery)
            await uow.commit()

    async def _persist_candidates(
        self, task_id: UUID, prepared: tuple[PreparedCandidate, ...]
    ) -> None:
        async with self._uow_factory() as uow:
            task = await uow.discovery_tasks.get_by_id(task_id)
            assert task is not None
            persisted: list[DiscoveryCandidate] = []
            for item in prepared:
                source_reference = item.candidate.source_url or item.candidate.external_id
                assert source_reference is not None
                candidate = DiscoveryCandidate(
                    id=uuid5(
                        NAMESPACE_URL,
                        f"{task_id}|{item.candidate.source}|{source_reference}|{len(persisted)}",
                    ),
                    source=item.candidate.source,
                    source_url=item.candidate.source_url,
                    external_id=item.candidate.external_id,
                    company_name=item.candidate.company_name.strip(),
                    normalized_name=item.normalized_name,
                    website=item.candidate.website,
                    normalized_domain=item.normalized_domain,
                    address=item.candidate.address,
                    region=item.candidate.region,
                    product_description=item.candidate.product_description,
                    import_evidence=item.candidate.import_evidence,
                    raw_metadata_json=item.candidate.raw_metadata_json,
                    status=DiscoveryCandidateStatus.DISCOVERED,
                    company_id=None,
                    duplicate_of_id=None,
                    failure_reason=None,
                    created_at=task.created_at,
                )
                if item.duplicate_of_index is not None:
                    candidate = candidate.duplicate(
                        duplicate_of_id=persisted[item.duplicate_of_index].id
                    )
                task.add_candidate(candidate)
                persisted.append(candidate)
            await uow.discovery_tasks.save(task)
            await uow.commit()

    async def _ingest_candidate(self, task_id: UUID, candidate: DiscoveryCandidate) -> None:
        reference = candidate.source_url or candidate.external_id
        assert reference is not None
        event = CompanyDiscovered(
            run_id=task_id,
            result=DiscoveryResult(
                snapshot=RawCompanySnapshot(
                    name_text=candidate.company_name,
                    website_text=candidate.website,
                    location_text=candidate.address or candidate.region,
                    description_text=candidate.product_description,
                    source=SourceReference(
                        source=candidate.source,
                        reference=reference,
                        retrieved_at=candidate.created_at,
                    ),
                )
            ),
        )
        try:
            outcome = await self._company_ingestion.handle(event)
            if outcome.status is IngestionStatus.REJECTED or outcome.company_id is None:
                updated = candidate.failed("; ".join(outcome.notes) or "company ingestion rejected")
            elif outcome.status is IngestionStatus.MERGED:
                updated = candidate.duplicate(
                    duplicate_of_id=None, company_id=outcome.company_id
                )
            else:
                updated = candidate.ingested(outcome.company_id)
        except Exception as exc:  # one company must never abort the task
            updated = candidate.failed(str(exc) or type(exc).__name__)

        async with self._uow_factory() as uow:
            task = await uow.discovery_tasks.get_by_id(task_id)
            assert task is not None
            task.replace_candidate(updated)
            await uow.discovery_tasks.save(task)
            await uow.commit()

    async def _complete_tasks(self, task_id: UUID, provider_failures: tuple[str, ...]) -> None:
        async with self._uow_factory() as uow:
            execution = await uow.tasks.get_by_id(task_id)
            discovery = await uow.discovery_tasks.get_by_id(task_id)
            assert execution is not None and discovery is not None
            candidate_failures = tuple(
                f"{item.company_name[:80]}: {item.failure_reason[:300]}"
                for item in discovery.candidates
                if item.failure_reason is not None
            )
            all_failures = (*provider_failures, *candidate_failures)
            discovery.complete(
                provider_failures=len(provider_failures),
                error_summary="; ".join(all_failures) or None,
            )
            if discovery.status.value == "failed":
                execution.fail(discovery.error_summary or "all discovery candidates failed")
            else:
                execution.complete()
            await uow.tasks.save(execution)
            await uow.discovery_tasks.save(discovery)
            await uow.commit()

    async def _fail_tasks(self, task_id: UUID, error: str) -> None:
        async with self._uow_factory() as uow:
            execution = await uow.tasks.get_by_id(task_id)
            discovery = await uow.discovery_tasks.get_by_id(task_id)
            assert execution is not None and discovery is not None
            discovery.fail(error)
            execution.fail(error)
            await uow.tasks.save(execution)
            await uow.discovery_tasks.save(discovery)
            await uow.commit()

    async def _require_task(self, task_id: UUID) -> DiscoveryTask:
        async with self._uow_factory() as uow:
            task = await uow.discovery_tasks.get_by_id(task_id)
        assert task is not None
        return task


class DiscoveryTaskQueryWorkflow:
    def __init__(self, uow_factory: Callable[[], DiscoveryTaskUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def get(self, task_id: UUID) -> DiscoveryTask | None:
        async with self._uow_factory() as uow:
            return await uow.discovery_tasks.get_by_id(task_id)
