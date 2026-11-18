"""Reddit technical community opportunity lead connector."""

from __future__ import annotations

import json
import logging
import uuid

from openpath.connectors.base import BaseConnector
from openpath.exceptions import ConnectorError
from openpath.extraction.parser import extract_clean_text
from openpath.models.entities import (
    EvidenceRecord,
    Opportunity,
    Source,
    VerificationCheck,
    VerificationResult,
    WorkMode,
)

logger = logging.getLogger(__name__)


class RedditConnector(BaseConnector):
    """Discovers hiring announcements and leads from developer subreddits."""

    async def fetch_opportunities(self, source: Source) -> list[Opportunity]:
        subreddit = source.metadata.get("subreddit") or "developersIndia"
        query = source.metadata.get("query") or "hiring OR internship OR fresher"
        from urllib.parse import quote_plus

        api_url = f"https://www.reddit.com/r/{subreddit}/search.json?q={quote_plus(query)}&restrict_sr=1&sort=new&limit=10"

        logger.info("Querying Reddit for r/%s: %s", subreddit, api_url)
        fetch_result = await self.http_client.fetch(api_url)
        if fetch_result.status_code != 200:
            logger.warning(
                "Reddit API returned status %d for %s", fetch_result.status_code, api_url
            )
            return []

        try:
            data = json.loads(fetch_result.text)
        except json.JSONDecodeError as err:
            raise ConnectorError(f"Failed to parse Reddit JSON: {err}") from err

        children = data.get("data", {}).get("children", [])
        opportunities: list[Opportunity] = []

        for child in children:
            post = child.get("data", {})
            title = post.get("title", "").strip()
            selftext = post.get("selftext", "")
            permalink = post.get("permalink", "")
            full_url = f"https://www.reddit.com{permalink}" if permalink else api_url
            clean_text = extract_clean_text(selftext)

            ev_id = str(uuid.uuid4())
            evidence = EvidenceRecord(
                id=ev_id,
                evidence_type="reddit_post",
                claim="community_discussion_lead",
                original_url=api_url,
                canonical_url=full_url,
                http_status=fetch_result.status_code,
                excerpt=clean_text[:500] if clean_text else title,
                content_hash=fetch_result.content_hash,
                extraction_method="reddit_public_json",
                retention_policy="metadata_only",
                metadata={"subreddit": subreddit, "author": post.get("author")},
            )

            checks = [
                VerificationCheck(
                    check_name="listing_existence",
                    result=VerificationResult.PASS,
                    explanation=f"Discussion thread confirmed on r/{subreddit}",
                    evidence_id=ev_id,
                ),
                VerificationCheck(
                    check_name="source_authority",
                    result=VerificationResult.UNKNOWN,
                    explanation="Community post on Reddit. Not an official employer endpoint.",
                    evidence_id=ev_id,
                ),
            ]

            import hashlib

            stable_id = f"rd_{hashlib.md5(full_url.encode()).hexdigest()[:12]}"

            opp = Opportunity(
                id=stable_id,
                company_name=f"Community Lead (r/{subreddit})",
                title=title,
                work_mode=WorkMode.UNCLEAR,
                locations=["India / Community Discussion"],
                description_text=clean_text,
                canonical_application_url=full_url,
                admission_class="COMMUNITY LEAD",
                status="active",
                content_hash=fetch_result.content_hash,
                source_ids=[source.id],
                evidence=[evidence],
                checks=checks,
            )
            opportunities.append(opp)

        return opportunities
