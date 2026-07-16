"""Contact candidate normalization: raw claim text → validated values.

An unusable name rejects the whole candidate; an unusable single channel
is dropped with an explanatory note (never silently)."""

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from app.domain.contact import (
    ContactChannel,
    ContactChannelType,
    Department,
    JobTitle,
    PersonName,
    RawContactSnapshot,
    SeniorityLevel,
)
from app.domain.exceptions import InvalidEmailAddress
from app.domain.values import EmailAddress

_DEPARTMENT_KEYWORDS: tuple[tuple[Department, tuple[str, ...]], ...] = (
    (Department.SUPPLY_CHAIN, ("supply chain",)),
    (Department.LOGISTICS, ("logistics", "shipping", "freight", "transport")),
    (Department.PROCUREMENT, ("procurement", "purchasing", "sourcing", "buyer")),
    (Department.OPERATIONS, ("operations", "ops")),
    (Department.FINANCE, ("finance", "accounting", "controller")),
    (Department.SALES_MARKETING, ("sales", "marketing", "growth")),
    (Department.HR, ("human resources", "hr ", "people ops", "recruit")),
    (Department.EXECUTIVE, ("ceo", "coo", "cfo", "president", "founder", "owner")),
)

_SENIORITY_KEYWORDS: tuple[tuple[SeniorityLevel, tuple[str, ...]], ...] = (
    (
        SeniorityLevel.C_LEVEL,
        ("ceo", "coo", "cfo", "cio", "chief", "president", "founder", "owner"),
    ),
    (SeniorityLevel.VP, ("vp", "vice president")),
    (SeniorityLevel.DIRECTOR, ("director",)),
    (SeniorityLevel.HEAD, ("head of", "head,")),
    (SeniorityLevel.MANAGER, ("manager", "lead")),
    (SeniorityLevel.SPECIALIST, ("specialist", "coordinator", "analyst", "assistant")),
)

_PHONE_DIGITS_RE = re.compile(r"\d")


@dataclass(frozen=True)
class NormalizedContactCandidate:
    """A candidate whose identity fields passed validation."""

    name: PersonName
    title: JobTitle | None
    department: Department
    seniority: SeniorityLevel
    email: ContactChannel | None
    linkedin: ContactChannel | None
    phone: ContactChannel | None
    dropped_notes: tuple[str, ...] = ()

    @property
    def channels(self) -> tuple[ContactChannel, ...]:
        return tuple(c for c in (self.email, self.linkedin, self.phone) if c is not None)


class ContactNormalizer:
    """Deterministic; raises DomainError only when the name is unusable
    (the candidate is then REJECTED upstream)."""

    def normalize(self, snapshot: RawContactSnapshot) -> NormalizedContactCandidate:
        name = PersonName(snapshot.raw_name)
        title = self._normalize_title(snapshot.raw_title)
        department, seniority = self._classify(title)
        notes: list[str] = []
        email = self._normalize_email(snapshot, notes)
        linkedin = self._normalize_linkedin(snapshot, notes)
        phone = self._normalize_phone(snapshot, notes)
        return NormalizedContactCandidate(
            name=name,
            title=title,
            department=department,
            seniority=seniority,
            email=email,
            linkedin=linkedin,
            phone=phone,
            dropped_notes=tuple(notes),
        )

    @staticmethod
    def _normalize_title(raw_title: str | None) -> JobTitle | None:
        if raw_title is None or not raw_title.strip():
            return None
        return JobTitle(raw_title)

    @staticmethod
    def _classify(title: JobTitle | None) -> tuple[Department, SeniorityLevel]:
        if title is None:
            return Department.UNKNOWN, SeniorityLevel.UNKNOWN
        lowered = f" {title.normalized} "
        department = Department.OTHER
        for candidate, keywords in _DEPARTMENT_KEYWORDS:
            if any(keyword in lowered for keyword in keywords):
                department = candidate
                break
        seniority = SeniorityLevel.UNKNOWN
        for level, keywords in _SENIORITY_KEYWORDS:
            if any(keyword in lowered for keyword in keywords):
                seniority = level
                break
        return department, seniority

    def _normalize_email(
        self, snapshot: RawContactSnapshot, notes: list[str]
    ) -> ContactChannel | None:
        if not snapshot.raw_email or not snapshot.raw_email.strip():
            return None
        try:
            email = EmailAddress(snapshot.raw_email)
        except InvalidEmailAddress:
            notes.append(f"email dropped as invalid: {snapshot.raw_email!r}")
            return None
        return ContactChannel(
            channel_type=ContactChannelType.EMAIL,
            normalized_value=email.value,
            display_value=snapshot.raw_email.strip(),
            source_reference=snapshot.source_reference,
        )

    def _normalize_linkedin(
        self, snapshot: RawContactSnapshot, notes: list[str]
    ) -> ContactChannel | None:
        if not snapshot.raw_linkedin_url or not snapshot.raw_linkedin_url.strip():
            return None
        raw = snapshot.raw_linkedin_url.strip()
        candidate = raw if "://" in raw else f"https://{raw}"
        parsed = urlparse(candidate)
        host = parsed.netloc.lower().removeprefix("www.")
        if host != "linkedin.com" or not parsed.path.strip("/"):
            notes.append(f"linkedin url dropped as invalid: {raw!r}")
            return None
        normalized = f"https://www.linkedin.com/{parsed.path.strip('/').lower()}"
        return ContactChannel(
            channel_type=ContactChannelType.LINKEDIN,
            normalized_value=normalized,
            display_value=raw,
            source_reference=snapshot.source_reference,
        )

    def _normalize_phone(
        self, snapshot: RawContactSnapshot, notes: list[str]
    ) -> ContactChannel | None:
        if not snapshot.raw_phone or not snapshot.raw_phone.strip():
            return None
        raw = snapshot.raw_phone.strip()
        digits = "".join(_PHONE_DIGITS_RE.findall(raw))
        if len(digits) < 7:
            notes.append(f"phone dropped as invalid: {raw!r}")
            return None
        normalized = f"+{digits}" if raw.lstrip().startswith("+") else digits
        return ContactChannel(
            channel_type=ContactChannelType.PHONE,
            normalized_value=normalized,
            display_value=raw,
            source_reference=snapshot.source_reference,
        )


__all__ = ["ContactNormalizer", "NormalizedContactCandidate"]
