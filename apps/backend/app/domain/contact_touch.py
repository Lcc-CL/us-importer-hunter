"""Shared contact windows for the SMTP and offline Umail channels."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from app.domain.umail_export import UmailExportRow

DEFAULT_CONTACT_WINDOW_HOURS = 168


@dataclass(frozen=True, slots=True)
class UmailTouchResult:
    export_row_id: UUID
    email: str
    occurred_at: datetime


class ContactTouchRepository(Protocol):
    async def reserve_export(
        self,
        rows: tuple[UmailExportRow, ...],
        *,
        window: timedelta,
    ) -> None: ...

    async def record_export_results(self, results: tuple[UmailTouchResult, ...]) -> None: ...
