"""Snapshot normalization: raw source text → validated domain values.

The accepting side of the Discovery boundary (ADR-0018/0019): raw claim
text becomes CompanyName / WebsiteUrl here, or the claim is rejected.
"""

from dataclasses import dataclass

from app.domain.discovery import RawCompanySnapshot
from app.domain.exceptions import InvalidWebsiteUrl
from app.domain.values import CompanyName, WebsiteUrl


@dataclass(frozen=True)
class NormalizedClaim:
    """A claim whose identity fields passed validation."""

    name: CompanyName
    website: WebsiteUrl | None
    website_dropped: bool = False  # website_text existed but was unusable


class SnapshotNormalizer:
    """Deterministic normalization; raises InvalidCompanyName when the
    claim has no usable name (the claim is then rejected upstream)."""

    def normalize(self, snapshot: RawCompanySnapshot) -> NormalizedClaim:
        name = CompanyName(snapshot.name_text)
        website: WebsiteUrl | None = None
        website_dropped = False
        if snapshot.website_text and snapshot.website_text.strip():
            raw = snapshot.website_text.strip()
            if "://" not in raw:
                raw = f"https://{raw}"
            try:
                website = WebsiteUrl(raw)
            except InvalidWebsiteUrl:
                website_dropped = True
        return NormalizedClaim(name=name, website=website, website_dropped=website_dropped)
