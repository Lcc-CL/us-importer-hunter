"""Aggregate API router for the v1 prefix."""

from fastapi import APIRouter

from app.api.routes import (
    bulk_import,
    discovery_tasks,
    health,
    import_evidence,
    import_resolution,
    mvp,
    prospect_batches,
    prospect_routing,
    research,
)

api_router = APIRouter()
api_router.include_router(bulk_import.router)
api_router.include_router(import_resolution.router)
api_router.include_router(health.router)
api_router.include_router(mvp.router)
api_router.include_router(research.router)
api_router.include_router(import_evidence.router)
api_router.include_router(discovery_tasks.router)
api_router.include_router(prospect_batches.router)
api_router.include_router(prospect_routing.router)
