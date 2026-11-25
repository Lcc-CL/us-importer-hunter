"""Authenticate staff routes and authorize outbound-mail actions."""

import re

import jwt
from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint

from app.core.operator_identity import IdentityUnavailableError, OperatorRoleMissingError
from app.domain.operator import Operator, OperatorRole

_UNSUBSCRIBE_PATH = re.compile(
    r"/mail-unsubscribe/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.I
)


def _is_public(path: str, method: str) -> bool:
    if path == "/health":
        return method == "GET"
    if path in ("/mail-feedback", "/mail-feedback/v1"):
        return method == "POST"
    return method in ("GET", "POST") and _UNSUBSCRIBE_PATH.fullmatch(path) is not None


def _error(status: int, code: str, message: str) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JSONResponse(
        {"code": code, "message": message, "request_id": None},
        status,
        headers=headers,
    )


async def authenticate_operator(request: Request, call_next: RequestResponseEndpoint) -> Response:
    settings = request.app.state.settings
    if settings.operator_identity_mode != "oidc" or request.method == "OPTIONS":
        return await call_next(request)
    path = request.url.path
    if path.startswith(settings.api_v1_prefix + "/") and _is_public(
        path.removeprefix(settings.api_v1_prefix),
        request.method,
    ):
        return await call_next(request)
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > 16384:
        return _error(401, "operator_login_required", "A staff login is required")
    try:
        request.state.operator = await request.app.state.operator_verifier.verify(token)
    except jwt.PyJWTError:
        return _error(401, "operator_token_invalid", "Staff login is invalid or expired")
    except OperatorRoleMissingError:
        return _error(403, "operator_role_missing", "The account has no assigned workspace role")
    except IdentityUnavailableError:
        return _error(
            503, "operator_identity_unavailable", "Staff identity verification is unavailable"
        )
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


def get_operator(request: Request) -> Operator | None:
    operator = getattr(request.state, "operator", None)
    if isinstance(operator, Operator):
        return operator
    if request.app.state.settings.operator_identity_mode == "oidc":
        raise HTTPException(status_code=401, detail="A staff login is required")
    return None


def require_operator_roles(operator: Operator | None, *roles: OperatorRole) -> None:
    if operator is not None and not operator.roles.intersection(roles):
        raise HTTPException(status_code=403, detail="This workspace role cannot perform the action")
