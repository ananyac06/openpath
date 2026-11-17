"""Asynchronous HTTP client with SSRF protection, rate limiting, and backoff."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import time
from contextlib import suppress
from urllib.parse import urlparse

import httpx

from openpath.config import CrawlerConfig
from openpath.exceptions import NetworkError, RateLimitExceeded
from openpath.network.ssrf import validate_safe_url

logger = logging.getLogger(__name__)


class FetchResult:
    """Structured result of an HTTP fetch operation."""

    def __init__(
        self,
        url: str,
        final_url: str,
        status_code: int,
        headers: dict[str, str],
        content: bytes,
        duration_ms: int,
    ) -> None:
        self.url = url
        self.final_url = final_url
        self.status_code = status_code
        self.headers = headers
        self.content = content
        self.duration_ms = duration_ms
        self._hash: str | None = None

    @property
    def content_hash(self) -> str:
        """SHA-256 hexadecimal digest of content."""
        if self._hash is None:
            self._hash = hashlib.sha256(self.content).hexdigest()
        return self._hash

    @property
    def text(self) -> str:
        """Decoded text content (UTF-8 with replacement)."""
        return self.content.decode("utf-8", errors="replace")


class DomainRateLimiter:
    """Token-bucket rate limiter per domain."""

    def __init__(self, rps: float = 1.0) -> None:
        self.rps = max(0.1, rps)
        self.interval = 1.0 / self.rps
        self._last_request_time: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, domain: str) -> None:
        async with self._lock:
            now = time.monotonic()
            last_time = self._last_request_time.get(domain, 0.0)
            elapsed = now - last_time
            if elapsed < self.interval:
                wait_time = self.interval - elapsed
                await asyncio.sleep(wait_time)
            self._last_request_time[domain] = time.monotonic()


class CircuitBreaker:
    """Circuit breaker for failing domains."""

    def __init__(self, error_threshold: int = 3, cooldown_seconds: int = 300) -> None:
        self.error_threshold = error_threshold
        self.cooldown_seconds = cooldown_seconds
        self._failure_counts: dict[str, int] = {}
        self._paused_until: dict[str, float] = {}

    def is_paused(self, domain: str) -> bool:
        paused_at = self._paused_until.get(domain)
        return bool(paused_at and time.monotonic() < paused_at)

    def record_success(self, domain: str) -> None:
        self._failure_counts[domain] = 0
        self._paused_until.pop(domain, None)

    def record_failure(self, domain: str) -> None:
        count = self._failure_counts.get(domain, 0) + 1
        self._failure_counts[domain] = count
        if count >= self.error_threshold:
            self._paused_until[domain] = time.monotonic() + self.cooldown_seconds
            logger.warning("Circuit breaker tripped for domain %s. Paused for %d seconds.", domain, self.cooldown_seconds)


class SafeHttpClient:
    """Hardened async HTTP client enforcing SSRF protection and rate limits."""

    def __init__(self, config: CrawlerConfig) -> None:
        self.config = config
        self.rate_limiter = DomainRateLimiter(rps=config.default_rate_limit_rps)
        self.circuit_breaker = CircuitBreaker(
            error_threshold=config.circuit_breaker_error_threshold,
            cooldown_seconds=config.circuit_breaker_cooldown_seconds,
        )
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": self.config.user_agent},
                timeout=httpx.Timeout(
                    timeout=self.config.request_timeout_seconds,
                    connect=self.config.connect_timeout_seconds,
                ),
                follow_redirects=False,  # Redirects manually validated for SSRF
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def fetch(
        self,
        url: str,
        etag: str | None = None,
        if_modified_since: str | None = None,
    ) -> FetchResult:
        """Fetch URL with SSRF checks, rate limiting, and exponential retries."""
        current_url = url
        redirect_hops = 0
        max_redirects = 5

        while redirect_hops <= max_redirects:
            # 1. SSRF Validation
            validate_safe_url(current_url)

            domain = urlparse(current_url).hostname or ""
            if self.circuit_breaker.is_paused(domain):
                raise NetworkError(f"Domain '{domain}' is temporarily paused by circuit breaker.")

            # 2. Rate limit acquisition
            await self.rate_limiter.acquire(domain)

            headers = {}
            if etag:
                headers["If-None-Match"] = etag
            if if_modified_since:
                headers["If-Modified-Since"] = if_modified_since

            client = await self._get_client()
            start_time = time.monotonic()

            try:
                response = await self._execute_with_retry(client, current_url, headers, domain)
                duration_ms = int((time.monotonic() - start_time) * 1000)

                # Check for redirects
                if response.status_code in (301, 302, 303, 307, 308):
                    redirect_location = response.headers.get("Location")
                    if not redirect_location:
                        break
                    # Resolve relative redirect URLs
                    from urllib.parse import urljoin
                    current_url = urljoin(current_url, redirect_location)
                    redirect_hops += 1
                    continue

                self.circuit_breaker.record_success(domain)
                return FetchResult(
                    url=url,
                    final_url=current_url,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    content=response.content,
                    duration_ms=duration_ms,
                )

            except Exception as err:
                self.circuit_breaker.record_failure(domain)
                raise NetworkError(f"Fetch failed for {current_url}: {err}") from err

        raise NetworkError(f"Exceeded max redirects ({max_redirects}) for {url}")

    async def _execute_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        domain: str,
    ) -> httpx.Response:
        """Execute request with exponential backoff on transient errors."""
        last_exception: Exception | None = None

        for attempt in range(self.config.max_retries + 1):
            try:
                response = await client.get(url, headers=headers)

                # Adhere to HTTP 429 Too Many Requests
                if response.status_code == 429:
                    retry_after_str = response.headers.get("Retry-After")
                    wait_time = 5.0
                    if retry_after_str:
                        with suppress(ValueError):
                            wait_time = float(retry_after_str)
                    logger.warning("Received 429 from %s. Sleeping for %.1f s.", url, wait_time)
                    if attempt < self.config.max_retries:
                        await asyncio.sleep(wait_time)
                        continue
                    raise RateLimitExceeded(f"Rate limit exceeded for {url}", details={"status": 429})

                # Cap max response size
                content_len = response.headers.get("Content-Length")
                if content_len and int(content_len) > self.config.max_response_bytes:
                    raise NetworkError(f"Response size {content_len} bytes exceeds maximum allowed {self.config.max_response_bytes}")

                return response

            except (httpx.RequestError, httpx.TimeoutException) as err:
                last_exception = err
                if attempt < self.config.max_retries:
                    backoff = (self.config.backoff_factor ** attempt) + random.uniform(0.1, 0.5)
                    logger.info("Transient error on %s: %s. Retrying in %.2fs...", url, err, backoff)
                    await asyncio.sleep(backoff)
                else:
                    break

        raise NetworkError(f"Failed to fetch {url} after {self.config.max_retries} attempts: {last_exception}")
