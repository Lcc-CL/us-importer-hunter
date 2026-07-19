"""Same-site rule: label-wise, derived from the user's host (ADR-0026 §2)."""

import pytest

from app.tools.website.site_scope import SiteScope


class TestSiteScope:
    @pytest.mark.parametrize(
        "candidate",
        [
            "https://example.com/about",
            "https://www.example.com/about",
            "https://shop.example.com/",
            "https://deep.shop.example.com/x",
            "http://example.com/insecure",  # scheme is the guard's problem, not scope's
        ],
    )
    def test_allows_origin_www_counterpart_and_subdomains(self, candidate: str) -> None:
        scope = SiteScope.from_url("https://example.com")
        assert scope.allows(candidate) is True

    @pytest.mark.parametrize(
        "candidate",
        [
            "https://notexample.com/",        # the endswith trap
            "https://example.com.evil.com/",  # suffix smuggling
            "https://evilexample.com/",
            "https://example.org/",
            "https://example.co.uk/",         # different registrable domain
            "https://linkedin.com/company/x",
        ],
    )
    def test_rejects_lookalikes_and_other_hosts(self, candidate: str) -> None:
        scope = SiteScope.from_url("https://example.com")
        assert scope.allows(candidate) is False

    def test_www_origin_also_allows_bare_host(self) -> None:
        scope = SiteScope.from_url("https://www.example.com/")
        assert scope.allows("https://example.com/about") is True
        assert scope.allows("https://api.example.com/") is True

    def test_multi_label_tld_is_not_over_permissive(self) -> None:
        """Deliberately stricter than PSL: co.uk siblings are out of scope,
        which is the safe direction to be wrong in."""
        scope = SiteScope.from_url("https://acme.co.uk/")
        assert scope.allows("https://shop.acme.co.uk/") is True
        assert scope.allows("https://other.co.uk/") is False

    def test_case_and_trailing_dot_normalized(self) -> None:
        scope = SiteScope.from_url("https://Example.COM./")
        assert scope.allows("https://example.com/x") is True

    def test_url_without_host_is_rejected(self) -> None:
        scope = SiteScope.from_url("https://example.com")
        assert scope.allows("not-a-url") is False

    def test_cannot_build_scope_without_host(self) -> None:
        with pytest.raises(ValueError):
            SiteScope.from_url("not-a-url")
