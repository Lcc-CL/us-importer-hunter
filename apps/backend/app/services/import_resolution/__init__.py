"""Deterministic import entity-resolution services."""

from app.services.import_resolution.matcher import DeterministicEntityMatcher, EntityMatch
from app.services.import_resolution.normalization import (
    ProjectedImportRow,
    RawImportProjector,
    classify_title,
    is_department_email,
    normalize_address,
    normalize_company_name,
    normalize_domain,
    normalize_linkedin,
    normalize_phone,
    normalize_text,
)

__all__ = [
    "DeterministicEntityMatcher",
    "EntityMatch",
    "ProjectedImportRow",
    "RawImportProjector",
    "classify_title",
    "is_department_email",
    "normalize_address",
    "normalize_company_name",
    "normalize_domain",
    "normalize_linkedin",
    "normalize_phone",
    "normalize_text",
]
