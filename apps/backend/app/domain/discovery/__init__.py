"""Discovery domain (Discovery context): finding importer claims.

Produces events only (CompanyDiscovered / DiscoveryCompleted /
DiscoveryFailed) — never creates Company or Opportunity aggregates and
never scores (ADR-0018).
"""

from app.domain.discovery.aggregate import (
    TERMINAL_RUN_STATUSES,
    DiscoveryRun,
    DiscoveryRunStatus,
)
from app.domain.discovery.values import (
    DiscoveryResult,
    DiscoveryStats,
    RawCompanySnapshot,
    Signal,
)

__all__ = [
    "TERMINAL_RUN_STATUSES",
    "DiscoveryResult",
    "DiscoveryRun",
    "DiscoveryRunStatus",
    "DiscoveryStats",
    "RawCompanySnapshot",
    "Signal",
]
