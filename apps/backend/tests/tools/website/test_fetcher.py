"""SafeFetcher against a loopback fixture server.

Loopback is exactly what the guard forbids, so these tests inject a relaxed
guard — constructor injection, never a runtime flag (ADR-0026 §6). The strict
default is asserted separately in test_url_guard.py.
"""

import asyncio
import gzip
from collections.abc import AsyncIterator, Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import httpx
import pytest

from app.tools.website.fetcher import (
    FetchedPage,
    FetchFailure,
    FetchLimits,
    SafeFetcher,
    create_research_client,
)
from app.tools.website.site_scope import SiteScope
from app.tools.website.url_guard import UrlGuardPolicy

HTML = b"<html><body><h1>Acme</h1><p>We import fasteners.</p></body></html>"


class FixtureHandler(BaseHTTPRequestHandler):
    """Canned responses covering the shapes the fetcher must survive."""

    def log_message(self, *args: object) -> None:  # silence test output
        return

    def do_GET(self) -> None:  # noqa: N802 — stdlib naming
        path = self.path
        if path == "/":
            self._send(200, HTML, "text/html")
        elif path == "/slow":
            import time

            time.sleep(2.0)
            self._send(200, HTML, "text/html")
        elif path == "/huge":
            # Content-Length declared and over the cap → refused on headers.
            self._send(200, b"x" * (256 * 1024), "text/html")
        elif path == "/chunked-huge":
            # No Content-Length → the byte cap must bite while streaming.
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            block = b"x" * 4096
            for _ in range(64):
                self.wfile.write(b"%X\r\n" % len(block) + block + b"\r\n")
            self.wfile.write(b"0\r\n\r\n")
        elif path == "/pdf":
            self._send(200, b"%PDF-1.4", "application/pdf")
        elif path == "/missing":
            self._send(404, b"nope", "text/html")
        elif path == "/redirect-once":
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
        elif path == "/redirect-loop":
            self.send_response(302)
            self.send_header("Location", "/redirect-loop")
            self.end_headers()
        elif path == "/redirect-offsite":
            self.send_response(302)
            self.send_header("Location", "https://evil.example/")
            self.end_headers()
        elif path == "/redirect-no-location":
            self.send_response(302)
            self.end_headers()
        elif path == "/gzip-bomb":
            payload = gzip.compress(b"x" * (12 * 1024 * 1024))
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif path == "/robots.txt":
            self._send(200, b"User-agent: *\nDisallow: /private/\n", "text/plain")
        else:
            self._send(200, HTML, "text/html")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class QuietHTTPServer(HTTPServer):
    """Truncation tests close the connection early, which makes the stdlib
    handler dump a traceback. Expected here, so keep the output clean."""

    def handle_error(self, request: object, client_address: object) -> None:
        return


@pytest.fixture(scope="module")
def server() -> Iterator[str]:
    httpd = QuietHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


class LoopbackResolver:
    """Test-only resolver: the fixture server really is on 127.0.0.1."""

    def resolve(self, host: str) -> tuple[str, ...]:
        return ("127.0.0.1",)


def make_fetcher(
    base: str,
    *,
    max_page_bytes: int = 1024 * 1024,
    max_decompressed_bytes: int = 8 * 1024 * 1024,
    timeout: float = 1.0,
    max_redirects: int = 3,
) -> SafeFetcher:
    limits = FetchLimits(
        max_page_bytes=max_page_bytes,
        max_decompressed_bytes=max_decompressed_bytes,
        request_timeout_seconds=timeout,
        max_redirects=max_redirects,
    )
    return SafeFetcher(
        limits=limits,
        resolver=LoopbackResolver(),
        # Relaxed only for loopback fixtures, by explicit injection.
        guard_policy=UrlGuardPolicy(
            allowed_ports=tuple(range(1024, 65536)) + (80, 443),
            denied_hostnames=frozenset(),
            allow_private_addresses=True,
        ),
        scope=SiteScope.from_url(base),
    )


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    # trust_env=False: a developer machine may export ALL_PROXY/HTTP_PROXY
    # (Clash and similar), and routing loopback through a SOCKS proxy both
    # fails and needs an optional httpx extra.
    async with httpx.AsyncClient(trust_env=False) as ac:
        yield ac


class TestHappyPath:
    async def test_fetches_html(self, server: str, client: httpx.AsyncClient) -> None:
        result = await make_fetcher(server).fetch(client, f"{server}/")
        assert isinstance(result, FetchedPage)
        assert result.status_code == 200
        assert "We import fasteners" in result.html
        assert result.truncated is False
        assert result.bytes_read == len(HTML)


class TestLimits:
    async def test_timeout_is_reported(self, server: str, client: httpx.AsyncClient) -> None:
        result = await make_fetcher(server, timeout=0.3).fetch(client, f"{server}/slow")
        assert isinstance(result, FetchFailure)
        assert result.code == "timeout"

    async def test_declared_oversize_refused_on_headers(
        self, server: str, client: httpx.AsyncClient
    ) -> None:
        fetcher = make_fetcher(server, max_page_bytes=4096, timeout=5.0)
        result = await fetcher.fetch(client, f"{server}/huge")
        assert isinstance(result, FetchFailure)
        assert result.code == "too_large"

    async def test_undeclared_oversize_truncated_while_streaming(
        self, server: str, client: httpx.AsyncClient
    ) -> None:
        """Chunked responses carry no Content-Length, so the cap has to bite
        mid-stream — this is the path that protects memory."""
        fetcher = make_fetcher(server, max_page_bytes=8192, timeout=5.0)
        result = await fetcher.fetch(client, f"{server}/chunked-huge")
        assert isinstance(result, FetchedPage)
        assert result.truncated is True
        assert result.bytes_read <= 8192

    async def test_non_html_rejected(self, server: str, client: httpx.AsyncClient) -> None:
        result = await make_fetcher(server).fetch(client, f"{server}/pdf")
        assert isinstance(result, FetchFailure)
        assert result.code == "not_html"

    async def test_http_error_reported(self, server: str, client: httpx.AsyncClient) -> None:
        result = await make_fetcher(server).fetch(client, f"{server}/missing")
        assert isinstance(result, FetchFailure)
        assert result.code == "http_error"
        assert result.status_code == 404


class TestRedirects:
    async def test_single_redirect_followed(
        self, server: str, client: httpx.AsyncClient
    ) -> None:
        result = await make_fetcher(server).fetch(client, f"{server}/redirect-once")
        assert isinstance(result, FetchedPage)
        assert result.redirect_hops == 1
        assert "Acme" in result.html

    async def test_redirect_loop_capped(self, server: str, client: httpx.AsyncClient) -> None:
        result = await make_fetcher(server, max_redirects=2).fetch(
            client, f"{server}/redirect-loop"
        )
        assert isinstance(result, FetchFailure)
        assert result.code == "too_many_redirects"

    async def test_offsite_redirect_refused(
        self, server: str, client: httpx.AsyncClient
    ) -> None:
        """The classic SSRF shape: an allowed host redirecting elsewhere.
        Every hop is re-validated, so the second hop never happens."""
        result = await make_fetcher(server).fetch(client, f"{server}/redirect-offsite")
        assert isinstance(result, FetchFailure)
        assert result.code == "off_site"

    async def test_redirect_without_location_reported(
        self, server: str, client: httpx.AsyncClient
    ) -> None:
        result = await make_fetcher(server).fetch(client, f"{server}/redirect-no-location")
        assert isinstance(result, FetchFailure)
        assert result.code == "bad_redirect"


class TestGuardStillApplies:
    async def test_disallowed_scheme_never_reaches_the_network(
        self, server: str, client: httpx.AsyncClient
    ) -> None:
        result = await make_fetcher(server).fetch(client, "file:///etc/passwd")
        assert isinstance(result, FetchFailure)
        assert result.code == "bad_scheme"

    async def test_offsite_url_refused_before_request(
        self, server: str, client: httpx.AsyncClient
    ) -> None:
        result = await make_fetcher(server).fetch(client, "https://linkedin.com/company/x")
        assert isinstance(result, FetchFailure)
        assert result.code == "off_site"

    async def test_production_guard_rejects_the_fixture_server(
        self, server: str, client: httpx.AsyncClient
    ) -> None:
        """Proof the relaxation above is test-only: with the real policy and a
        real resolver, loopback is refused."""
        strict = SafeFetcher(scope=SiteScope.from_url(server))
        result = await strict.fetch(client, f"{server}/")
        assert isinstance(result, FetchFailure)
        assert result.code in {"denied_hostname", "private_address", "bad_port"}


class TestProxyIsolation:
    async def test_host_proxy_env_does_not_reroute_research_traffic(
        self, server: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A developer or container with ALL_PROXY set must not silently send
        research requests through it: the proxy would resolve the host instead
        of us, which is exactly what the SSRF guard's IP checks rely on."""
        monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:9")
        monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
        monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")

        async with create_research_client(timeout=5.0) as client:
            result = await make_fetcher(server, timeout=5.0).fetch(client, f"{server}/")
        assert isinstance(result, FetchedPage)
        assert "Acme" in result.html

    def test_client_does_not_trust_environment(self) -> None:
        client = create_research_client()
        assert client.trust_env is False

    async def test_proxy_must_be_passed_explicitly(self, server: str) -> None:
        """Opting in is possible — it just has to be a decision, not ambient."""
        async with create_research_client(proxy="http://127.0.0.1:9", timeout=1.0) as client:
            result = await make_fetcher(server, timeout=1.0).fetch(client, f"{server}/")
        assert isinstance(result, FetchFailure)  # the dead proxy is actually used


class TestConcurrencySafety:
    async def test_parallel_fetches_do_not_interfere(
        self, server: str, client: httpx.AsyncClient
    ) -> None:
        fetcher = make_fetcher(server)
        results = await asyncio.gather(
            *(fetcher.fetch(client, f"{server}/page-{i}") for i in range(4))
        )
        assert all(isinstance(result, FetchedPage) for result in results)
