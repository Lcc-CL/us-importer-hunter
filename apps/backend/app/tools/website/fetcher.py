"""SafeFetcher: fetch one page under every limit ADR-0026 defines.

Redirects are followed manually so each hop can be re-validated by the guard
and re-checked against the site scope. Bodies are read in chunks and cut at the
byte cap, so an endless response cannot exhaust memory.
"""

import time
from dataclasses import dataclass, field

import httpx

from app.tools.website.site_scope import SiteScope
from app.tools.website.url_guard import (
    HostResolver,
    SystemHostResolver,
    UrlGuardPolicy,
    UrlRejected,
    validate_url,
)

HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")


def create_research_client(
    *, proxy: str | None = None, timeout: float = 10.0
) -> httpx.AsyncClient:
    """The only sanctioned way to build a client for research fetching.

    `trust_env=False` on purpose: with the default, `ALL_PROXY` / `HTTP_PROXY`
    / `HTTPS_PROXY` in the host environment would silently reroute every
    outbound research request through a proxy the operator never chose for this
    purpose. That changes the egress path — and therefore what the SSRF guard's
    IP checks actually mean, since the proxy resolves the host, not us. A proxy
    must be an explicit decision, so it is a parameter here and nothing else.
    """
    return httpx.AsyncClient(
        trust_env=False,
        proxy=proxy,
        timeout=timeout,
        follow_redirects=False,  # redirects are validated hop by hop
    )


@dataclass(frozen=True)
class FetchLimits:
    max_page_bytes: int = 2 * 1024 * 1024
    max_decompressed_bytes: int = 8 * 1024 * 1024
    request_timeout_seconds: float = 10.0
    max_redirects: int = 3
    user_agent: str = "USImporterHunterBot/0.2"


@dataclass(frozen=True)
class FetchedPage:
    """A page we actually read. `truncated` matters: a half-read page must
    never be mistaken for a complete one."""

    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    html: str
    bytes_read: int
    truncated: bool
    redirect_hops: int
    elapsed_ms: int


@dataclass(frozen=True)
class FetchFailure:
    requested_url: str
    code: str
    detail: str
    status_code: int | None = None


FetchOutcome = FetchedPage | FetchFailure


@dataclass
class SafeFetcher:
    """Fetches HTML pages. All network policy lives here; callers pass URLs."""

    limits: FetchLimits = field(default_factory=FetchLimits)
    resolver: HostResolver = field(default_factory=SystemHostResolver)
    guard_policy: UrlGuardPolicy = field(default_factory=UrlGuardPolicy)
    scope: SiteScope | None = None

    async def fetch(self, client: httpx.AsyncClient, url: str) -> FetchOutcome:
        started = time.monotonic()
        current = url
        hops = 0

        while True:
            try:
                validated = validate_url(
                    current, resolver=self.resolver, policy=self.guard_policy
                )
            except UrlRejected as exc:
                return FetchFailure(requested_url=url, code=exc.code, detail=str(exc))

            if self.scope is not None and not self.scope.allows(validated.url):
                return FetchFailure(
                    requested_url=url,
                    code="off_site",
                    detail=f"host outside the research scope: {validated.host}",
                )

            try:
                response = await self._request(client, validated.url)
            except httpx.TimeoutException:
                return FetchFailure(requested_url=url, code="timeout", detail="request timed out")
            except httpx.HTTPError as exc:
                return FetchFailure(requested_url=url, code="transport_error", detail=str(exc))

            if response.is_redirect:
                location = response.headers.get("location")
                await response.aclose()
                if not location:
                    return FetchFailure(
                        requested_url=url, code="bad_redirect", detail="redirect without location"
                    )
                hops += 1
                if hops > self.limits.max_redirects:
                    return FetchFailure(
                        requested_url=url,
                        code="too_many_redirects",
                        detail=f"exceeded {self.limits.max_redirects} redirects",
                    )
                current = str(httpx.URL(validated.url).join(location))
                continue

            return await self._read_body(
                response=response,
                requested_url=url,
                final_url=validated.url,
                hops=hops,
                started=started,
            )

    async def _request(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        request = client.build_request(
            "GET",
            url,
            headers={
                "User-Agent": self.limits.user_agent,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
                # Identity encoding keeps the byte cap meaningful and removes
                # the decompression-bomb path entirely for this request.
                "Accept-Encoding": "identity",
            },
            timeout=self.limits.request_timeout_seconds,
        )
        return await client.send(request, stream=True, follow_redirects=False)

    async def _read_body(
        self,
        *,
        response: httpx.Response,
        requested_url: str,
        final_url: str,
        hops: int,
        started: int | float,
    ) -> FetchOutcome:
        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        try:
            if response.status_code >= 400:
                return FetchFailure(
                    requested_url=requested_url,
                    code="http_error",
                    detail=f"HTTP {response.status_code}",
                    status_code=response.status_code,
                )
            if content_type and content_type not in HTML_CONTENT_TYPES:
                return FetchFailure(
                    requested_url=requested_url,
                    code="not_html",
                    detail=f"content type {content_type!r} is not HTML",
                    status_code=response.status_code,
                )

            declared = response.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > self.limits.max_page_bytes:
                return FetchFailure(
                    requested_url=requested_url,
                    code="too_large",
                    detail=f"content-length {declared} exceeds cap",
                    status_code=response.status_code,
                )

            chunks: list[bytes] = []
            total = 0
            truncated = False
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > self.limits.max_decompressed_bytes:
                    return FetchFailure(
                        requested_url=requested_url,
                        code="too_large",
                        detail="decompressed body exceeded cap",
                        status_code=response.status_code,
                    )
                if total > self.limits.max_page_bytes:
                    keep = self.limits.max_page_bytes - (total - len(chunk))
                    if keep > 0:
                        chunks.append(chunk[:keep])
                    truncated = True
                    break
                chunks.append(chunk)
        finally:
            await response.aclose()

        raw = b"".join(chunks)
        encoding = response.charset_encoding or "utf-8"
        try:
            html = raw.decode(encoding, errors="replace")
        except LookupError:
            html = raw.decode("utf-8", errors="replace")

        return FetchedPage(
            requested_url=requested_url,
            final_url=final_url,
            status_code=response.status_code,
            content_type=content_type or "text/html",
            html=html,
            bytes_read=len(raw),
            truncated=truncated,
            redirect_hops=hops,
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )
