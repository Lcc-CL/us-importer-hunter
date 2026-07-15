"""Typed responses for health endpoints."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    app: str
    environment: str


class DependencyStatus(BaseModel):
    name: str
    healthy: bool
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: Literal["ready", "degraded"]
    dependencies: list[DependencyStatus]
