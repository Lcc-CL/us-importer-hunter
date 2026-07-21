"""Title → the responsibilities it carries.

`DeterministicRoleMatcher` is named for what it is: phrase matching over a
versioned vocabulary, with word boundaries and implication rules. It is not
semantic, and calling it semantic would misrepresent what a reviewer can rely
on. A genuine semantic matcher can implement the same protocol later; the
protocol exists so that swap does not touch callers.

The rule that shapes everything here: matching is additive. A title that says
both "sales" and "purchasing" gets both roles. Nothing removes a role because
another one also matched — that collapse is what lost real buying contacts.
"""

from dataclasses import dataclass
from typing import Protocol

from app.domain.contact.roles import (
    ROLE_DEFINITIONS,
    TAXONOMY_VERSION,
    DecisionRole,
    role_definition,
)
from app.services.contact.title_normalizer import NormalizedTitle, normalize_title


@dataclass(frozen=True)
class RoleClassification:
    """What a title means, and how much of that to trust."""

    roles: tuple[DecisionRole, ...]
    confidence: float
    method: str
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    taxonomy_version: str = TAXONOMY_VERSION
    normalized_title: str = ""
    historical_role: bool = False
    assistant_role: bool = False


class RoleMatcher(Protocol):
    """Turns a normalized title into responsibilities."""

    @property
    def method(self) -> str: ...

    def classify(self, title: NormalizedTitle) -> RoleClassification: ...


class DeterministicRoleMatcher:
    """Phrase matching over the taxonomy. Explainable, offline, free."""

    @property
    def method(self) -> str:
        return "deterministic"

    def classify(self, title: NormalizedTitle) -> RoleClassification:
        if not title.normalized_title:
            return RoleClassification(
                roles=(DecisionRole.UNKNOWN,),
                confidence=0.0,
                method=self.method,
                reasons=("no title supplied",),
                normalized_title="",
            )

        padded = title.padded
        direct: list[DecisionRole] = []
        reasons: list[str] = []
        warnings: list[str] = []

        for definition in ROLE_DEFINITIONS:
            if definition.code is DecisionRole.UNKNOWN:
                continue
            hit = next(
                (phrase for phrase in definition.positive_phrases if phrase in padded), None
            )
            if hit is None:
                continue
            veto = next(
                (phrase for phrase in definition.negative_phrases if phrase in padded), None
            )
            if veto is not None:
                warnings.append(f"{definition.code.value} vetoed by {veto.strip()!r}")
                continue
            direct.append(definition.code)
            reasons.append(f"matched {hit.strip()!r} → {definition.code.value}")

        if not direct:
            return RoleClassification(
                roles=(DecisionRole.UNKNOWN,),
                confidence=0.2,
                method=self.method,
                reasons=("no taxonomy phrase matched this title",),
                warnings=tuple(warnings),
                normalized_title=title.normalized_title,
                historical_role=title.historical_role,
                assistant_role=title.assistant_role,
            )

        # Implications are added, never substituted: an import manager buys
        # freight whether or not the title says so, and still counts as import.
        roles = list(direct)
        for role in direct:
            for implied in role_definition(role).implies:
                if implied not in roles:
                    roles.append(implied)
                    reasons.append(f"{role.value} implies {implied.value}")

        if title.historical_role:
            warnings.append(
                "title describes a former role — not a current decision maker"
            )
        if title.assistant_role:
            warnings.append("assistant or deputy level — supports the decision maker")
        if title.interim_role:
            warnings.append("interim or acting role")

        return RoleClassification(
            roles=tuple(_stable_order(roles)),
            confidence=self._confidence(direct, title),
            method=self.method,
            reasons=tuple(reasons),
            warnings=tuple(warnings),
            normalized_title=title.normalized_title,
            historical_role=title.historical_role,
            assistant_role=title.assistant_role,
        )

    @staticmethod
    def _confidence(direct: list[DecisionRole], title: NormalizedTitle) -> float:
        """How much the *classification* can be trusted — not how good a lead
        the person is. A historical title is classified confidently and is
        still the wrong person to email."""
        score = 0.6 + 0.1 * min(len(direct), 3)
        if title.seniority is not None and title.normalized_title:
            score += 0.1
        if title.historical_role:
            score -= 0.2
        return round(max(0.0, min(score, 1.0)), 3)


def _stable_order(roles: list[DecisionRole]) -> list[DecisionRole]:
    """Taxonomy order, so the same title always classifies identically."""
    order = {definition.code: index for index, definition in enumerate(ROLE_DEFINITIONS)}
    return sorted(dict.fromkeys(roles), key=lambda role: order[role])


def classify_title(raw: str | None, matcher: RoleMatcher | None = None) -> RoleClassification:
    """Convenience for callers holding a raw title string."""
    return (matcher or DeterministicRoleMatcher()).classify(normalize_title(raw))
