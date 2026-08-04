"""Read-only real-data acceptance helpers."""

from app.services.acceptance.preflight import (
    ACCEPTANCE_MAX_BYTES,
    ACCEPTANCE_MAX_ROWS,
    NETEASE_MAPPING_PROFILE,
    AcceptancePreflightError,
    NetEasePreflightReport,
    RealDataPreflightService,
    UmailPreflightReport,
)

__all__ = [
    "ACCEPTANCE_MAX_BYTES",
    "ACCEPTANCE_MAX_ROWS",
    "NETEASE_MAPPING_PROFILE",
    "AcceptancePreflightError",
    "NetEasePreflightReport",
    "RealDataPreflightService",
    "UmailPreflightReport",
]
