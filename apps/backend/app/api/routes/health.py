"""Health endpoints: liveness (no dependencies) and readiness (DB + Redis)."""

import logging

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DbSessionDep, RedisDep, SettingsDep
from app.schemas.health import DependencyStatus, HealthResponse, ReadinessResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(settings: SettingsDep) -> HealthResponse:
    """Liveness probe — always succeeds if the process is up."""
    return HealthResponse(app=settings.app_name, environment=settings.app_env)


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness(session: DbSessionDep, redis: RedisDep) -> ReadinessResponse:
    """Readiness probe — verifies PostgreSQL and Redis connectivity."""
    dependencies: list[DependencyStatus] = []

    try:
        await session.execute(text("SELECT 1"))
        dependencies.append(DependencyStatus(name="postgres", healthy=True))
    except Exception as exc:  # noqa: BLE001 — report, don't crash the probe
        logger.warning("Postgres readiness check failed: %s", exc)
        dependencies.append(
            DependencyStatus(name="postgres", healthy=False, detail=str(exc))
        )

    try:
        await redis.ping()
        dependencies.append(DependencyStatus(name="redis", healthy=True))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis readiness check failed: %s", exc)
        dependencies.append(
            DependencyStatus(name="redis", healthy=False, detail=str(exc))
        )

    all_healthy = all(dep.healthy for dep in dependencies)
    return ReadinessResponse(
        status="ready" if all_healthy else "degraded",
        dependencies=dependencies,
    )
