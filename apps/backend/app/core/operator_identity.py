"""Verify OIDC ID tokens using a configured issuer and cached signing keys."""

import asyncio
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

import httpx
import jwt

from app.core.config import Settings
from app.domain.operator import Operator


class IdentityUnavailableError(Exception):
    """The configured issuer's signed keys could not be loaded."""


class OperatorRoleMissingError(Exception):
    """The authenticated subject has no configured workspace role."""


def _https_url(value: str, *, issuer: bool = False) -> bool:
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
        and (not issuer or not parsed.query)
    )


class OperatorIdentityVerifier:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if (
            not _https_url(settings.operator_oidc_issuer, issuer=True)
            or not _https_url(settings.operator_oidc_jwks_url)
            or not settings.operator_oidc_audience.strip()
            or not any(settings.operator_role_groups.values())
        ):
            raise ValueError("OIDC issuer, audience, JWKS URL and role mapping are required")
        self.settings = settings
        self.transport = transport
        self.keys: dict[str, jwt.PyJWK] = {}
        self.expires_at = 0.0
        self.refresh_after = 0.0
        self.lock = asyncio.Lock()

    async def verify(self, token: str) -> Operator:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if header.get("alg") != "RS256" or not isinstance(kid, str) or not kid:
            raise jwt.InvalidTokenError("Unsupported signing header")
        signing_key = await self._key(kid)
        audience = self.settings.operator_oidc_audience
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=self.settings.operator_oidc_issuer,
            leeway=15,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
        authorized_party = claims.get("azp")
        audiences = claims["aud"]
        if authorized_party is not None or (isinstance(audiences, list) and len(audiences) > 1):
            if authorized_party != audience:
                raise jwt.InvalidTokenError("Unexpected authorized party")
        subject = claims["sub"]
        if (
            not isinstance(subject, str)
            or not subject
            or len(subject) > 255
            or any(ord(char) < 32 for char in subject)
        ):
            raise jwt.InvalidTokenError("Invalid subject")
        raw_groups = claims.get("groups", [])
        groups = (
            {value for value in raw_groups if isinstance(value, str)}
            if (isinstance(raw_groups, list))
            else set()
        )
        roles = frozenset(
            role
            for role, identifiers in self.settings.operator_role_groups.items()
            if groups.intersection(identifiers)
        )
        if not roles:
            raise OperatorRoleMissingError
        raw_name = claims.get("name")
        name = raw_name if isinstance(raw_name, str) else ""
        name = "".join(char for char in name if ord(char) >= 32).strip()
        return Operator(
            self.settings.operator_oidc_issuer,
            subject,
            name[:160] or subject[:160],
            roles,
        )

    async def _key(self, kid: str) -> jwt.PyJWK:
        async with self.lock:
            now = monotonic()
            if kid in self.keys and now < self.expires_at:
                return self.keys[kid]
            if now >= self.refresh_after:
                # Limit refreshes for unknown key IDs, including concurrent requests.
                self.refresh_after = now + 10
                await self._refresh()
            if monotonic() >= self.expires_at:
                raise IdentityUnavailableError
            if kid not in self.keys:
                raise jwt.InvalidTokenError("Unknown signing key")
            return self.keys[kid]

    async def _refresh(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=4, transport=self.transport) as client:
                response = await client.get(self.settings.operator_oidc_jwks_url)
                response.raise_for_status()
                document: Any = response.json()
            candidates = document.get("keys") if isinstance(document, dict) else None
            if not isinstance(candidates, list) or len(candidates) > 128:
                raise ValueError("Invalid JWKS")
            keys: dict[str, jwt.PyJWK] = {}
            for raw in candidates:
                if (
                    not isinstance(raw, dict)
                    or raw.get("kty") != "RSA"
                    or raw.get("use", "sig") != "sig"
                    or raw.get("alg", "RS256") != "RS256"
                    or not isinstance(raw.get("kid"), str)
                    or "d" in raw
                ):
                    continue
                kid = raw["kid"]
                if kid in keys:
                    raise ValueError("Duplicate signing key ID")
                keys[kid] = jwt.PyJWK.from_dict(raw, algorithm="RS256")
            if not keys:
                raise ValueError("No suitable signing keys")
        except (httpx.HTTPError, jwt.PyJWTError, ValueError, TypeError, KeyError):
            raise IdentityUnavailableError from None
        self.keys = keys
        self.expires_at = monotonic() + 300
