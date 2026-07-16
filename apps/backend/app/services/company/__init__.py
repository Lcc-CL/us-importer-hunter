"""Company service: company entity lifecycle — normalization, dedup, enrichment."""

from app.services.company.deduplicator import RepositoryCompanyDeduplicator
from app.services.company.normalizer import NormalizedClaim, SnapshotNormalizer

__all__ = ["NormalizedClaim", "RepositoryCompanyDeduplicator", "SnapshotNormalizer"]
