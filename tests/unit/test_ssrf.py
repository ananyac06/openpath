"""Unit tests for SSRF boundary enforcement and URL validation."""

import pytest

from openpath.exceptions import SSRFSecurityViolation
from openpath.network.ssrf import validate_safe_url


def test_ssrf_rejects_non_http_schemes() -> None:
    for invalid_url in [
        "file:///etc/passwd",
        "ftp://example.com/file",
        "gopher://example.com",
        "data:text/html,<h1>Hello</h1>",
        "javascript:alert(1)",
    ]:
        with pytest.raises(SSRFSecurityViolation) as exc_info:
            validate_safe_url(invalid_url)
        assert "Unsupported scheme" in str(exc_info.value)


def test_ssrf_rejects_localhost_and_internal_hosts() -> None:
    for forbidden_host in [
        "http://localhost:8080/admin",
        "http://127.0.0.1:5000",
        "http://metadata.google.internal/computeMetadata/v1/",
    ]:
        with pytest.raises(SSRFSecurityViolation):
            validate_safe_url(forbidden_host)


def test_ssrf_allows_public_https_domains(monkeypatch: pytest.MonkeyPatch) -> None:
    # Mock DNS resolution to public IP so unit tests run hermetically offline
    import socket

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )
    validate_safe_url("https://boards-api.greenhouse.io/v1/boards/groww/jobs")
    validate_safe_url("https://api.lever.co/v0/postings/meesho")
    validate_safe_url("https://api.ashbyhq.com/posting-api/job-board/posthog")
