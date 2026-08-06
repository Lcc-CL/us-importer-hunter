"""Typed responses for health endpoints."""

from typing import Literal

from pydantic import BaseModel

WorkerStatusValue = Literal["healthy", "unavailable", "unknown"]
WorkerReasonCode = Literal[
    "WORKER_HEARTBEAT_OK",
    "WORKER_HEARTBEAT_MISSING",
    "WORKER_HEARTBEAT_EXPIRED",
    "WORKER_HEARTBEAT_INVALID",
    "REDIS_UNAVAILABLE",
]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    app: str
    environment: str


class DependencyStatus(BaseModel):
    name: str
    healthy: bool
    detail: str | None = None


class WorkerDependencyStatus(DependencyStatus):
    """Worker dependency with structured heartbeat health (D5e1.2).

    Kept as a subclass so postgres/redis entries keep the exact v0.1 wire
    shape while the worker entry can carry a precise status and reason.
    """

    status: WorkerStatusValue
    reason_code: WorkerReasonCode
    last_seen_at: str | None = None
    age_seconds: float | None = None


class ReadinessResponse(BaseModel):
    status: Literal["ready", "degraded"]
    dependencies: list[DependencyStatus | WorkerDependencyStatus]


class RuntimeStatusResponse(BaseModel):
    """Non-sensitive runtime configuration for the UI header badge.

    Deliberately excludes credentials and endpoint URLs; adding fields
    here requires the same review as exposing them publicly.
    """

    provider: Literal["fake", "openai"]
    model: str
    #: The research extractor, reported separately because it is configured
    #: independently — a deployment can draft with a real model while still
    #: researching with the Fake one, and the panel must say so.
    research_provider: Literal["fake", "openai", "deepseek"]
    research_model: str
    environment: str
    real_data_gate: Literal["enabled", "blocked"]
