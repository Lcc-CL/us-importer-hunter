"""Small, non-leaking HTTP error mapping for the MVP API."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas.mvp import ApiErrorResponse
from app.shared.exceptions import (
    ApplicationConflictError,
    EvidenceReviewIncompleteError,
    InvalidInputError,
    ProviderUnavailableError,
    ResourceNotFoundError,
)

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


def _response(request: Request, *, status: int, code: str, message: str) -> JSONResponse:
    payload = ApiErrorResponse(
        code=code,
        message=message,
        request_id=_request_id(request),
    )
    return JSONResponse(status_code=status, content=payload.model_dump(mode="json"))


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        return _response(
            request,
            status=422,
            code="request_validation_error",
            message="Request validation failed",
        )

    @app.exception_handler(ResourceNotFoundError)
    async def resource_not_found(
        request: Request, exc: ResourceNotFoundError
    ) -> JSONResponse:
        return _response(request, status=404, code="resource_not_found", message=str(exc))

    @app.exception_handler(ApplicationConflictError)
    async def application_conflict(
        request: Request, exc: ApplicationConflictError
    ) -> JSONResponse:
        return _response(request, status=409, code="invalid_state", message=str(exc))

    @app.exception_handler(EvidenceReviewIncompleteError)
    async def evidence_review_incomplete(
        request: Request, exc: EvidenceReviewIncompleteError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "code": exc.code,
                "message": str(exc),
                "pending_claim_count": exc.pending_claim_count,
                "request_id": _request_id(request),
            },
        )

    @app.exception_handler(InvalidInputError)
    async def invalid_input(request: Request, exc: InvalidInputError) -> JSONResponse:
        return _response(request, status=422, code=exc.code, message=str(exc))

    @app.exception_handler(ProviderUnavailableError)
    async def provider_unavailable(
        request: Request, _exc: ProviderUnavailableError
    ) -> JSONResponse:
        return _response(
            request,
            status=503,
            code="provider_unavailable",
            message="The configured provider is unavailable",
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API error", exc_info=exc)
        return _response(
            request,
            status=500,
            code="internal_error",
            message="An unexpected error occurred",
        )
