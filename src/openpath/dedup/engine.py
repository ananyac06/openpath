"""Multi-signal opportunity deduplication and cluster manager."""

from __future__ import annotations

import json
import logging
import uuid
from difflib import SequenceMatcher
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from openpath.db.connection import DatabaseManager
from openpath.models.entities import Opportunity

logger = logging.getLogger(__name__)


def normalize_url_for_dedup(url: str) -> str:
    """Strip tracking query parameters (utm_*, ref, source, etc.) for URL normalization."""
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    clean_params = {
        k: v for k, v in query_params.items()
        if not (k.startswith("utm_") or k in ("ref", "source", "gh_src", "lever-source", "tracking"))
    }
    clean_query = urlencode(clean_params, doseq=True)
    # Remove trailing slash
    clean_path = parsed.path.rstrip("/")
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), clean_path, parsed.params, clean_query, ""))


def string_similarity(a: str, b: str) -> float:
    """Calculate SequenceMatcher similarity between two strings."""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


class DuplicateMatch:
    def __init__(self, canonical_id: str, duplicate_id: str, score: float, signals: dict[str, str]) -> None:
        self.canonical_id = canonical_id
        self.duplicate_id = duplicate_id
        self.score = score
        self.signals = signals


class DeduplicationEngine:
    """Clusters identical opportunity records across multiple discovery channels."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def find_duplicate(self, candidate: Opportunity, existing: list[Opportunity]) -> DuplicateMatch | None:
        """Evaluate candidate against a list of existing opportunities for a duplicate match."""
        cand_norm_url = normalize_url_for_dedup(candidate.canonical_application_url)

        for opp in existing:
            if opp.id == candidate.id:
                continue

            signals: dict[str, str] = {}
            score = 0.0

            # Signal 1: Canonical Application URL Match
            opp_norm_url = normalize_url_for_dedup(opp.canonical_application_url)
            if cand_norm_url and opp_norm_url and cand_norm_url == opp_norm_url:
                signals["canonical_url_match"] = cand_norm_url
                score = 1.0
                return DuplicateMatch(opp.id, candidate.id, score, signals)

            # Signal 2: Same company + exact normalized title + same location
            if opp.company_name.lower() == candidate.company_name.lower():
                title_sim = string_similarity(opp.title, candidate.title)
                loc_cand = candidate.location_raw or ""
                loc_opp = opp.location_raw or ""
                loc_sim = string_similarity(loc_cand, loc_opp) if (loc_cand and loc_opp) else 0.5

                if title_sim >= 0.95 and loc_sim >= 0.8:
                    signals["company_match"] = opp.company_name
                    signals["title_similarity"] = f"{title_sim:.2f}"
                    signals["location_similarity"] = f"{loc_sim:.2f}"
                    score = (title_sim * 0.7) + (loc_sim * 0.3)
                    if score >= 0.90:
                        return DuplicateMatch(opp.id, candidate.id, score, signals)

        return None

    def record_cluster(self, match: DuplicateMatch) -> str:
        """Persist duplicate cluster membership in SQLite."""
        cluster_id = str(uuid.uuid4())
        with self.db.transaction() as conn:
            # Check if cluster already exists for canonical_id
            row = conn.execute(
                "SELECT id FROM duplicate_clusters WHERE canonical_opportunity_id = ?;",
                (match.canonical_id,),
            ).fetchone()
            if row:
                cluster_id = row[0]
            else:
                conn.execute(
                    """
                    INSERT INTO duplicate_clusters (id, canonical_opportunity_id, match_signals_json)
                    VALUES (?, ?, ?);
                    """,
                    (cluster_id, match.canonical_id, json.dumps(match.signals)),
                )

            # Add member
            conn.execute(
                """
                INSERT OR REPLACE INTO duplicate_members (cluster_id, opportunity_id, similarity)
                VALUES (?, ?, ?);
                """,
                (cluster_id, match.duplicate_id, match.score),
            )

        return cluster_id
