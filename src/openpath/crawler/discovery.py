"""Live source discovery.

Probes candidate ATS board slugs against their public job-board APIs and
registers only boards that return live postings, so the crawler's coverage
grows without registering dead or invented sources.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from urllib.parse import quote_plus

from openpath.data.source_candidates import CANDIDATE_BOARDS
from openpath.db.repository import Repository
from openpath.models.entities import AuthorityTier, Source

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DiscoveryResult:
    """Outcome of probing one candidate board."""

    source_id: str
    connector_id: str
    board_token: str
    company_name: str
    url: str
    jobs_found: int
    status: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "registered"


def _board_urls(connector_id: str, token: str) -> tuple[str, str]:
    """Return (jobs_api_url, careers_page_url) for a board token."""
    if connector_id in ("ats.greenhouse", "greenhouse"):
        return (
            f"https://boards-api.greenhouse.io/v1/boards/{quote_plus(token)}/jobs",
            f"https://boards.greenhouse.io/{quote_plus(token)}",
        )
    if connector_id in ("ats.lever", "lever"):
        return (
            f"https://api.lever.co/v0/postings/{quote_plus(token)}?mode=json",
            f"https://jobs.lever.co/{quote_plus(token)}",
        )
    return (
        f"https://api.ashbyhq.com/posting-api/job-board/{quote_plus(token)}",
        f"https://jobs.ashbyhq.com/{quote_plus(token)}",
    )


def _source_for(connector_id: str, token: str, company_name: str, jobs_url: str) -> Source:
    """Build a Source row for a board confirmed to exist."""
    jobs_api, careers_page = _board_urls(connector_id, token)
    pretty = company_name or token.replace("-", " ").title()
    return Source(
        id=f"{connector_id.split('.')[-1]}.{token}",
        connector_id=connector_id,
        name=pretty,
        category="ats",
        base_url=jobs_url,
        authority_tier=AuthorityTier.ATS,
        access_method="public_api",
        policy_url=careers_page,
        enabled=True,
        metadata={
            "board_token": token,
            "company_name": pretty,
            "website_url": careers_page,
            "jobs_api": jobs_api,
            "region": "global",
        },
    )


async def discover_sources(
    http_client: object,
    repo: Repository,
    connectors: dict[str, tuple[str, ...]] | None = None,
    probe_limit: int | None = None,
) -> list[DiscoveryResult]:
    """Probe candidate boards and register the ones returning live postings.

    Each probe is an unauthenticated GET of the board's public jobs endpoint.
    Boards that answer 200 with at least one posting are registered; 404/403
    and empty boards are skipped entirely (never registered).
    """
    boards = connectors or CANDIDATE_BOARDS
    results: list[DiscoveryResult] = []

    existing = {s.id for s in repo.list_sources()}

    async def probe(connector_id: str, token: str) -> DiscoveryResult:
        jobs_url, _ = _board_urls(connector_id, token)
        source_id = f"{connector_id.split('.')[-1]}.{token}"
        try:
            res = await http_client.fetch(jobs_url)  # type: ignore[attr-defined]
        except Exception as err:  # network/SSRF/paused domain
            return DiscoveryResult(
                source_id, connector_id, token, token, jobs_url, 0, "error", str(err)
            )

        if res.status_code != 200:
            return DiscoveryResult(
                source_id,
                connector_id,
                token,
                token,
                jobs_url,
                0,
                "unavailable",
                f"HTTP {res.status_code}",
            )

        # Count live postings by parsing the payload rather than guessing from
        # its byte size (Greenhouse/Lever use "jobs", Ashby "postings").
        try:
            payload = json.loads(res.text or "{}")
        except json.JSONDecodeError:
            return DiscoveryResult(
                source_id,
                connector_id,
                token,
                token,
                jobs_url,
                0,
                "unparsable",
                "response was not valid JSON",
            )

        if not isinstance(payload, dict):
            return DiscoveryResult(
                source_id,
                connector_id,
                token,
                token,
                jobs_url,
                0,
                "unexpected",
                "response was not a JSON object",
            )

        postings = payload.get("jobs")
        if postings is None:
            postings = payload.get("postings")
        count = len(postings) if isinstance(postings, list) else 0

        if count == 0:
            return DiscoveryResult(
                source_id,
                connector_id,
                token,
                token,
                jobs_url,
                0,
                "no_openings",
                "no live postings",
            )

        # Register the board (re-registering is idempotent).
        try:
            repo.register_source(_source_for(connector_id, token, token, jobs_url))
            existing.add(source_id)
            return DiscoveryResult(
                source_id,
                connector_id,
                token,
                token,
                jobs_url,
                count,
                "registered",
                f"{count} live posting(s)",
            )
        except Exception as err:
            return DiscoveryResult(
                source_id, connector_id, token, token, jobs_url, 0, "error", str(err)
            )

    tasks = [
        probe(connector_id, token)
        for connector_id, tokens in boards.items()
        for token in tokens
        if f"{connector_id.split('.')[-1]}.{token}" not in existing
    ]
    if probe_limit:
        tasks = tasks[:probe_limit]

    results = await asyncio.gather(*tasks, return_exceptions=False)
    return list(results)
