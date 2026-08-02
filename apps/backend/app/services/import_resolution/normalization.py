"""Deterministic projection and normalization of raw import rows."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from app.domain.import_resolution import ImportRoleCategory
from app.domain.values import EmailAddress

_NON_ALNUM = re.compile(r"[^a-z0-9\u4e00-\u9fff]+")
_COMPANY_SUFFIX = re.compile(
    r"\b(incorporated|inc|llc|ltd|limited|corp|corporation|company|co|plc)\b"
)

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "company_name": ("company_name", "company", "公司名称", "公司", "客户名称", "企业名称"),
    "external_company_id": ("external_company_id", "company_id", "客户id", "企业id", "公司id"),
    "website": ("website", "domain", "官网", "网站", "公司网站"),
    "address": ("address", "公司地址", "地址", "注册地址"),
    "company_type": ("company_type", "公司类型", "企业类型", "客户类型"),
    "phone": ("phone", "company_phone", "公司电话", "电话"),
    "contact_name": ("contact_name", "联系人", "联系人姓名", "姓名"),
    "contact_email": ("contact_email", "email", "邮箱", "电子邮箱"),
    "contact_phone": ("contact_phone", "mobile", "联系人电话", "手机", "手机号"),
    "contact_title": ("contact_title", "title", "职位", "职务", "岗位"),
    "contact_linkedin": ("contact_linkedin", "linkedin", "linkedin_url"),
}

DEPARTMENT_EMAIL_PREFIXES = frozenset(
    {
        "admin",
        "contact",
        "customerservice",
        "export",
        "hello",
        "import",
        "info",
        "logistics",
        "office",
        "operations",
        "procurement",
        "purchase",
        "purchasing",
        "sales",
        "service",
        "shipping",
        "support",
        "warehouse",
    }
)


@dataclass(frozen=True)
class ProjectedImportRow:
    company_name: str | None
    external_company_id: str | None
    website: str | None
    normalized_domain: str | None
    address: str | None
    normalized_address: str | None
    company_type: str | None
    company_phone: str | None
    normalized_company_phone: str | None
    contact_name: str | None
    contact_email: str | None
    contact_email_domain: str | None
    contact_phone: str | None
    normalized_contact_phone: str | None
    contact_title: str | None
    contact_linkedin: str | None
    normalized_linkedin: str | None
    normalized_company_name: str | None
    normalized_contact_name: str | None
    normalized_contact_title: str | None
    role_category: ImportRoleCategory
    seniority: str
    is_department_contact: bool
    projection_warnings: tuple[str, ...]

    @property
    def has_company_data(self) -> bool:
        return any(
            (self.company_name, self.external_company_id, self.website, self.address)
        )

    @property
    def has_contact_data(self) -> bool:
        return any(
            (
                self.contact_name,
                self.contact_email,
                self.contact_phone,
                self.contact_linkedin,
            )
        )


class RawImportProjector:
    def project(
        self,
        raw_payload: Mapping[str, Any],
        *,
        mapping: Mapping[str, str],
    ) -> ProjectedImportRow:
        raw_fields = raw_payload.get("fields")
        fields = raw_fields if isinstance(raw_fields, dict) else {}
        lowered = {str(key).strip().lower(): value for key, value in fields.items()}

        def value(logical_field: str) -> str | None:
            mapped_column = mapping.get(logical_field)
            raw: object | None = fields.get(mapped_column) if mapped_column else None
            if raw is None:
                for alias in FIELD_ALIASES.get(logical_field, ()):
                    if alias.lower() in lowered:
                        raw = lowered[alias.lower()]
                        break
            if raw is None:
                return None
            cleaned = str(raw).strip()
            return cleaned or None

        warnings: list[str] = []
        company_name = value("company_name")
        website = value("website")
        normalized_domain = normalize_domain(website)
        if website and normalized_domain is None:
            warnings.append("website_invalid")
        contact_email = value("contact_email")
        contact_email_domain: str | None = None
        if contact_email:
            try:
                contact_email = EmailAddress(contact_email).value
                contact_email_domain = contact_email.rsplit("@", 1)[1]
            except Exception:
                warnings.append("contact_email_invalid")
                contact_email = None
        contact_linkedin = value("contact_linkedin")
        normalized_linkedin = normalize_linkedin(contact_linkedin)
        if contact_linkedin and normalized_linkedin is None:
            warnings.append("contact_linkedin_invalid")
        contact_title = value("contact_title")
        role_category, seniority = classify_title(contact_title)
        is_department_contact = is_department_email(contact_email)
        contact_name = value("contact_name")
        if contact_name is None and is_department_contact:
            local_part = (contact_email or "department@").split("@", 1)[0]
            contact_name = f"{local_part.replace('.', ' ').replace('_', ' ').title()} Department"
        if normalized_domain and contact_email_domain and normalized_domain != contact_email_domain:
            warnings.append("email_domain_mismatch")
        if is_possible_intermediary(company_name, value("company_type")):
            warnings.append("possible_intermediary")
        return ProjectedImportRow(
            company_name=company_name,
            external_company_id=value("external_company_id"),
            website=website,
            normalized_domain=normalized_domain,
            address=value("address"),
            normalized_address=normalize_address(value("address")),
            company_type=normalize_text(value("company_type")),
            company_phone=value("phone"),
            normalized_company_phone=normalize_phone(value("phone")),
            contact_name=contact_name,
            contact_email=contact_email,
            contact_email_domain=contact_email_domain,
            contact_phone=value("contact_phone"),
            normalized_contact_phone=normalize_phone(value("contact_phone")),
            contact_title=contact_title,
            contact_linkedin=contact_linkedin,
            normalized_linkedin=normalized_linkedin,
            normalized_company_name=normalize_company_name(company_name),
            normalized_contact_name=normalize_text(contact_name),
            normalized_contact_title=normalize_text(contact_title),
            role_category=role_category,
            seniority=seniority,
            is_department_contact=is_department_contact,
            projection_warnings=tuple(warnings),
        )


def normalize_company_name(value: str | None) -> str | None:
    normalized = normalize_text(value)
    if normalized is None:
        return None
    without_suffix = _COMPANY_SUFFIX.sub(" ", normalized)
    collapsed = " ".join(without_suffix.split())
    return collapsed or normalized


def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _NON_ALNUM.sub(" ", value.lower())
    normalized = " ".join(cleaned.split())
    return normalized or None


def normalize_address(value: str | None) -> str | None:
    return normalize_text(value)


def normalize_phone(value: str | None) -> str | None:
    if value is None:
        return None
    digits = "".join(character for character in value if character.isdigit())
    return digits if len(digits) >= 7 else None


def normalize_domain(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip().lower()
    if "@" in candidate and "://" not in candidate:
        candidate = candidate.rsplit("@", 1)[1]
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    host = parsed.hostname
    if host is None or "." not in host:
        return None
    return host.removeprefix("www.")


def normalize_linkedin(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").removeprefix("www.").lower()
    path = parsed.path.strip("/").lower()
    if host != "linkedin.com" or not path:
        return None
    return f"https://www.linkedin.com/{path}"


def is_department_email(value: str | None) -> bool:
    if value is None:
        return False
    local_part = value.split("@", 1)[0].lower()
    compact = re.sub(r"[^a-z]", "", local_part)
    return compact in DEPARTMENT_EMAIL_PREFIXES


def classify_title(value: str | None) -> tuple[ImportRoleCategory, str]:
    normalized = normalize_text(value) or ""
    role_rules: tuple[tuple[ImportRoleCategory, tuple[str, ...]], ...] = (
        (ImportRoleCategory.OWNER_FOUNDER, ("owner", "founder", "co founder", "proprietor")),
        (
            ImportRoleCategory.EXECUTIVE,
            ("chief executive", "ceo", "president", "general manager", "managing director"),
        ),
        (ImportRoleCategory.PROCUREMENT, ("procurement", "purchasing", "buyer", "sourcing")),
        (ImportRoleCategory.SUPPLY_CHAIN, ("supply chain", "planning")),
        (ImportRoleCategory.LOGISTICS, ("logistics", "transportation", "shipping")),
        (ImportRoleCategory.OPERATIONS, ("operations", "operation")),
        (ImportRoleCategory.IMPORT_EXPORT, ("import", "export", "trade compliance")),
        (ImportRoleCategory.WAREHOUSE, ("warehouse", "distribution center", "fulfillment")),
        (ImportRoleCategory.SALES, ("sales", "business development", "account manager")),
        (ImportRoleCategory.IRRELEVANT, ("human resources", "recruiter", "legal", "accounting")),
    )
    category = ImportRoleCategory.UNKNOWN
    for candidate, keywords in role_rules:
        if any(keyword in normalized for keyword in keywords):
            category = candidate
            break
    seniority_rules: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("c_level", ("chief ", " ceo", " cfo", " coo", "cto")),
        ("vp", ("vice president", " vp ", "svp", "evp")),
        ("director", ("director",)),
        ("head", ("head",)),
        ("manager", ("manager", "supervisor")),
        ("specialist", ("specialist", "coordinator", "analyst", "buyer")),
    )
    seniority = "unknown"
    padded = f" {normalized} "
    for seniority_candidate, keywords in seniority_rules:
        if any(keyword in padded for keyword in keywords):
            seniority = seniority_candidate
            break
    return category, seniority


def is_possible_intermediary(company_name: str | None, company_type: str | None) -> bool:
    text = f"{company_name or ''} {company_type or ''}".lower()
    return any(
        keyword in text
        for keyword in ("freight forward", "customs broker", "warehouse", "3pl", "货代", "报关")
    )
