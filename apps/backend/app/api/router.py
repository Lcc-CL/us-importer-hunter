"""Aggregate API router for the v1 prefix."""

from fastapi import APIRouter

from app.api.routes import health, import_evidence, mvp, research

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(mvp.router)
api_router.include_router(research.router)
api_router.include_router(import_evidence.router)
