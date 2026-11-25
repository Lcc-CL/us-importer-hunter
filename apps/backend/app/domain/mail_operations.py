"""Read-only view of the active delivery queue and its workers."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

MAIL_PULSE_INTERVAL_SECONDS = 10
MAIL_PULSE_TTL_SECONDS = 45

DispatchState = Literal[
    "disabled",
    "not_configured",
    "worker_config_mismatch",
    "no_worker",
    "poll_stale",
    "polling",
]


@dataclass(frozen=True, slots=True)
class MailWorkerActivity:
    sender_hash: str | None
    verified_only: bool
    poll_age_seconds: float | None
    completion_age_seconds: float | None


@dataclass(frozen=True, slots=True)
class MailQueueFacts:
    observed_at: datetime
    ready: int
    scheduled: int
    paused: int
    blocked: int
    in_flight: int
    expired_leases: int
    unknown: int
    oldest_ready_seconds: int | None
    live_workers: int
    dispatch_workers: int
    compatible_workers: int
    polling_workers: int
    last_poll_at: datetime | None
    last_completion_at: datetime | None


@dataclass(frozen=True, slots=True)
class MailQueueStatus:
    dispatch_state: DispatchState
    queue: MailQueueFacts


class MailOperationsStore(Protocol):
    async def snapshot(
        self,
        sender_hash: str | None,
        *,
        verified_only: bool,
    ) -> MailQueueFacts: ...
