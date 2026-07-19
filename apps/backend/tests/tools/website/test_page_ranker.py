"""Page discovery is deterministic — the crawler's targets cannot be steered
by page content (ADR-0025 §6)."""

from app.tools.website.page_ranker import (
    LinkCandidate,
    extract_links,
    normalize_link,
    rank_pages,
    score_url,
)
from app.tools.website.site_scope import SiteScope

SCOPE = SiteScope.from_url("https://example.com")
BASE = "https://example.com/"


class TestNormalizeLink:
    def test_relative_links_become_absolute(self) -> None:
        assert normalize_link(BASE, "/about") == "https://example.com/about"
        assert normalize_link("https://example.com/a/b", "../c") == "https://example.com/c"

    def test_fragments_and_tracking_stripped(self) -> None:
        assert normalize_link(BASE, "/about#team") == "https://example.com/about"
        assert normalize_link(BASE, "/p?utm_source=x&id=3") == "https://example.com/p?id=3"
        assert normalize_link(BASE, "/p?utm_source=x") == "https://example.com/p"

    def test_non_navigational_schemes_dropped(self) -> None:
        for href in ["#top", "mailto:a@b.com", "tel:+1", "javascript:x()", "data:text/html,x", ""]:
            assert normalize_link(BASE, href) is None


class TestScoring:
    def test_about_outranks_products_outranks_news(self) -> None:
        about, _ = score_url("https://example.com/about")
        products, _ = score_url("https://example.com/products")
        news, _ = score_url("https://example.com/news")
        assert about > products > news > 0

    def test_categories_are_labelled(self) -> None:
        assert score_url("https://example.com/about-us")[1] == "about"
        assert score_url("https://example.com/our-services")[1] == "products"
        assert score_url("https://example.com/warehouse")[1] == "capabilities"
        assert score_url("https://example.com/contact")[1] == "contact"

    def test_chinese_paths_recognized(self) -> None:
        assert score_url("https://example.com/关于我们")[1] == "about"

    def test_anchor_text_can_classify_an_opaque_path(self) -> None:
        score, category = score_url("https://example.com/p/17", anchor_text="About our company")
        assert category == "about"
        assert score > 0

    def test_junk_paths_penalized(self) -> None:
        for url in [
            "https://example.com/cart",
            "https://example.com/login",
            "https://example.com/privacy-policy",
            "https://example.com/careers",
        ]:
            assert score_url(url)[0] < 0

    def test_assets_penalized(self) -> None:
        assert score_url("https://example.com/brochure.pdf")[0] < 0
        assert score_url("https://example.com/logo.png")[0] < 0

    def test_deeper_paths_score_lower_in_the_same_category(self) -> None:
        shallow, _ = score_url("https://example.com/about")
        deep, _ = score_url("https://example.com/about/history/1998")
        assert shallow > deep


class TestRankPages:
    def test_respects_limit_and_orders_by_score(self) -> None:
        links = [
            LinkCandidate("/news"),
            LinkCandidate("/about"),
            LinkCandidate("/products"),
            LinkCandidate("/contact"),
            LinkCandidate("/warehouse"),
        ]
        chosen = rank_pages(base_url=BASE, links=links, scope=SCOPE, limit=4)
        assert len(chosen) == 4
        assert chosen[0].url.endswith("/about")
        assert [page.score for page in chosen] == sorted(
            (page.score for page in chosen), reverse=True
        )

    def test_spreads_across_categories(self) -> None:
        """Four product pages must not consume every slot."""
        links = [LinkCandidate(f"/products/{i}") for i in range(6)] + [
            LinkCandidate("/about"),
            LinkCandidate("/contact"),
        ]
        chosen = rank_pages(base_url=BASE, links=links, scope=SCOPE, limit=3)
        categories = {page.category for page in chosen}
        assert "about" in categories
        assert "contact" in categories
        assert len(categories) == 3

    def test_off_site_links_never_selected(self) -> None:
        links = [
            LinkCandidate("https://linkedin.com/company/x", "About us"),
            LinkCandidate("https://notexample.com/about", "About"),
            LinkCandidate("/about"),
        ]
        chosen = rank_pages(base_url=BASE, links=links, scope=SCOPE, limit=5)
        assert [page.url for page in chosen] == ["https://example.com/about"]

    def test_duplicates_and_already_seen_skipped(self) -> None:
        links = [LinkCandidate("/about"), LinkCandidate("/about#team"), LinkCandidate("/about/")]
        chosen = rank_pages(
            base_url=BASE,
            links=links,
            scope=SCOPE,
            limit=5,
            already_seen=frozenset({"https://example.com/products"}),
        )
        assert len(chosen) == 1

    def test_deterministic_across_runs(self) -> None:
        links = [LinkCandidate(f"/products/{i}") for i in range(5)]
        first = rank_pages(base_url=BASE, links=links, scope=SCOPE, limit=3)
        second = rank_pages(base_url=BASE, links=links, scope=SCOPE, limit=3)
        assert [p.url for p in first] == [p.url for p in second]

    def test_discovery_reason_is_reported(self) -> None:
        chosen = rank_pages(
            base_url=BASE, links=[LinkCandidate("/about")], scope=SCOPE, limit=1
        )
        assert chosen[0].discovery_reason == "ranked:about"


class TestExtractLinks:
    def test_pulls_href_and_anchor_text(self) -> None:
        html = """
          <a href="/about">About <span>Us</span></a>
          <a href="/products">Products</a>
          <a>no href</a>
        """
        links = extract_links(html)
        assert [link.url for link in links] == ["/about", "/products"]
        assert "About" in links[0].anchor_text
