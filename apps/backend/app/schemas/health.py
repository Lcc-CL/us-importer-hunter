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
    research_provider: Literal["fake", "openai"]
    research_model: str
    environment: str
