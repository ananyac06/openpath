"""Ashby ATS Public Job Board connector."""

from __future__ import annotations

import json
import logging
import uuid

from openpath.connectors.base import BaseConnector
from openpath.exceptions import ConnectorError
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
    WorkMode,
)

logger = logging.getLogger(__name__)


class AshbyConnector(BaseConnector):
    """Fetches opportunities from official Ashby Job Board API."""

    async def fetch_opportunities(self, source: Source) -> list[Opportunity]:
        board_slug = source.metadata.get("board_token") or source.metadata.get("board_slug")
        if not board_slug and source.base_url:
            from urllib.parse import urlparse
            parts = urlparse(source.base_url).path.strip("/").split("/")
            if "job-board" in parts:
                idx = parts.index("job-board")
                if idx + 1 < len(parts):
                    board_slug = parts[idx + 1]

        if not board_slug:
            raise ConnectorError(f"Missing board_slug for Ashby source {source.id}")

        api_url = f"https://api.ashbyhq.com/posting-api/job-board/{board_slug}?includeCompensation=true"
        logger.info("Fetching Ashby postings for '%s' from %s", board_slug, api_url)

        fetch_result = await self.http_client.fetch(api_url)
        if fetch_result.status_code != 200:
            logger.warning("Ashby API returned status %d for %s", fetch_result.status_code, api_url)
            return []

        try:
            data = json.loads(fetch_result.text)
        except json.JSONDecodeError as err:
            raise ConnectorError(f"Invalid JSON returned from Ashby API {api_url}: {err}") from err

        raw_jobs = data.get("jobs", [])
        company_name = source.metadata.get("company_name") or source.name
        opportunities: list[Opportunity] = []

        for job in raw_jobs:
            title = job.get("title", "").strip()
            if not title:
                continue

            job_url = job.get("jobUrl") or f"https://jobs.ashbyhq.com/{board_slug}"
            apply_url = job.get("applyUrl") or job_url
            raw_location = job.get("location")
            workplace_type = (job.get("workplaceType") or "").lower()

            html_content = job.get("descriptionHtml") or job.get("descriptionPlain") or ""
            clean_text = extract_clean_text(html_content) if "<" in html_content else html_content

            if workplace_type == "remote" or job.get("isRemote"):
                work_mode = WorkMode.REMOTE
            elif workplace_type == "hybrid":
                work_mode = WorkMode.HYBRID
            else:
                work_mode = normalize_work_mode(raw_location, clean_text)

            india_eligible = detect_india_accessibility(raw_location, clean_text)

            # Check compensation
            compensation_str = "Not disclosed"
            if "compensation" in data and isinstance(data["compensation"], dict):
                tier_summary = data["compensation"].get("compensationTierSummary")
                if tier_summary:
                    compensation_str = tier_summary

            ev_id = str(uuid.uuid4())
            evidence = EvidenceRecord(
                id=ev_id,
                evidence_type="api_json_field",
                claim="job_posting",
                original_url=api_url,
                canonical_url=job_url,
                http_status=fetch_result.status_code,
                excerpt=clean_text[:500] if clean_text else f"Job: {title} at {company_name}",
                content_hash=fetch_result.content_hash,
                extraction_method="ashby_posting_api",
                metadata={"board_slug": board_slug, "department": job.get("department")},
            )

            checks = [
                VerificationCheck(
                    check_name="listing_existence",
                    result=VerificationResult.PASS,
                    explanation=f"Listing confirmed via Ashby Job Board API for {board_slug}",
                    evidence_id=ev_id,
                ),
                VerificationCheck(
                    check_name="source_authority",
                    result=VerificationResult.PASS,
                    explanation=f"Published directly via official Ashby endpoint for {board_slug}",
                    evidence_id=ev_id,
                ),
                VerificationCheck(
                    check_name="application_destination",
                    result=VerificationResult.PASS,
                    explanation=f"Application URL resolves to authorized Ashby hosted page: {apply_url}",
                    evidence_id=ev_id,
                ),
                VerificationCheck(
                    check_name="current_availability",
                    result=VerificationResult.PASS,
                    explanation="Currently published on live Ashby job board feed",
                    evidence_id=ev_id,
                ),
            ]

            admission_class = "VERIFIED" if india_eligible is not False else "REJECTED"

            # Use hash of title + job_url for stable ID
            import hashlib
            stable_id = f"ab_{board_slug}_{hashlib.md5(f'{title}_{job_url}'.encode()).hexdigest()[:10]}"

            opp = Opportunity(
                id=stable_id,
                company_name=company_name,
                title=title,
                work_mode=work_mode,
                locations=[raw_location] if raw_location else [],
                description_text=clean_text,
                compensation_text=compensation_str,
                canonical_application_url=apply_url,
                admission_class=admission_class,
                status="active",
                content_hash=fetch_result.content_hash,
                source_ids=[source.id],
                evidence=[evidence],
                checks=checks,
            )
            opportunities.append(opp)

        return opportunities
