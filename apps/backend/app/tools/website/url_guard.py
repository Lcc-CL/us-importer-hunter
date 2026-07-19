"""URL guard: the only thing standing between a user-supplied URL and SSRF.

A pure function over (url, resolved_ips) — no network, no I/O — so the whole
attack matrix is table-driven unit tests. DNS resolution is injected via the
HostResolver protocol (ADR-0026).

Every request re-validates, including after every redirect hop: checking only
the URL the user typed is the standard bypass, because a permitted host can
redirect to 127.0.0.1.
"""

import ipaddress
import socket
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlsplit

DEFAULT_ALLOWED_SCHEMES = ("http", "https")
DEFAULT_ALLOWED_PORTS = (80, 443)

# Exact hostnames and suffixes that never resolve to anything we may fetch.
DENIED_HOSTNAMES = frozenset({"localhost", "metadata.google.internal"})
DENIED_HOST_SUFFIXES = (".localhost", ".internal", ".local")


class UrlRejected(Exception):
    """The URL must not be fetched. The message names the failing rule."""

    def __init__(self, reason: str, *, code: str) -> None:
        super().__init__(reason)
        self.code = code


class HostResolver(Protocol):
    """Resolves a hostname to every address it currently points at."""

    def resolve(self, host: str) -> tuple[str, ...]: ...


class SystemHostResolver:
    """Production resolver. Returns every A/AAAA record, not just the first —
    a host that resolves to one public and one private address is hostile."""

    def resolve(self, host: str) -> tuple[str, ...]:
        try:
            infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise UrlRejected(f"host does not resolve: {host}", code="dns_failure") from exc
        return tuple({str(info[4][0]) for info in infos})


@dataclass(frozen=True)
class UrlGuardPolicy:
    allowed_schemes: tuple[str, ...] = DEFAULT_ALLOWED_SCHEMES
    allowed_ports: tuple[int, ...] = DEFAULT_ALLOWED_PORTS
    denied_hostnames: frozenset[str] = field(default_factory=lambda: DENIED_HOSTNAMES)
    denied_suffixes: tuple[str, ...] = DENIED_HOST_SUFFIXES
    max_redirects: int = 3
    # Test-only escape hatch for loopback fixture servers (ADR-0026 §6).
    # Constructor injection by design: there is deliberately no setting, env
    # var or runtime flag that can turn this on in a deployed environment.
    allow_private_addresses: bool = False


@dataclass(frozen=True)
class ValidatedUrl:
    """A URL that passed every rule, with the addresses it resolved to.

    `resolved_ips` is carried so the fetcher can compare the peer address it
    actually connected to against what we validated (ADR-0026 §6 residual
    DNS-rebinding window).
    """

    url: str
    scheme: str
    host: str
    port: int
    resolved_ips: tuple[str, ...]


def is_public_ip(raw: str) -> bool:
    """False for every address family we refuse to talk to.

    Checked explicitly rather than via `is_global` alone: the flags below are
    the ones that matter for SSRF and reading them by name keeps the rule
    auditable. Covers loopback, RFC1918, link-local (169.254.0.0/16, which is
    where cloud metadata lives), unique-local, multicast, reserved and
    unspecified.
    """
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return False
    if (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        return False
    # IPv6 transition addresses can smuggle a private IPv4 inside a public-looking v6.
    if isinstance(address, ipaddress.IPv6Address):
        mapped = address.ipv4_mapped or getattr(address, "sixtofour", None)
        if mapped is not None and not is_public_ip(str(mapped)):
            return False
    return True


def _reject_hostname(host: str, policy: UrlGuardPolicy) -> None:
    lowered = host.lower().rstrip(".")
    if lowered in policy.denied_hostnames:
        raise UrlRejected(f"hostname is denied: {host}", code="denied_hostname")
    if any(lowered.endswith(suffix) for suffix in policy.denied_suffixes):
        raise UrlRejected(f"hostname suffix is denied: {host}", code="denied_hostname")


def validate_url(
    url: str,
    *,
    resolver: HostResolver,
    policy: UrlGuardPolicy | None = None,
) -> ValidatedUrl:
    """Validate one URL. Raises UrlRejected; never returns a partial result."""
    policy = policy or UrlGuardPolicy()
    parts = urlsplit(url.strip())

    if parts.scheme.lower() not in policy.allowed_schemes:
        raise UrlRejected(f"scheme not allowed: {parts.scheme!r}", code="bad_scheme")
    if parts.username or parts.password:
        raise UrlRejected("URL must not embed credentials", code="credentials_in_url")

    host = parts.hostname
    if not host:
        raise UrlRejected("URL has no host", code="no_host")
    _reject_hostname(host, policy)

    try:
        port = parts.port
    except ValueError as exc:  # e.g. "http://x:notaport/"
        raise UrlRejected("invalid port", code="bad_port") from exc
    port = port or (443 if parts.scheme.lower() == "https" else 80)
    if port not in policy.allowed_ports:
        raise UrlRejected(f"port not allowed: {port}", code="bad_port")

    resolved = resolver.resolve(host)
    if not resolved:
        raise UrlRejected(f"host does not resolve: {host}", code="dns_failure")
    for ip in resolved:
        if not policy.allow_private_addresses and not is_public_ip(ip):
            # Do not echo the address back to the caller verbatim in user-facing
            # paths; the code is what matters for the response.
            raise UrlRejected(
                f"host resolves to a non-public address: {host}",
                code="private_address",
            )

    return ValidatedUrl(
        url=url.strip(),
        scheme=parts.scheme.lower(),
        host=host,
        port=port,
        resolved_ips=resolved,
    )
