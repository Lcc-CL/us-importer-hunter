"""Health endpoints: liveness, readiness, and safe runtime metadata."""

import logging
from datetime import datetime

from fastapi import APIRouter
from redis.asyncio import Redis
from sqlalchemy import text

from app.api.deps import DbSessionDep, RedisDep, SettingsDep
from app.core.worker_health import (
    WORKER_HEARTBEAT_KEY,
    WORKER_HEARTBEAT_TTL_SECONDS,
    parse_worker_heartbeat,
)
from app.domain.clock import utcnow
from app.schemas.health import (
    DependencyStatus,
    HealthResponse,
    ReadinessResponse,
    RuntimeStatusResponse,
    WorkerDependencyStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


async def _worker_dependency(redis: Redis) -> WorkerDependencyStatus:
    """Report the worker from its Redis heartbeat without leaking internals."""
    try:
        await redis.ping()
    except Exception as exc:  # noqa: BLE001 — report, don't crash the probe
        logger.warning("Redis readiness check failed: %s", exc)
        return WorkerDependencyStatus(
            name="worker",
            healthy=False,
            detail="worker status unknown because Redis is unavailable",
            status="unknown",
            reason_code="REDIS_UNAVAILABLE",
        )

    try:
        if not bool(await redis.exists(WORKER_HEARTBEAT_KEY)):
            return WorkerDependencyStatus(
                name="worker",
                healthy=False,
                detail="worker heartbeat missing",
                status="unavailable",
                reason_code="WORKER_HEARTBEAT_MISSING",
            )
        raw = await redis.get(WORKER_HEARTBEAT_KEY)
        payload = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        parsed = parse_worker_heartbeat(payload)
        if parsed is None:
            return WorkerDependencyStatus(
                name="worker",
                healthy=False,
                detail="worker heartbeat payload invalid",
                status="unavailable",
                reason_code="WORKER_HEARTBEAT_INVALID",
            )
        heartbeat_at = datetime.fromisoformat(parsed["heartbeat_at"])
        age_seconds = max(0.0, (utcnow() - heartbeat_at).total_seconds())
        last_seen_at = heartbeat_at.isoformat()
        if age_seconds > WORKER_HEARTBEAT_TTL_SECONDS:
            return WorkerDependencyStatus(
                name="worker",
                healthy=False,
                detail="worker heartbeat expired",
                status="unavailable",
                reason_code="WORKER_HEARTBEAT_EXPIRED",
                last_seen_at=last_seen_at,
                age_seconds=round(age_seconds, 1),
            )
        return WorkerDependencyStatus(
            name="worker",
            healthy=True,
            detail=None,
            status="healthy",
            reason_code="WORKER_HEARTBEAT_OK",
            last_seen_at=last_seen_at,
            age_seconds=round(age_seconds, 1),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Worker readiness check failed: %s", exc)
        return WorkerDependencyStatus(
            name="worker",
            healthy=False,
            detail="worker status unavailable",
            status="unknown",
            reason_code="WORKER_HEARTBEAT_INVALID",
        )


@router.get("/health", response_model=HealthResponse)
async def health(settings: SettingsDep) -> HealthResponse:
    """Liveness probe — always succeeds if the process is up."""
    return HealthResponse(app=settings.app_name, environment=settings.app_env)


@router.get("/health/runtime", response_model=RuntimeStatusResponse)
async def runtime_status(settings: SettingsDep) -> RuntimeStatusResponse:
    """Which providers and models this deployment runs.

    Names only — never a key or an endpoint URL.
    """
    provider = settings.email_generator_provider
    research = settings.research_extractor_provider
    return RuntimeStatusResponse(
        provider=provider,
        model=settings.openai_model if provider == "openai" else "fake-static-v1",
        research_provider=research,
        research_model=(
            settings.resolved_research_model
            if research == "openai"
            else settings.deepseek_model
            if research == "deepseek"
            else "fake-research-v1"
        ),
        environment=settings.app_env,
        real_data_gate="enabled" if settings.real_data_acknowledged else "blocked",
    )


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness(session: DbSessionDep, redis: RedisDep) -> ReadinessResponse:
    """Readiness probe — verifies PostgreSQL, Redis, and worker heartbeat."""
    dependencies: list[DependencyStatus] = []

    try:
        await session.execute(text("SELECT 1"))
        dependencies.append(DependencyStatus(name="postgres", healthy=True))
    except Exception as exc:  # noqa: BLE001 — report, don't crash the probe
        logger.warning("Postgres readiness check failed: %s", exc)
        dependencies.append(
            DependencyStatus(
                name="postgres",
                healthy=False,
                detail="database connection check failed",
            )
        )

    try:
        await redis.ping()
        dependencies.append(DependencyStatus(name="redis", healthy=True))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis readiness check failed: %s", exc)
        dependencies.append(
            DependencyStatus(
                name="redis",
                healthy=False,
                detail="cache connection check failed",
            )
        )

    dependencies.append(await _worker_dependency(redis))

    all_healthy = all(dep.healthy for dep in dependencies)
    return ReadinessResponse(
        status="ready" if all_healthy else "degraded",
        dependencies=dependencies,
    )
