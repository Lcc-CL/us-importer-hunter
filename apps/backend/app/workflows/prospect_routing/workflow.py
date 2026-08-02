"""Application workflows for deterministic prospect routing and human review."""

import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.domain.bulk_import import ImportSessionStatus
from app.domain.exceptions import DuplicateOperation, InvalidStateTransition
from app.domain.import_resolution import (
    ImportJobType,
    ImportProcessingJob,
    ImportResolutionStatus,
)
from app.domain.prospect_batch import ProspectBatch
from app.domain.prospect_routing import (
    ROUTING_RULES_VERSION,
    ProspectRoute,
    ProspectRouteReviewAction,
    ProspectRouteReviewStatus,
    ProspectRoutingCriteria,
    ProspectRoutingRun,
    ProspectRoutingRunStatus,
    ProspectTier,
    RoutingSourceCompany,
)
from app.domain.repositories import ImportResolutionUnitOfWork
from app.services.prospect_routing import (
    DEFAULT_WEIGHTS,
    DeterministicProspectRoutingScorer,
    RoutingFeatureProjector,
)
from app.shared.exceptions import (
    ApplicationConflictError,
    InvalidInputError,
    ResourceNotFoundError,
)

RoutingUowFactory = Callable[[], ImportResolutionUnitOfWork]
ProgressHeartbeat = Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class ProspectRoutingSubmission:
    run: ProspectRoutingRun
    job: ImportProcessingJob
    reused: bool
    recalculated: bool


@dataclass(frozen=True)
class ProspectRoutePage:
    routing_run_id: UUID
    page: int
    limit: int
    total: int
    routes: tuple[ProspectRoute, ...]


@dataclass(frozen=True)
class ProspectRoutingBatchSubmission:
    batch: ProspectBatch
    reused: bool


class ProspectRoutingSubmissionWorkflow:
    def __init__(
        self,
        uow_factory: RoutingUowFactory,
        *,
        max_attempts: int = 3,
    ) -> None:
        self._uow_factory = uow_factory
        self._max_attempts = max_attempts

    async def submit(
        self,
        import_session_id: UUID,
        criteria: ProspectRoutingCriteria,
    ) -> ProspectRoutingSubmission:
        configuration_hash = _configuration_hash(criteria)
        try:
            async with self._uow_factory() as uow:
                session = await uow.bulk_import.get_session(import_session_id)
                resolution = await uow.import_resolution.get_resolution(import_session_id)
                if session is None:
                    raise ResourceNotFoundError(
                        f"import session not found: {import_session_id}"
                    )
                if session.status not in {
                    ImportSessionStatus.COMPLETED,
                    ImportSessionStatus.PARTIAL_FAILED,
                }:
                    raise ApplicationConflictError(
                        "prospect routing requires a completed import session"
                    )
                if resolution is None or resolution.status not in {
                    ImportResolutionStatus.COMPLETED,
                    ImportResolutionStatus.PARTIAL_FAILED,
                }:
                    raise ApplicationConflictError(
                        "prospect routing requires completed entity resolution"
                    )
                sources = await uow.prospect_routing.list_source_companies(
                    import_session_id
                )
                if not sources:
                    raise ApplicationConflictError(
                        "entity resolution produced no routable companies"
                    )
                entity_state_hash = _entity_state_hash(sources)
                existing = await uow.prospect_routing.find_run_by_configuration(
                    import_session_id=import_session_id,
                    rules_version=ROUTING_RULES_VERSION,
                    configuration_hash=configuration_hash,
                )
                if existing is not None:
                    locked = await uow.prospect_routing.get_run_for_update(existing.id)
                    assert locked is not None
                    latest_job = await uow.import_processing_jobs.get_latest_for_routing_run(
                        locked.id
                    )
                    if (
                        locked.entity_state_hash == entity_state_hash
                        and locked.status is not ProspectRoutingRunStatus.FAILED
                        and latest_job is not None
                    ):
                        return ProspectRoutingSubmission(
                            run=locked,
                            job=latest_job,
                            reused=True,
                            recalculated=False,
                        )
                    locked.reset_for_recalculation(entity_state_hash=entity_state_hash)
                    await uow.prospect_routing.replace_routes(locked.id, ())
                    await uow.prospect_routing.save_run(locked)
                    job = _new_routing_job(locked, max_attempts=self._max_attempts)
                    await uow.import_processing_jobs.add(job)
                    await uow.commit()
                    return ProspectRoutingSubmission(
                        run=locked,
                        job=job,
                        reused=False,
                        recalculated=True,
                    )

                run = ProspectRoutingRun.create(
                    import_session_id=import_session_id,
                    rules_version=ROUTING_RULES_VERSION,
                    configuration_hash=configuration_hash,
                    entity_state_hash=entity_state_hash,
                    criteria=criteria,
                    weights_snapshot=DEFAULT_WEIGHTS,
                )
                await uow.prospect_routing.add_run(run)
                await uow.flush()
                job = _new_routing_job(run, max_attempts=self._max_attempts)
                await uow.import_processing_jobs.add(job)
                await uow.commit()
                return ProspectRoutingSubmission(
                    run=run,
                    job=job,
                    reused=False,
                    recalculated=False,
                )
        except DuplicateOperation:
            async with self._uow_factory() as uow:
                reused_run = await uow.prospect_routing.find_run_by_configuration(
                    import_session_id=import_session_id,
                    rules_version=ROUTING_RULES_VERSION,
                    configuration_hash=configuration_hash,
                )
                if reused_run is None:
                    raise
                reused_job = await uow.import_processing_jobs.get_latest_for_routing_run(
                    reused_run.id
                )
                if reused_job is None:
                    raise
                return ProspectRoutingSubmission(
                    run=reused_run,
                    job=reused_job,
                    reused=True,
                    recalculated=False,
                )


class ProspectRoutingExecutionWorkflow:
    def __init__(self, uow_factory: RoutingUowFactory) -> None:
        self._uow_factory = uow_factory
        self._projector = RoutingFeatureProjector()
        self._scorer = DeterministicProspectRoutingScorer()

    async def execute(
        self,
        routing_run_id: UUID,
        *,
        heartbeat: ProgressHeartbeat | None = None,
    ) -> ProspectRoutingRun:
        async with self._uow_factory() as uow:
            run = await uow.prospect_routing.get_run_for_update(routing_run_id)
            if run is None:
                raise ResourceNotFoundError(
                    f"prospect routing run not found: {routing_run_id}"
                )
            run.start()
            await uow.prospect_routing.save_run(run)
            await uow.commit()

        async with self._uow_factory() as uow:
            run = await uow.prospect_routing.get_run(routing_run_id)
            assert run is not None
            session = await uow.bulk_import.get_session(run.import_session_id)
            if session is None:
                raise ResourceNotFoundError(
                    f"import session not found: {run.import_session_id}"
                )
            sources = await uow.prospect_routing.list_source_companies(
                run.import_session_id
            )
        mapping = _logical_mapping(session.mapping_json)
        actual_state_hash = _entity_state_hash(sources)
        routes: list[ProspectRoute] = []
        for position, source in enumerate(sources, start=1):
            features = self._projector.project(source, mapping=mapping)
            routes.append(
                self._scorer.score(
                    routing_run_id=run.id,
                    criteria=run.criteria,
                    features=features,
                )
            )
            if heartbeat is not None and position % 100 == 0:
                await heartbeat()

        async with self._uow_factory() as uow:
            locked = await uow.prospect_routing.get_run_for_update(routing_run_id)
            if locked is None:
                raise ResourceNotFoundError(
                    f"prospect routing run not found: {routing_run_id}"
                )
            if locked.status is not ProspectRoutingRunStatus.RUNNING:
                raise ApplicationConflictError(
                    f"routing run in {locked.status.value} cannot persist results"
                )
            locked.entity_state_hash = actual_state_hash
            await uow.prospect_routing.replace_routes(routing_run_id, tuple(routes))
            locked.complete(tuple(routes))
            await uow.prospect_routing.save_run(locked)
            await uow.commit()
            return locked


class ProspectRoutingQueryWorkflow:
    def __init__(self, uow_factory: RoutingUowFactory) -> None:
        self._uow_factory = uow_factory

    async def get(
        self, routing_run_id: UUID
    ) -> tuple[ProspectRoutingRun, ImportProcessingJob | None]:
        async with self._uow_factory() as uow:
            run = await uow.prospect_routing.get_run(routing_run_id)
            if run is None:
                raise ResourceNotFoundError(
                    f"prospect routing run not found: {routing_run_id}"
                )
            job = await uow.import_processing_jobs.get_latest_for_routing_run(
                routing_run_id
            )
            return run, job

    async def list_routes(
        self,
        *,
        routing_run_id: UUID,
        tier: ProspectTier | None,
        review_status: ProspectRouteReviewStatus | None,
        minimum_score: float | None,
        maximum_score: float | None,
        has_contact: bool | None,
        role_category: str | None,
        page: int,
        limit: int,
    ) -> ProspectRoutePage:
        async with self._uow_factory() as uow:
            if await uow.prospect_routing.get_run(routing_run_id) is None:
                raise ResourceNotFoundError(
                    f"prospect routing run not found: {routing_run_id}"
                )
            routes, total = await uow.prospect_routing.list_routes(
                routing_run_id=routing_run_id,
                tier=tier,
                review_status=review_status,
                minimum_score=minimum_score,
                maximum_score=maximum_score,
                has_contact=has_contact,
                role_category=role_category,
                offset=(page - 1) * limit,
                limit=limit,
            )
            return ProspectRoutePage(
                routing_run_id=routing_run_id,
                page=page,
                limit=limit,
                total=total,
                routes=tuple(routes),
            )


class ProspectRouteReviewWorkflow:
    def __init__(self, uow_factory: RoutingUowFactory) -> None:
        self._uow_factory = uow_factory

    async def review(
        self,
        route_id: UUID,
        *,
        action: ProspectRouteReviewAction,
        effective_tier: ProspectTier | None,
        override_reason: str | None,
        reviewed_by: str,
    ) -> ProspectRoute:
        async with self._uow_factory() as uow:
            route = await uow.prospect_routing.get_route_for_update(route_id)
            if route is None:
                raise ResourceNotFoundError(f"prospect route not found: {route_id}")
            try:
                if action is ProspectRouteReviewAction.CONFIRM:
                    reviewed = route.confirm(reviewed_by=reviewed_by)
                elif action is ProspectRouteReviewAction.OVERRIDE:
                    if effective_tier is None or override_reason is None:
                        raise InvalidInputError(
                            code="ROUTING_OVERRIDE_REQUIRED",
                            message="override requires effective_tier and override_reason",
                        )
                    reviewed = route.override(
                        effective_tier=effective_tier,
                        override_reason=override_reason,
                        reviewed_by=reviewed_by,
                    )
                else:
                    if override_reason is None:
                        raise InvalidInputError(
                            code="ROUTING_EXCLUDE_REASON_REQUIRED",
                            message="exclude requires override_reason",
                        )
                    reviewed = route.override(
                        effective_tier=ProspectTier.D,
                        override_reason=override_reason,
                        reviewed_by=reviewed_by,
                    )
            except InvalidStateTransition as exc:
                raise ApplicationConflictError(str(exc)) from exc
            await uow.prospect_routing.save_route(reviewed)
            await uow.commit()
            return reviewed


class ProspectRoutingBatchWorkflow:
    def __init__(self, uow_factory: RoutingUowFactory) -> None:
        self._uow_factory = uow_factory

    async def create(
        self,
        routing_run_id: UUID,
        company_ids: tuple[UUID, ...],
    ) -> ProspectRoutingBatchSubmission:
        if not company_ids:
            raise InvalidInputError(
                code="ROUTING_BATCH_COMPANIES_REQUIRED",
                message="at least one company_id is required",
            )
        unique_ids = tuple(dict.fromkeys(company_ids))
        if len(unique_ids) != len(company_ids):
            raise InvalidInputError(
                code="ROUTING_BATCH_COMPANIES_DUPLICATED",
                message="company_ids must not contain duplicates",
            )
        if len(unique_ids) > 5:
            raise InvalidInputError(
                code="ROUTING_BATCH_LIMIT_EXCEEDED",
                message="a prospect batch can contain at most five companies",
            )
        try:
            async with self._uow_factory() as uow:
                run = await uow.prospect_routing.get_run(routing_run_id)
                if run is None:
                    raise ResourceNotFoundError(
                        f"prospect routing run not found: {routing_run_id}"
                    )
                if run.status not in {
                    ProspectRoutingRunStatus.COMPLETED,
                    ProspectRoutingRunStatus.PARTIAL_COMPLETED,
                }:
                    raise ApplicationConflictError(
                        "prospect batch requires a completed routing run"
                    )
                routes = await uow.prospect_routing.list_routes_for_companies(
                    routing_run_id=routing_run_id,
                    company_ids=unique_ids,
                )
                route_by_company = {route.company_id: route for route in routes}
                missing = [value for value in unique_ids if value not in route_by_company]
                if missing:
                    raise InvalidInputError(
                        code="ROUTING_BATCH_COMPANY_OUTSIDE_RUN",
                        message="all company_ids must belong to this routing run",
                    )
                invalid = [
                    route.company_id
                    for route in routes
                    if route.effective_tier is not ProspectTier.A
                    or route.review_status
                    not in {
                        ProspectRouteReviewStatus.CONFIRMED,
                        ProspectRouteReviewStatus.OVERRIDDEN,
                    }
                ]
                if invalid:
                    raise ApplicationConflictError(
                        "only confirmed or overridden effective-tier A routes may enter a batch"
                    )
                selection_hash = _selection_hash(
                    routing_run_id,
                    run.execution_generation,
                    unique_ids,
                )
                existing = await uow.prospect_batches.find_for_routing_selection(
                    routing_run_id=routing_run_id,
                    routing_selection_hash=selection_hash,
                )
                if existing is not None:
                    return ProspectRoutingBatchSubmission(batch=existing, reused=True)
                batch = ProspectBatch.create_from_routing(
                    routing_run_id=routing_run_id,
                    routing_selection_hash=selection_hash,
                    requested_count=len(company_ids),
                    companies=tuple(
                        (company_id, route_by_company[company_id].company_name)
                        for company_id in unique_ids
                    ),
                )
                await uow.prospect_batches.add(batch)
                await uow.commit()
                return ProspectRoutingBatchSubmission(batch=batch, reused=False)
        except DuplicateOperation:
            async with self._uow_factory() as uow:
                run = await uow.prospect_routing.get_run(routing_run_id)
                if run is None:
                    raise
                selection_hash = _selection_hash(
                    routing_run_id,
                    run.execution_generation,
                    unique_ids,
                )
                existing = await uow.prospect_batches.find_for_routing_selection(
                    routing_run_id=routing_run_id,
                    routing_selection_hash=selection_hash,
                )
                if existing is None:
                    raise
                return ProspectRoutingBatchSubmission(batch=existing, reused=True)


def _new_routing_job(
    run: ProspectRoutingRun,
    *,
    max_attempts: int,
) -> ImportProcessingJob:
    return ImportProcessingJob.create(
        import_session_id=run.import_session_id,
        job_type=ImportJobType.PROSPECT_ROUTING,
        routing_run_id=run.id,
        business_key=f"prospect-routing:{run.id}:{run.execution_generation}",
        max_attempts=max_attempts,
    )


def _configuration_hash(criteria: ProspectRoutingCriteria) -> str:
    payload = {
        "rules_version": ROUTING_RULES_VERSION,
        "criteria": criteria.to_json(),
        "weights": DEFAULT_WEIGHTS,
    }
    return _sha256(payload)


def _entity_state_hash(sources: tuple[RoutingSourceCompany, ...]) -> str:
    payload = [
        {
            "company_id": str(source.company_id),
            "company_name": source.company_name,
            "website": source.website,
            "profile_domain": source.profile_domain,
            "profile_address": source.profile_address,
            "profile_company_type": source.profile_company_type,
            "unresolved_company_conflict": source.unresolved_company_conflict,
            "rows": [
                {
                    "id": str(row.raw_import_row_id),
                    "row_number": row.row_number,
                    "payload": row.raw_payload,
                }
                for row in source.rows
            ],
            "contacts": [
                {
                    "id": str(contact.contact_id),
                    "role_category": contact.role_category,
                    "seniority": contact.seniority,
                    "status": contact.status,
                    "has_usable_channel": contact.has_usable_channel,
                    "has_usable_email": contact.has_usable_email,
                }
                for contact in source.contacts
            ],
        }
        for source in sources
    ]
    return _sha256(payload)


def _selection_hash(
    routing_run_id: UUID,
    execution_generation: int,
    company_ids: tuple[UUID, ...],
) -> str:
    return _sha256(
        {
            "routing_run_id": str(routing_run_id),
            "execution_generation": execution_generation,
            "company_ids": sorted(str(value) for value in company_ids),
        }
    )


def _sha256(value: Any) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _logical_mapping(value: dict[str, Any]) -> dict[str, str]:
    raw = value.get("logical_fields", {})
    if not isinstance(raw, dict):
        return {}
    return {
        str(key): str(mapped)
        for key, mapped in raw.items()
        if str(key).strip() and str(mapped).strip()
    }
