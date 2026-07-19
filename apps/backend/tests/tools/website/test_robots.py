"""robots.txt handling (ADR-0026 §4): obeyed, and failure means allow."""

from urllib.robotparser import RobotFileParser

import pytest

from app.tools.website.robots import (
    ROBOTS_TOKEN,
    RobotsPolicy,
    normalize_robots_text,
    robots_token_from_user_agent,
    robots_url_for,
)

FULL_USER_AGENT = "USImporterHunterBot/0.2 (+https://example.com/bot)"


def policy_from(text: str, user_agent: str = FULL_USER_AGENT) -> RobotsPolicy:
    """Build a policy exactly the way production does — same normalization,
    same token derivation."""
    parser = RobotFileParser()
    parser.parse(normalize_robots_text(text).splitlines())
    return RobotsPolicy(
        robots_token=robots_token_from_user_agent(user_agent),
        parser=parser,
        fetched=True,
    )


class TestTokenDerivation:
    @pytest.mark.parametrize(
        "user_agent",
        [
            "USImporterHunterBot",
            "USImporterHunterBot/0.2",
            "USImporterHunterBot/0.2 (+https://example.com/bot)",
            "USImporterHunterBot/1.0 (+contact)",
        ],
    )
    def test_all_ua_forms_reduce_to_the_product_token(self, user_agent: str) -> None:
        assert robots_token_from_user_agent(user_agent) == ROBOTS_TOKEN

    def test_empty_user_agent_falls_back_to_the_token(self) -> None:
        assert robots_token_from_user_agent("/1.0") == ROBOTS_TOKEN


class TestNormalization:
    def test_version_suffix_stripped_from_agent_lines(self) -> None:
        text = "User-agent: USImporterHunterBot/0.2\nDisallow: /x/\n"
        assert "User-agent: USImporterHunterBot\n" in normalize_robots_text(text)

    def test_star_group_untouched(self) -> None:
        assert "User-agent: *" in normalize_robots_text("User-agent: *\nDisallow: /\n")

    def test_rules_and_other_directives_untouched(self) -> None:
        text = "User-agent: Foo/1\nDisallow: /a/b.html\nCrawl-delay: 5\nSitemap: https://x/s.xml"
        out = normalize_robots_text(text)
        assert "Disallow: /a/b.html" in out
        assert "Crawl-delay: 5" in out
        assert "Sitemap: https://x/s.xml" in out

    def test_unrelated_agents_still_do_not_match_us(self) -> None:
        """Normalization can only make us obey more rules, never fewer."""
        policy = policy_from("User-agent: SomeOtherBot/1.0\nDisallow: /\n")
        assert policy.allows("https://example.com/anything") is True


class TestRobotsUrl:
    def test_derived_from_origin_root(self) -> None:
        assert robots_url_for("https://example.com/about/us") == "https://example.com/robots.txt"
        assert robots_url_for("http://example.com") == "http://example.com/robots.txt"

    def test_port_is_preserved(self) -> None:
        assert robots_url_for("https://example.com:443/x") == "https://example.com:443/robots.txt"


class TestDecisions:
    def test_disallowed_path_is_refused(self) -> None:
        policy = policy_from("User-agent: *\nDisallow: /private/\n")
        assert policy.allows("https://example.com/private/secret") is False
        assert policy.allows("https://example.com/about") is True

    def test_disallow_all_blocks_everything_including_homepage(self) -> None:
        policy = policy_from("User-agent: *\nDisallow: /\n")
        assert policy.allows("https://example.com/") is False
        assert policy.allows("https://example.com/about") is False

    def test_robots_line_without_version_applies_to_us(self) -> None:
        """The common real-world form: sites name the bare product token."""
        policy = policy_from(
            "User-agent: USImporterHunterBot\nDisallow: /nope/\n\n"
            "User-agent: *\nDisallow: /\n"
        )
        assert policy.allows("https://example.com/nope/x") is False
        assert policy.allows("https://example.com/about") is True

    def test_robots_line_with_version_also_applies_to_us(self) -> None:
        """The reason we match on the bare token: handing robotparser the full
        versioned UA made a versioned robots line fail to apply, silently
        falling through to `*`. Matching on the token fixes both forms."""
        policy = policy_from(
            "User-agent: USImporterHunterBot/0.2\nDisallow: /nope/\n\n"
            "User-agent: *\nDisallow: /\n"
        )
        assert policy.allows("https://example.com/nope/x") is False
        assert policy.allows("https://example.com/about") is True

    def test_both_forms_agree(self) -> None:
        """Whatever a site writes, our decision must be the same."""
        rules = "Disallow: /nope/\n\nUser-agent: *\nDisallow: /\n"
        bare = policy_from(f"User-agent: USImporterHunterBot\n{rules}")
        versioned = policy_from(f"User-agent: USImporterHunterBot/0.2\n{rules}")
        for url in ["https://example.com/nope/x", "https://example.com/about"]:
            assert bare.allows(url) == versioned.allows(url)

    def test_empty_robots_allows_everything(self) -> None:
        assert policy_from("").allows("https://example.com/anything") is True


class TestFailureIsAllow:
    def test_unreachable_robots_means_allow(self) -> None:
        """Standard convention: no robots.txt is not a prohibition."""
        policy = RobotsPolicy(
            robots_token=ROBOTS_TOKEN,
            parser=None,
            fetched=False,
            note="robots.txt unreachable — treating as allow",
        )
        assert policy.allows("https://example.com/anything") is True
        assert policy.fetched is False
        assert policy.note is not None
