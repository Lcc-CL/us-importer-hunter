"""Stable operator identities for business action records."""

from dataclasses import dataclass
from typing import Literal

OperatorRole = Literal["sales", "approver", "admin"]


@dataclass(frozen=True, slots=True)
class AuditActor:
    name: str
    issuer: str | None = None
    subject: str | None = None

    @property
    def verified(self) -> bool:
        return self.issuer is not None and self.subject is not None


@dataclass(frozen=True, slots=True)
class Operator:
    issuer: str
    subject: str
    name: str
    roles: frozenset[OperatorRole]

    def audit_actor(self) -> AuditActor:
        return AuditActor(self.name, self.issuer, self.subject)
