"""Time helpers for the domain layer: UTC-aware everywhere."""

from datetime import UTC, datetime

from app.domain.exceptions import DomainError


def utcnow() -> datetime:
    """Current time, timezone-aware, UTC."""
    return datetime.now(UTC)


def ensure_utc(value: datetime, *, field: str) -> datetime:
    """Reject naive datetimes; normalize aware ones to UTC."""
    if value.tzinfo is None:
        raise DomainError(f"{field} must be timezone-aware (UTC)")
    return value.astimezone(UTC)
