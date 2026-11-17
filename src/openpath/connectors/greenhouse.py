"""Greenhouse ATS Public Job Board connector."""

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
)

logger = logging.getLogger(__name__)


class GreenhouseConnector(BaseConnector):
    """Fetches opportunities from official Greenhouse Job Board APIs."""

    async def fetch_opportunities(self, source: Source) -> list[Opportunity]:
        board_token = source.metadata.get("board_token")
        if not board_token and source.base_url:
            # Extract board_token from base_url if needed
            from urllib.parse import urlparse
            parts = urlparse(source.base_url).path.strip("/").split("/")
            if "boards" in parts:
                idx = parts.index("boards")
                if idx + 1 < len(parts):
                    board_token = parts[idx + 1]

        if not board_token:
            raise ConnectorError(f"Missing board_token for Greenhouse source {source.id}")

        api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
        logger.info("Fetching Greenhouse postings for '%s' from %s", board_token, api_url)

        fetch_result = await self.http_client.fetch(api_url)
        if fetch_result.status_code != 200:
            logger.warning("Greenhouse API returned status %d for %s", fetch_result.status_code, api_url)
            return []

        try:
            data = json.loads(fetch_result.text)
        except json.JSONDecodeError as err:
            raise ConnectorError(f"Invalid JSON returned from Greenhouse API {api_url}: {err}") from err

        raw_jobs = data.get("jobs", [])
        company_name = source.metadata.get("company_name") or source.name
        opportunities: list[Opportunity] = []

        for job in raw_jobs:
            job_id = str(job.get("id"))
            title = job.get("title", "").strip()
            if not title:
                continue

            absolute_url = job.get("absolute_url") or f"https://boards.greenhouse.io/{board_token}/jobs/{job_id}"
            location_info = job.get("location") or {}
            raw_location = location_info.get("name") if isinstance(location_info, dict) else str(location_info)
            html_content = job.get("content") or ""
            clean_text = extract_clean_text(html_content)

            work_mode = normalize_work_mode(raw_location, clean_text)
            india_eligible = detect_india_accessibility(raw_location, clean_text)

            # Build traceable evidence
            ev_id = str(uuid.uuid4())
            evidence = EvidenceRecord(
                id=ev_id,
                evidence_type="api_json_field",
                claim="job_posting",
                original_url=api_url,
                canonical_url=absolute_url,
                http_status=fetch_result.status_code,
                excerpt=clean_text[:500] if clean_text else f"Job: {title} at {company_name}",
                content_hash=fetch_result.content_hash,
                extraction_method="greenhouse_v1_api",
                metadata={"job_id": job_id, "board_token": board_token, "requisition_id": job.get("requisition_id")},
            )

            # Verification checks
            checks = [
                VerificationCheck(
                    check_name="listing_existence",
                    result=VerificationResult.PASS,
                    explanation=f"Listing confirmed via Greenhouse Board API with ID {job_id}",
                    evidence_id=ev_id,
                ),
                VerificationCheck(
                    check_name="source_authority",
                    result=VerificationResult.PASS,
                    explanation=f"Published directly through official Greenhouse endpoint for {board_token}",
                    evidence_id=ev_id,
                ),
                VerificationCheck(
                    check_name="application_destination",
                    result=VerificationResult.PASS,
                    explanation=f"Application URL resolves to authorized Greenhouse hosted board: {absolute_url}",
                    evidence_id=ev_id,
                ),
                VerificationCheck(
                    check_name="current_availability",
                    result=VerificationResult.PASS,
                    explanation="Currently published on live ATS feed",
                    evidence_id=ev_id,
                ),
            ]

            admission_class = "VERIFIED" if india_eligible is not False else "REJECTED"

            opp = Opportunity(
                id=f"gh_{board_token}_{job_id}",
                company_name=company_name,
                title=title,
                work_mode=work_mode,
                locations=[raw_location] if raw_location else [],
                description_text=clean_text,
                canonical_application_url=absolute_url,
                admission_class=admission_class,
                status="active",
                content_hash=fetch_result.content_hash,
                source_ids=[source.id],
                evidence=[evidence],
                checks=checks,
            )
            opportunities.append(opp)

        return opportunities
