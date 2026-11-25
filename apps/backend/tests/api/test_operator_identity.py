"""Verify real signatures against a local test JWKS, with zero IdP traffic."""

import json
from datetime import timedelta
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import Settings
from app.core.operator_identity import OperatorIdentityVerifier
from app.domain.clock import utcnow
from app.main import create_app


class TestIssuer:
    __test__ = False

    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.key_requests = 0

    def _serve_keys(self, request: httpx.Request) -> httpx.Response:
        self.key_requests += 1
        assert str(request.url) == "https://login.example.test/keys"
        public_key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        return httpx.Response(200, json={"keys": [{**public_key, "kid": "staff-key"}]})

    def configure(self, settings: Settings) -> OperatorIdentityVerifier:
        settings.operator_identity_mode = "oidc"
        settings.operator_oidc_issuer = "https://login.example.test"
        settings.operator_oidc_jwks_url = "https://login.example.test/keys"
        settings.operator_oidc_audience = "hunter-app"
        settings.operator_role_groups = {
            "sales": ["sales-group"],
            "approver": ["approver-group"],
            "admin": ["admin-group"],
        }
        return OperatorIdentityVerifier(settings, transport=httpx.MockTransport(self._serve_keys))

    def token(self, roles: list[str], subject: str = "subject-1", **extra: Any) -> str:
        now = utcnow()
        claims = {
            "iss": "https://login.example.test",
            "aud": "hunter-app",
            "sub": subject,
            "name": "Operator " + subject,
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "groups": roles,
            **extra,
        }
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": "staff-key"})

    def headers(self, role: str, subject: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token([role + '-group'], subject)}"}


async def test_private_routes_verify_issuer_audience_signature_and_roles() -> None:
    issuer = TestIssuer()
    settings = Settings(_env_file=None, app_env="production")
    verifier = issuer.configure(settings)
    app = create_app(settings)
    app.state.operator_verifier = verifier

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://test",
    ) as client:
        assert (await client.get("/api/v1/health")).status_code == 200
        unsubscribe = "/api/v1/mail-unsubscribe/751f1763-85d4-47ee-98cf-3c58b2164713"
        assert (await client.get(unsubscribe)).status_code == 200
        path = "/api/v1/mail-campaigns/config"
        assert (await client.get(path, headers={"X-Operator": "admin"})).status_code == 401
        valid = issuer.token(["sales-group"])
        tokens = [
            issuer.token(["admin-group"], aud="different-app"),
            issuer.token(["admin-group"], iss="https://different.example.test"),
            issuer.token(["admin-group"], exp=utcnow() - timedelta(minutes=1)),
            issuer.token(["admin-group"], aud=["hunter-app", "other"], azp="other"),
            valid.rsplit(".", 1)[0] + ".invalid",
        ]
        for token in tokens:
            denied = await client.get(path, headers={"Authorization": f"Bearer {token}"})
            assert denied.status_code == 401
        no_role = await client.get(
            path,
            headers={"Authorization": f"Bearer {issuer.token(['unknown'])}"},
        )
        assert no_role.status_code == 403

        # Dependency wiring on the config route expects a production session factory.
        # A public operational endpoint can still answer without one.
        identity = await verifier.verify(valid)
        assert identity.roles == frozenset({"sales"})
        assert identity.subject == "subject-1"
        assert issuer.key_requests == 1


def test_oidc_mode_requires_explicit_issuer_settings() -> None:
    with pytest.raises(ValueError, match="OIDC issuer"):
        create_app(Settings(_env_file=None, operator_identity_mode="oidc"))
