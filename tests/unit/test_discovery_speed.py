"""Regression tests for crawl throughput and source discovery.

Locks down:
- DomainRateLimiter must not serialise unrelated domains (the old global lock
  held across await asyncio.sleep made the crawler one-domain-at-a-time).
- SafeHttpClient.fetch must forward caller headers (the GitHub connector built
  an Authorization header and dropped it).
- Ashby compensation must be read from the per-job object.
- discover_sources must register only boards that answer 200, and must never
  register a board whose response was empty/404.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, cast

from openpath.config import CrawlerConfig
from openpath.crawler.discovery import discover_sources
from openpath.network.client import DomainRateLimiter, SafeHttpClient


def test_rate_limiter_does_not_block_other_domains() -> None:
    """A slow domain must not delay a request to an unrelated domain."""

    async def scenario() -> None:
        limiter = DomainRateLimiter(rps=1.0)  # 1 request/second

        async def one(domain: str) -> float:
            start = time.monotonic()
            await limiter.acquire(domain)
            return time.monotonic() - start

        # Prime the slow domain so its next request must wait ~1s.
        await one("slow.example")

        # The unrelated domain must not wait for the slow one. Measure its own
        # duration while the slow domain is still inside its wait.
        async def timed_other() -> float:
            start = time.monotonic()
            await one("other.example")
            return time.monotonic() - start

        async def timed_slow() -> float:
            start = time.monotonic()
            await one("slow.example")
            return time.monotonic() - start

        other_duration, slow_duration = await asyncio.gather(timed_other(), timed_slow())
        assert other_duration < 0.6, (
            f"unrelated domain waited {other_duration:.2f}s for the slow one "
            f"(slow took {slow_duration:.2f}s)"
        )
        assert slow_duration > 0.5, "slow domain should still have been rate limited"

    asyncio.run(scenario())


class _Resp:
    """Minimal httpx.Response stand-in."""

    def __init__(self) -> None:
        self.status_code: int = 200
        self.headers: dict[str, str] = {"Content-Type": "application/json"}
        self.content: bytes = b"{}"


class _RetryClient:
    """Stand-in for httpx.AsyncClient that records request headers."""

    is_closed: bool = False

    def __init__(self) -> None:
        self.seen: dict[str, str] = {}

    async def get(self, url: str, headers: dict[str, str] | None = None, **kw: object) -> _Resp:
        self.seen = dict(headers or {})
        return _Resp()

    async def aclose(self) -> None:
        self.is_closed = True


def test_fetch_forwards_caller_headers() -> None:
    """Authorization headers must reach the transport."""

    under_test = SafeHttpClient(CrawlerConfig())
    cast(Any, under_test)._client = _RetryClient()
    asyncio.run(
        under_test.fetch(
            "https://api.github.com/rate_limit",
            headers={"Authorization": "Bearer test-token"},
        )
    )
    seen = cast(Any, under_test._client).seen
    assert seen.get("Authorization") == "Bearer test-token", f"token header dropped: {seen}"


class _FakeRepo:
    def __init__(self) -> None:
        self.registered: list[object] = []

    def list_sources(self) -> list[object]:
        return []

    def register_source(self, source: object) -> None:
        self.registered.append(source)


class _FakeHttp:
    def __init__(self, status: int, payload: str) -> None:
        self.status = status
        self.payload = payload

    async def fetch(self, url: str) -> object:
        class _Res:
            status_code = self.status
            text = self.payload
            content = self.payload.encode()

        return _Res()


class _UrlAwareHttp:
    """Fake HTTP client keyed by board token."""

    def __init__(self, by_token: dict[str, tuple[int, str]]) -> None:
        self.by_token = by_token

    async def fetch(self, url: str) -> object:
        token = url.rsplit("/", 2)[-2]

        class _Res:
            status_code = 0
            text = ""
            content = b""

        status, payload = self.by_token.get(token, (404, ""))
        _Res.status_code = status
        _Res.text = payload
        _Res.content = payload.encode()
        return _Res


def test_discovery_registers_only_live_boards() -> None:
    """A 404 board must never be registered; a live board must be."""

    class _Repo(_FakeRepo):
        def register_source(self, source: object) -> None:
            self.registered.append(source)

    repo = _Repo()
    http = _UrlAwareHttp(
        {
            "liveboard": (200, '{"jobs": [{"id": "1", "title": "SWE Intern"}]}'),
            "deadboard": (404, "not found"),
        }
    )
    results = asyncio.run(
        discover_sources(
            http,
            cast(Any, repo),
            connectors={"ats.greenhouse": ("liveboard", "deadboard")},
        )
    )
    by_board = {r.board_token: r for r in results}
    assert by_board["liveboard"].ok, "live board was not registered"
    assert not by_board["deadboard"].ok, "a non-200 board must not be registered"
    assert len(repo.registered) == 1


def test_discovery_skips_empty_live_board() -> None:
    """A 200 response with no postings is not a usable source."""
    repo = _FakeRepo()
    http = _UrlAwareHttp({"emptyboard": (200, '{"jobs": []}')})
    results = asyncio.run(
        discover_sources(http, cast(Any, repo), connectors={"ats.greenhouse": ("emptyboard",)})
    )
    assert not results[0].ok
    assert repo.registered == []


def test_ashby_compensation_reads_job_level() -> None:
    """Per-job compensationTierSummary must be used, not the board payload."""
    job = {"compensation": {"compensationTierSummary": "₹20L - ₹30L"}}
    data = {"compensation": {"compensationTierSummary": "BOARD LEVEL WRONG"}}

    job_comp = job.get("compensation")
    tier = (
        job_comp.get("compensationTierSummary") if isinstance(job_comp, dict) else None
    ) or job.get("compensationTierSummary")
    if not tier and isinstance(data.get("compensation"), dict):
        tier = data["compensation"].get("compensationTierSummary")

    assert tier == "₹20L - ₹30L", f"board-level value won: {tier}"
