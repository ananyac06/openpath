"""Company career page crawler and ATS endpoint auto-discovery."""

from __future__ import annotations

import json
import logging
import re

from lxml import html

from openpath.connectors.base import BaseConnector
from openpath.extraction.parser import (
    detect_india_accessibility,
    extract_clean_text,
    normalize_work_mode,
)
from openpath.models.entities import (
    EvidenceRecord,
    Opportunity,
    Source,
    VerificationCheck,
    VerificationResult,
)

logger = logging.getLogger(__name__)

# ATS URL detection patterns
GREENHOUSE_REGEX = re.compile(
    r"https?://(?:boards|job-boards|job-boards\.eu)\.greenhouse\.io/([a-zA-Z0-9_\-]+)",
    re.IGNORECASE,
)
LEVER_REGEX = re.compile(
    r"https?://jobs\.lever\.co/([a-zA-Z0-9_\-]+)",
    re.IGNORECASE,
)
ASHBY_REGEX = re.compile(
    r"https?://jobs\.ashbyhq\.com/([a-zA-Z0-9_\-]+)",
    re.IGNORECASE,
)


class DiscoveredATSBoard:
    def __init__(self, provider: str, board_token: str, original_url: str) -> None:
        self.provider = provider
        self.board_token = board_token
        self.original_url = original_url


def detect_ats_links(page_html: str) -> list[DiscoveredATSBoard]:
    """Inspect page HTML for links pointing to Greenhouse, Lever, or Ashby job boards."""
    discovered: list[DiscoveredATSBoard] = []
    seen: set[tuple[str, str]] = set()

    for match in GREENHOUSE_REGEX.finditer(page_html):
        token = match.group(1).lower()
        if ("greenhouse", token) not in seen and token not in ("embed", "v1", "job"):
            seen.add(("greenhouse", token))
            discovered.append(DiscoveredATSBoard("greenhouse", token, match.group(0)))

    for match in LEVER_REGEX.finditer(page_html):
        token = match.group(1).lower()
        if ("lever", token) not in seen and token not in ("apply", "embed"):
            seen.add(("lever", token))
            discovered.append(DiscoveredATSBoard("lever", token, match.group(0)))

    for match in ASHBY_REGEX.finditer(page_html):
        token = match.group(1).lower()
        if ("ashby", token) not in seen and token not in ("api", "apply"):
            seen.add(("ashby", token))
            discovered.append(DiscoveredATSBoard("ashby", token, match.group(0)))

    return discovered


class CareerPageSpider(BaseConnector):
    """Crawls official company career pages and extracts job postings or detects ATS boards."""

    async def fetch_opportunities(self, source: Source) -> list[Opportunity]:
        if not source.base_url:
            return []

        logger.info("Crawling career page for %s: %s", source.name, source.base_url)
        fetch_res = await self.http_client.fetch(source.base_url)
        if fetch_res.status_code != 200:
            logger.warning(
                "Career page %s returned status %d", source.base_url, fetch_res.status_code
            )
            return []

        page_html = fetch_res.text
        # 1. Check for ATS board links on the career page
        ats_boards = detect_ats_links(page_html)
        if ats_boards:
            for board in ats_boards:
                logger.info(
                    "Auto-discovered %s ATS board '%s' on %s",
                    board.provider,
                    board.board_token,
                    source.base_url,
                )

        # 2. Extract JSON-LD schema.org/JobPosting if present
        opportunities: list[Opportunity] = []
        try:
            tree = html.fromstring(page_html)
            scripts = tree.xpath("//script[@type='application/ld+json']/text()")
            for script in scripts:
                if not isinstance(script, str):
                    continue
                try:
                    data = json.loads(script)
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        if item.get("@type") == "JobPosting":
                            opp = self._parse_json_ld_job(
                                item, source, fetch_res.url, fetch_res.content_hash
                            )
                            if opp:
                                opportunities.append(opp)
                except Exception:
                    continue
        except Exception as err:
            logger.debug("HTML parsing for %s encountered: %s", source.base_url, err)

        return opportunities

    def _parse_json_ld_job(
        self,
        data: dict,
        source: Source,
        source_url: str,
        content_hash: str,
    ) -> Opportunity | None:
        title = data.get("title")
        if not title:
            return None

        clean_title = str(title).strip()
        desc = extract_clean_text(str(data.get("description", "")))
        job_url = data.get("url") or source_url

        # Location extraction
        job_loc = data.get("jobLocation", {})
        raw_loc = None
        if isinstance(job_loc, dict):
            address = job_loc.get("address", {})
            if isinstance(address, dict):
                raw_loc = address.get("addressLocality") or address.get("addressCountry")
            elif isinstance(address, str):
                raw_loc = address

        work_mode = normalize_work_mode(raw_loc, desc)
        india_eligible = detect_india_accessibility(raw_loc, desc)

        company_info = data.get("hiringOrganization", {})
        company_name = company_info.get("name") if isinstance(company_info, dict) else source.name

        import uuid

        ev_id = str(uuid.uuid4())
        evidence = EvidenceRecord(
            id=ev_id,
            evidence_type="json_ld",
            claim="job_posting",
            original_url=source_url,
            canonical_url=job_url,
            http_status=200,
            excerpt=desc[:500] if desc else clean_title,
            content_hash=content_hash,
            extraction_method="schema_org_json_ld",
        )

        checks = [
            VerificationCheck(
                check_name="listing_existence",
                result=VerificationResult.PASS,
                explanation="Structured Schema.org/JobPosting metadata found on official domain",
                evidence_id=ev_id,
            ),
            VerificationCheck(
                check_name="source_authority",
                result=VerificationResult.PASS,
                explanation=f"Published directly on official website: {source_url}",
                evidence_id=ev_id,
            ),
        ]

        admission_class = "VERIFIED" if india_eligible is not False else "REJECTED"

        import hashlib

        stable_id = f"ld_{hashlib.md5(f'{clean_title}_{job_url}'.encode()).hexdigest()[:12]}"

        return Opportunity(
            id=stable_id,
            company_name=company_name or source.name,
            title=clean_title,
            work_mode=work_mode,
            locations=[raw_loc] if raw_loc else [],
            description_text=desc,
            canonical_application_url=job_url,
            admission_class=admission_class,
            status="active",
            content_hash=content_hash,
            source_ids=[source.id],
            evidence=[evidence],
            checks=checks,
        )
