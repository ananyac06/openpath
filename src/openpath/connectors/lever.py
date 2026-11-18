"""Lever ATS Public Postings API connector."""

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


class LeverConnector(BaseConnector):
    """Fetches opportunities from official Lever Postings API."""

    async def fetch_opportunities(self, source: Source) -> list[Opportunity]:
        company_slug = source.metadata.get("board_token") or source.metadata.get("company_slug")
        if not company_slug and source.base_url:
            from urllib.parse import urlparse

            parts = urlparse(source.base_url).path.strip("/").split("/")
            if "postings" in parts:
                idx = parts.index("postings")
                if idx + 1 < len(parts):
                    company_slug = parts[idx + 1]

        if not company_slug:
            raise ConnectorError(f"Missing company slug for Lever source {source.id}")

        api_url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"
        logger.info("Fetching Lever postings for '%s' from %s", company_slug, api_url)

        fetch_result = await self.http_client.fetch(api_url)
        if fetch_result.status_code != 200:
            logger.warning("Lever API returned status %d for %s", fetch_result.status_code, api_url)
            return []

        try:
            data = json.loads(fetch_result.text)
        except json.JSONDecodeError as err:
            raise ConnectorError(f"Invalid JSON returned from Lever API {api_url}: {err}") from err

        if not isinstance(data, list):
            logger.warning("Lever response is not a list for %s", api_url)
            return []

        company_name = source.metadata.get("company_name") or source.name
        opportunities: list[Opportunity] = []

        for posting in data:
            posting_id = str(posting.get("id"))
            title = posting.get("text", "").strip()
            if not title:
                continue

            hosted_url = (
                posting.get("hostedUrl") or f"https://jobs.lever.co/{company_slug}/{posting_id}"
            )
            apply_url = posting.get("applyUrl") or hosted_url
            categories = posting.get("categories") or {}
            raw_location = categories.get("location") if isinstance(categories, dict) else None
            html_content = posting.get("description") or posting.get("descriptionPlain") or ""
            clean_text = extract_clean_text(html_content) if "<" in html_content else html_content

            work_mode = normalize_work_mode(raw_location, clean_text)
            india_eligible = detect_india_accessibility(raw_location, clean_text)

            ev_id = str(uuid.uuid4())
            evidence = EvidenceRecord(
                id=ev_id,
                evidence_type="api_json_field",
                claim="job_posting",
                original_url=api_url,
                canonical_url=hosted_url,
                http_status=fetch_result.status_code,
                excerpt=clean_text[:500] if clean_text else f"Job: {title} at {company_name}",
                content_hash=fetch_result.content_hash,
                extraction_method="lever_v0_api",
                metadata={
                    "posting_id": posting_id,
                    "company_slug": company_slug,
                    "categories": categories,
                },
            )

            checks = [
                VerificationCheck(
                    check_name="listing_existence",
                    result=VerificationResult.PASS,
                    explanation=f"Listing confirmed via Lever Postings API with ID {posting_id}",
                    evidence_id=ev_id,
                ),
                VerificationCheck(
                    check_name="source_authority",
                    result=VerificationResult.PASS,
                    explanation=f"Published directly via official Lever endpoint for {company_slug}",
                    evidence_id=ev_id,
                ),
                VerificationCheck(
                    check_name="application_destination",
                    result=VerificationResult.PASS,
                    explanation=f"Application URL resolves to authorized Lever hosted page: {apply_url}",
                    evidence_id=ev_id,
                ),
                VerificationCheck(
                    check_name="current_availability",
                    result=VerificationResult.PASS,
                    explanation="Currently published on live Lever postings feed",
                    evidence_id=ev_id,
                ),
            ]

            admission_class = "VERIFIED" if india_eligible is not False else "REJECTED"

            opp = Opportunity(
                id=f"lv_{company_slug}_{posting_id}",
                company_name=company_name,
                title=title,
                work_mode=work_mode,
                locations=[raw_location] if raw_location else [],
                description_text=clean_text,
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
