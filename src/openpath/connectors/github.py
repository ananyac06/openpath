"""GitHub open-source and contributor opportunities connector."""

from __future__ import annotations

import json
import logging
import uuid

from openpath.connectors.base import BaseConnector
from openpath.exceptions import ConnectorError
from openpath.extraction.parser import (
    extract_clean_text,
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


class GitHubConnector(BaseConnector):
    """Discovers open source mentorships, fellowships, and contributor opportunities via GitHub API."""

    async def fetch_opportunities(self, source: Source) -> list[Opportunity]:
        query = (
            source.metadata.get("search_query") or "label:internship label:mentorship state:open"
        )
        from urllib.parse import quote_plus

        api_url = f"https://api.github.com/search/issues?q={quote_plus(query)}&sort=updated&order=desc&per_page=10"

        logger.info("Querying GitHub API: %s", api_url)
        headers = {"Accept": "application/vnd.github.v3+json"}
        token = source.metadata.get("github_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        fetch_result = await self.http_client.fetch(api_url, headers=headers)
        if fetch_result.status_code != 200:
            logger.warning(
                "GitHub API returned status %d for %s", fetch_result.status_code, api_url
            )
            return []

        try:
            data = json.loads(fetch_result.text)
        except json.JSONDecodeError as err:
            raise ConnectorError(f"Failed to parse GitHub JSON: {err}") from err

        items = data.get("items", [])
        opportunities: list[Opportunity] = []

        for item in items:
            title = item.get("title", "").strip()
            html_url = item.get("html_url", "")
            body = item.get("body", "") or ""
            clean_text = extract_clean_text(body)

            repo_url = item.get("repository_url", "")
            repo_name = repo_url.split("/")[-1] if repo_url else "GitHub Project"

            # Derive work mode from the issue's own labels rather than assuming
            # remote; "onsite"/"in-office" labels exist in mentorship programs.
            labels = [str(lbl.get("name", "")).lower() for lbl in item.get("labels", [])]
            label_text = " ".join(labels)
            if any(w in label_text for w in ("onsite", "in-office", "in person")):
                work_mode = WorkMode.ONSITE
            elif any(w in label_text for w in ("remote", "worldwide")):
                work_mode = WorkMode.REMOTE
            else:
                work_mode = WorkMode.UNCLEAR

            ev_id = str(uuid.uuid4())
            evidence = EvidenceRecord(
                id=ev_id,
                evidence_type="github_issue",
                claim="community_opportunity_lead",
                original_url=api_url,
                canonical_url=html_url,
                http_status=fetch_result.status_code,
                excerpt=clean_text[:500] if clean_text else title,
                content_hash=fetch_result.content_hash,
                extraction_method="github_search_api",
                metadata={"issue_number": item.get("number"), "repo": repo_name},
            )

            # Verification check explicitly reflects COMMUNITY LEAD status
            checks = [
                VerificationCheck(
                    check_name="listing_existence",
                    result=VerificationResult.PASS,
                    explanation=f"Listing confirmed via GitHub Search API in repository {repo_name}",
                    evidence_id=ev_id,
                ),
                VerificationCheck(
                    check_name="source_authority",
                    result=VerificationResult.UNKNOWN,
                    explanation="Community lead from GitHub repository. Not yet confirmed against official corporate careers endpoint.",
                    evidence_id=ev_id,
                ),
            ]

            import hashlib

            stable_id = f"ghub_{hashlib.md5(html_url.encode()).hexdigest()[:12]}"

            opp = Opportunity(
                id=stable_id,
                company_name=repo_name,
                title=title,
                work_mode=work_mode,
                locations=[f"Open Source · {repo_name}"],
                description_text=clean_text,
                canonical_application_url=html_url,
                admission_class="COMMUNITY LEAD",
                status="active",
                content_hash=fetch_result.content_hash,
                source_ids=[source.id],
                evidence=[evidence],
                checks=checks,
            )
            opportunities.append(opp)

        return opportunities
