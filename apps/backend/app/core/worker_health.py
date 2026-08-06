"""Shared, non-sensitive worker heartbeat contract.

The heartbeat payload is a small JSON document — owner plus a UTC heartbeat
timestamp — so the readiness probe can distinguish a fresh heartbeat from a
missing, expired or malformed one without ever exposing connection details.
"""

import json
from datetime import datetime
from typing import TypedDict

WORKER_HEARTBEAT_KEY = "us_importer_hunter:worker:heartbeat"
#: How long a heartbeat stays valid without a refresh. Larger than the
#: refresh interval so a single missed write does not flip the worker to
#: unavailable, but small enough that a stopped worker is detected quickly.
WORKER_HEARTBEAT_TTL_SECONDS = 15
#: How often the worker refreshes its heartbeat, independently of job length.
WORKER_HEARTBEAT_REFRESH_SECONDS = 5


class WorkerHeartbeat(TypedDict):
    owner: str
    heartbeat_at: str


def build_worker_heartbeat(owner: str, now: datetime) -> str:
    """Serialize the non-sensitive heartbeat payload."""
    return json.dumps(
        {"owner": owner, "heartbeat_at": now.isoformat()},
        separators=(",", ":"),
    )


def parse_worker_heartbeat(payload: str | None) -> WorkerHeartbeat | None:
    """Parse a heartbeat payload; return None when it is invalid."""
    if not payload:
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    owner = data.get("owner")
    heartbeat_at = data.get("heartbeat_at")
    if not isinstance(owner, str) or not isinstance(heartbeat_at, str):
        return None
    return WorkerHeartbeat(owner=owner, heartbeat_at=heartbeat_at)
