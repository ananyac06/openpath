"""Regression tests for openpath.web.server do_GET rendering.

Bugs these tests lock down:
  1. do_GET used str.replace for only some HTML_TEMPLATE placeholders, leaving
     the rest as literal ``{name}`` text in the rendered page.
  2. do_GET had no exception handling, so a DB/render error closed the
     connection without any HTTP response (browser showed ERR_EMPTY_RESPONSE).
  3. Placeholder counts (verified, internship, entry, remote) must be
     substituted with real integers rather than left raw.
"""

from __future__ import annotations

import re
import types
from typing import Any

from openpath.models.entities import Opportunity, WorkMode
from openpath.web.server import HTML_TEMPLATE, LocalViewerHandler


def _make_repo(fail: bool = False) -> Any:
    opps = [
        Opportunity(
            company_name="SDE Co",
            canonical_application_url="https://sde.example/job1",
            title="Software Engineering Intern",
            locations=["Bangalore"],
            work_mode=WorkMode.REMOTE,
            admission_class="VERIFIED",
        ),
        Opportunity(
            company_name="OpenCo",
            canonical_application_url="https://openco.example/job1",
            title="Graduate Engineer",
            locations=[],
            work_mode=WorkMode.HYBRID,
            admission_class="VERIFIED",
        ),
    ]
    orgs = [
        {
            "canonical_name": "SDE Co",
            "legal_name": "SDE Company",
            "country": "US",
            "category": "us_sp500",
            "website_url": "https://sde.example",
            "registry_id": "SDE-1",
            "live_jobs_count": 2,
        }
    ]

    def list_opportunities(**_: object) -> list[Opportunity]:
        if fail:
            raise RuntimeError("db down")
        return list(opps)

    def list_organisations(**_: object) -> list[dict[str, object]]:
        return list(orgs)

    return types.SimpleNamespace(
        list_opportunities=list_opportunities,
        list_organisations=list_organisations,
    )


class _WFile:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def write(self, data: bytes) -> int:
        self.chunks.append(data)
        return len(data)

    @property
    def body(self) -> bytes:
        return b"".join(self.chunks)


def _handler(path: str = "/", fail: bool = False) -> LocalViewerHandler:
    """Build a real handler instance without invoking BaseHTTPRequestHandler init."""
    handler = object.__new__(LocalViewerHandler)
    handler.path = path  # type: ignore[assignment]
    handler.repo = _make_repo(fail=fail)  # type: ignore[assignment]
    handler.wfile = _WFile()  # type: ignore[assignment]
    handler.headers = {}  # type: ignore[assignment]
    return handler


def _record_calls(handler: LocalViewerHandler) -> list[tuple[str, int]]:
    calls: list[tuple[str, int]] = []
    handler.send_response = lambda code, *a: calls.append(("response", code))  # type: ignore[method-assign]
    handler.send_error = lambda code, *a: calls.append(("error", code))  # type: ignore[method-assign]
    handler.send_header = lambda *a: None  # type: ignore[method-assign]
    handler.end_headers = lambda: None  # type: ignore[method-assign]
    handler.log_message = lambda *a: None  # type: ignore[method-assign]
    return calls


def _render(fail: bool = False) -> str:
    handler = _handler(fail=fail)
    body = handler._render_page()
    return body.decode("utf-8")


def test_do_get_leaves_no_literal_placeholders() -> None:
    body = _render()
    leftover = re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", body)
    assert leftover == [], f"unrendered placeholders remain: {leftover[:20]}"


def test_do_get_replaces_all_template_placeholders() -> None:
    body = _render()
    placeholders = set(re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", HTML_TEMPLATE))
    missing = [name for name in placeholders if f"{{{name}}}" in body]
    assert missing == [], f"placeholders not replaced: {missing}"


def test_do_get_opportunities_count_rendered() -> None:
    body = _render()
    assert ">2<" in body, "expected total_opportunities=2 in body"


def test_do_get_directory_cards_rendered() -> None:
    body = _render()
    assert "SDE Co" in body
    assert "SDE Company" in body


def test_do_get_exception_yields_500() -> None:
    handler = _handler(fail=True)
    calls = _record_calls(handler)
    handler.do_GET()
    codes = [code for kind, code in calls]
    assert 500 in codes, f"expected HTTP 500 on render failure, got {calls}"
    # No success response may be sent on failure.
    assert ("response", 200) not in calls


def test_do_get_unknown_path_yields_404() -> None:
    handler = _handler(path="/does-not-exist")
    calls = _record_calls(handler)
    handler.do_GET()
    assert 404 in [code for _, code in calls]


def test_html_template_is_well_formed_for_replace() -> None:
    weird = [m for m in re.findall(r"\{(?![a-zA-Z_][a-zA-Z0-9_]*\})(\{[^}]*\})", HTML_TEMPLATE)]
    assert weird == [], f"non-placeholder braces in template: {weird[:5]}"
