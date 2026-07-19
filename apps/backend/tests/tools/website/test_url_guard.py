"""SSRF matrix for the URL guard (ADR-0026).

Table-driven and network-free: DNS is injected, so every hostile shape is a
row rather than a live request.
"""

import pytest

from app.tools.website.url_guard import (
    UrlGuardPolicy,
    UrlRejected,
    is_public_ip,
    validate_url,
)


class StubResolver:
    """Returns whatever the test says the host resolves to."""

    def __init__(self, mapping: dict[str, tuple[str, ...]] | None = None) -> None:
        self._mapping = mapping or {}

    def resolve(self, host: str) -> tuple[str, ...]:
        return self._mapping.get(host, ("93.184.216.34",))  # public by default


PUBLIC = StubResolver()


class TestScheme:
    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "ftp://example.com/x",
            "gopher://example.com/",
            "data:text/html,<h1>x</h1>",
            "javascript:alert(1)",
            "ws://example.com/socket",
        ],
    )
    def test_non_http_schemes_rejected(self, url: str) -> None:
        with pytest.raises(UrlRejected) as exc:
            validate_url(url, resolver=PUBLIC)
        assert exc.value.code in {"bad_scheme", "no_host"}

    @pytest.mark.parametrize("url", ["http://example.com/", "https://example.com/"])
    def test_http_and_https_allowed(self, url: str) -> None:
        assert validate_url(url, resolver=PUBLIC).host == "example.com"


class TestCredentialsAndHost:
    def test_embedded_credentials_rejected(self) -> None:
        with pytest.raises(UrlRejected) as exc:
            validate_url("https://user:pass@example.com/", resolver=PUBLIC)
        assert exc.value.code == "credentials_in_url"

    def test_missing_host_rejected(self) -> None:
        with pytest.raises(UrlRejected) as exc:
            validate_url("https:///path", resolver=PUBLIC)
        assert exc.value.code == "no_host"

    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost/",
            "http://LOCALHOST/",
            "http://api.localhost/",
            "http://service.internal/",
            "http://metadata.google.internal/computeMetadata/v1/",
            "http://printer.local/",
        ],
    )
    def test_denied_hostnames_rejected(self, url: str) -> None:
        with pytest.raises(UrlRejected) as exc:
            validate_url(url, resolver=PUBLIC)
        assert exc.value.code == "denied_hostname"


class TestPorts:
    @pytest.mark.parametrize("port", [22, 25, 3306, 5432, 6379, 8000, 8080, 11211])
    def test_non_web_ports_rejected(self, port: int) -> None:
        with pytest.raises(UrlRejected) as exc:
            validate_url(f"http://example.com:{port}/", resolver=PUBLIC)
        assert exc.value.code == "bad_port"

    def test_default_ports_inferred_from_scheme(self) -> None:
        assert validate_url("https://example.com/", resolver=PUBLIC).port == 443
        assert validate_url("http://example.com/", resolver=PUBLIC).port == 80

    def test_explicit_web_ports_allowed(self) -> None:
        assert validate_url("http://example.com:80/", resolver=PUBLIC).port == 80
        assert validate_url("https://example.com:443/", resolver=PUBLIC).port == 443


class TestResolvedAddresses:
    @pytest.mark.parametrize(
        "ip",
        [
            "127.0.0.1",         # loopback
            "127.1.2.3",
            "10.0.0.5",          # RFC1918
            "172.16.4.4",
            "172.31.255.255",
            "192.168.1.1",
            "169.254.169.254",   # cloud metadata
            "0.0.0.0",           # unspecified
            "255.255.255.255",   # reserved/broadcast
            "224.0.0.1",         # multicast
            "::1",               # IPv6 loopback
            "fc00::1",           # unique-local
            "fe80::1",           # IPv6 link-local
            "::ffff:127.0.0.1",  # IPv4-mapped loopback
        ],
    )
    def test_private_and_special_addresses_rejected(self, ip: str) -> None:
        resolver = StubResolver({"evil.example": (ip,)})
        with pytest.raises(UrlRejected) as exc:
            validate_url("https://evil.example/", resolver=resolver)
        assert exc.value.code == "private_address"

    def test_any_private_address_in_the_set_rejects(self) -> None:
        """A host answering with one public and one private address is hostile;
        validating only the first record is the bypass."""
        resolver = StubResolver({"mixed.example": ("93.184.216.34", "127.0.0.1")})
        with pytest.raises(UrlRejected) as exc:
            validate_url("https://mixed.example/", resolver=resolver)
        assert exc.value.code == "private_address"

    def test_public_addresses_allowed(self) -> None:
        resolver = StubResolver({"ok.example": ("93.184.216.34", "2606:2800:220:1::1")})
        validated = validate_url("https://ok.example/x", resolver=resolver)
        assert validated.resolved_ips == ("93.184.216.34", "2606:2800:220:1::1")

    def test_unresolvable_host_rejected(self) -> None:
        resolver = StubResolver({"ghost.example": ()})
        with pytest.raises(UrlRejected) as exc:
            validate_url("https://ghost.example/", resolver=resolver)
        assert exc.value.code == "dns_failure"


class TestIsPublicIp:
    @pytest.mark.parametrize("ip", ["93.184.216.34", "1.1.1.1", "2606:2800:220:1::1"])
    def test_public(self, ip: str) -> None:
        assert is_public_ip(ip) is True

    @pytest.mark.parametrize(
        "ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "not-an-ip", ""]
    )
    def test_not_public(self, ip: str) -> None:
        assert is_public_ip(ip) is False


class TestPolicyIsConfigurable:
    def test_policy_can_widen_ports_for_tests_only(self) -> None:
        """Loopback fixtures need a relaxed guard; it is constructor injection,
        never a runtime flag (ADR-0026 §6)."""
        policy = UrlGuardPolicy(allowed_ports=(80, 443, 8931), denied_hostnames=frozenset())
        resolver = StubResolver({"example.com": ("93.184.216.34",)})
        validated = validate_url("http://example.com:8931/", resolver=resolver, policy=policy)
        assert validated.port == 8931

    def test_default_policy_still_rejects_that_port(self) -> None:
        with pytest.raises(UrlRejected):
            validate_url("http://example.com:8931/", resolver=PUBLIC)

    def test_private_addresses_allowed_only_by_explicit_injection(self) -> None:
        resolver = StubResolver({"fixture.test": ("127.0.0.1",)})
        relaxed = UrlGuardPolicy(denied_hostnames=frozenset(), allow_private_addresses=True)
        assert validate_url("http://fixture.test/", resolver=resolver, policy=relaxed).host

    def test_private_addresses_rejected_by_default(self) -> None:
        """The escape hatch above must be opt-in at construction: no setting,
        env var or flag can enable it in a deployed environment."""
        assert UrlGuardPolicy().allow_private_addresses is False
        resolver = StubResolver({"fixture.test": ("127.0.0.1",)})
        with pytest.raises(UrlRejected) as exc:
            validate_url("http://fixture.test/", resolver=resolver)
        assert exc.value.code == "private_address"
