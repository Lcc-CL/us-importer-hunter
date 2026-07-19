"""Same-site rule (ADR-0026 §2).

Scope is derived from the host the *user* supplied, never from a guessed
registrable domain. Comparison is label-wise: `notexample.com` must not match
`example.com`, which a naive `endswith` would allow.

Deliberately stricter than a public-suffix-list approach and with no PSL
dependency: taking the last two labels of `www.example.co.uk` yields `co.uk`,
which would let the crawler roam all of `*.co.uk`. The cost is that a company
on several registrable domains is only partly reachable — an acceptable
direction to be wrong in.
"""

from dataclasses import dataclass
from urllib.parse import urlsplit


def _normalize(host: str) -> str:
    return host.strip().lower().rstrip(".")


@dataclass(frozen=True)
class SiteScope:
    """The set of hosts a single research run may fetch."""

    origin_host: str
    bare_host: str

    @classmethod
    def from_url(cls, url: str) -> "SiteScope":
        host = _normalize(urlsplit(url).hostname or "")
        if not host:
            raise ValueError(f"cannot derive site scope from {url!r}")
        bare = host[4:] if host.startswith("www.") else host
        return cls(origin_host=host, bare_host=bare)

    def allows(self, url: str) -> bool:
        """True when `url`'s host is the origin, its www/non-www counterpart,
        or a subdomain of either."""
        host = _normalize(urlsplit(url).hostname or "")
        if not host:
            return False
        for base in {self.origin_host, self.bare_host}:
            if host == base or host.endswith("." + base):
                return True
        return False
