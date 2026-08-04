"""Typed contracts for read-only real-data acceptance preflight."""

from typing import Literal, Self

from pydantic import BaseModel

from app.services.acceptance import NetEasePreflightReport, UmailPreflightReport


class NetEasePreflightResponse(BaseModel):
    file_type: Literal["csv", "xlsx"]
    file_size_bytes: int
    file_sha256: str
    encoding: str
    sheets: list[str]
    selected_sheet: str
    total_rows: int
    analyzed_rows: int
    inferred_data_type: Literal["company", "contact", "shipment", "mixed", "unknown"]
    mapping_profile: str
    suggested_mapping: dict[str, str]
    mapping_confidence: dict[str, str]
    manual_mapping_applied: bool
    unknown_fields: list[str]
    missing_required_fields: list[str]
    duplicate_columns: list[str]
    empty_rows: int
    invalid_rows: int
    estimated_company_count: int
    estimated_contact_count: int
    estimated_trade_record_count: int
    coverage: dict[str, float]
    estimated_high_confidence_reviews: int
    estimated_medium_confidence_reviews: int
    no_business_side_effects: Literal[True]
    real_data_gate: Literal["enabled", "blocked"]

    @classmethod
    def from_report(cls, report: NetEasePreflightReport, *, gate_enabled: bool) -> Self:
        payload = dict(report.__dict__)
        payload.update(
            sheets=list(report.sheets),
            unknown_fields=list(report.unknown_fields),
            missing_required_fields=list(report.missing_required_fields),
            duplicate_columns=list(report.duplicate_columns),
            no_business_side_effects=True,
            real_data_gate="enabled" if gate_enabled else "blocked",
        )
        return cls.model_validate(payload)


class UmailPreflightResponse(BaseModel):
    file_type: Literal["csv"]
    file_size_bytes: int
    file_sha256: str
    encoding: str
    total_rows: int
    mapping_profile: str
    suggested_mapping: dict[str, str]
    mapping_confidence: dict[str, str]
    manual_mapping_applied: bool
    unknown_fields: list[str]
    missing_required_fields: list[str]
    duplicate_columns: list[str]
    event_type_distribution: dict[str, int]
    time_format_distribution: dict[str, int]
    bounce_type_distribution: dict[str, int]
    coverage: dict[str, float]
    estimated_strong_id_matches: int
    estimated_email_fallback_matches: int
    estimated_ambiguous_rows: int
    unsupported_event_count: int
    missing_occurred_at_count: int
    invalid_rows: int
    match_estimate_basis: Literal["file_identifiers_only", "database_snapshot"]
    no_business_side_effects: Literal[True]
    real_data_gate: Literal["enabled", "blocked"]

    @classmethod
    def from_report(cls, report: UmailPreflightReport, *, gate_enabled: bool) -> Self:
        payload = dict(report.__dict__)
        payload.update(
            unknown_fields=list(report.unknown_fields),
            missing_required_fields=list(report.missing_required_fields),
            duplicate_columns=list(report.duplicate_columns),
            no_business_side_effects=True,
            real_data_gate="enabled" if gate_enabled else "blocked",
        )
        return cls.model_validate(payload)
