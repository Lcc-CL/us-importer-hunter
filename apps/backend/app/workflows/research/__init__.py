"""Research workflow: deep-dive analysis of a single company on demand,
outside the full lead-generation pipeline.

v0.2: website → fetched pages → cleaned text → extracted claims → validated
claims persisted as a ResearchRun. Never writes Company or Opportunity state.
"""

from app.workflows.research.workflow import (
    ClientFactory,
    FetcherFactory,
    ReadPage,
    ResearchAction,
    ResearchLimits,
    ResearchOutcome,
    ResearchWorkflow,
)

__all__ = [
    "ClientFactory",
    "FetcherFactory",
    "ReadPage",
    "ResearchAction",
    "ResearchLimits",
    "ResearchOutcome",
    "ResearchWorkflow",
]
