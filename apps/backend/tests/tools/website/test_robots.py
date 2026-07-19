"""robots.txt handling (ADR-0026 §4): obeyed, and failure means allow."""

from urllib.robotparser import RobotFileParser

from app.tools.website.robots import RobotsPolicy, robots_url_for


def policy_from(text: str, user_agent: str = "USImporterHunterBot/0.2") -> RobotsPolicy:
    parser = RobotFileParser()
    parser.parse(text.splitlines())
    return RobotsPolicy(user_agent=user_agent, parser=parser, fetched=True)


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

    def test_rules_targeting_our_agent_are_honoured(self) -> None:
        """robotparser matches on the token before "/" in our UA, so a
        robots.txt naming `USImporterHunterBot` applies to
        `USImporterHunterBot/0.2` and overrides the `*` group."""
        policy = policy_from(
            "User-agent: USImporterHunterBot\nDisallow: /nope/\n\n"
            "User-agent: *\nDisallow: /\n"
        )
        assert policy.allows("https://example.com/nope/x") is False
        assert policy.allows("https://example.com/about") is True

    def test_versioned_agent_line_does_not_match_and_star_applies(self) -> None:
        """The mirror case, recorded because it is surprising: a robots.txt
        line carrying our version string is *longer* than the token we match
        on, so it does not apply and the `*` group wins."""
        policy = policy_from(
            "User-agent: USImporterHunterBot/0.2\nDisallow: /nope/\n\n"
            "User-agent: *\nDisallow: /\n"
        )
        assert policy.allows("https://example.com/about") is False

    def test_empty_robots_allows_everything(self) -> None:
        assert policy_from("").allows("https://example.com/anything") is True


class TestFailureIsAllow:
    def test_unreachable_robots_means_allow(self) -> None:
        """Standard convention: no robots.txt is not a prohibition."""
        policy = RobotsPolicy(
            user_agent="USImporterHunterBot/0.2",
            parser=None,
            fetched=False,
            note="robots.txt unreachable — treating as allow",
        )
        assert policy.allows("https://example.com/anything") is True
        assert policy.fetched is False
        assert policy.note is not None
