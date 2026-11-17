"""Repository layer for structured data access in OpenPath."""

from __future__ import annotations

import json
import logging
from typing import Any

from openpath.db.connection import DatabaseManager
from openpath.models.entities import (
    AuthorityTier,
    CandidateProfile,
    EvidenceRecord,
    Opportunity,
    Source,
    VerificationCheck,
    VerificationResult,
    WorkMode,
)

logger = logging.getLogger(__name__)


class Repository:
    """Encapsulates all database read and write operations."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    # ---------------------------------------------------------
    # Candidate Profiles
    # ---------------------------------------------------------

    def list_profiles(self) -> list[CandidateProfile]:
        """Retrieve all candidate profiles."""
        with self.db.connection() as conn:
            rows = conn.execute("SELECT * FROM candidate_profiles ORDER BY name ASC;").fetchall()
            return [CandidateProfile.from_db_row(dict(r)) for r in rows]

    def get_profile(self, profile_id: str) -> CandidateProfile | None:
        """Retrieve a specific profile by ID."""
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM candidate_profiles WHERE id = ?;", (profile_id,)
            ).fetchone()
            if not row:
                return None
            return CandidateProfile.from_db_row(dict(row))

    def upsert_profile(self, profile: CandidateProfile) -> None:
        """Insert or update a candidate profile."""
        row_data = profile.to_db_row()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO candidate_profiles (
                    id, name, eligibility_json, skills_json, languages_json,
                    specialisations_json, preferences_json, created_at, updated_at
                ) VALUES (
                    :id, :name, :eligibility_json, :skills_json, :languages_json,
                    :specialisations_json, :preferences_json, :created_at, :updated_at
                )
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    eligibility_json = excluded.eligibility_json,
                    skills_json = excluded.skills_json,
                    languages_json = excluded.languages_json,
                    specialisations_json = excluded.specialisations_json,
                    preferences_json = excluded.preferences_json,
                    updated_at = excluded.updated_at;
                """,
                row_data,
            )

    # ---------------------------------------------------------
    # Sources
    # ---------------------------------------------------------

    def list_sources(self, enabled_only: bool = False) -> list[Source]:
        """Retrieve list of sources."""
        query = "SELECT * FROM sources"
        params: list[Any] = []
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY category ASC, name ASC;"

        with self.db.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            results: list[Source] = []
            for r in rows:
                meta = json.loads(r["metadata_json"] or "{}")
                results.append(
                    Source(
                        id=r["id"],
                        connector_id=r["connector_id"],
                        name=r["name"],
                        category=r["category"],
                        base_url=r["base_url"],
                        authority_tier=AuthorityTier(r["authority_tier"])
                        if r["authority_tier"] in AuthorityTier._value2member_map_
                        else AuthorityTier.UNKNOWN,
                        access_method=r["access_method"],
                        policy_url=r["policy_url"],
                        enabled=bool(r["enabled"]),
                        last_status=r["last_status"],
                        last_checked_at=r["last_checked_at"],
                        metadata=meta,
                    )
                )
            return results

    def get_source(self, source_id: str) -> Source | None:
        """Retrieve a specific source by ID."""
        with self.db.connection() as conn:
            row = conn.execute("SELECT * FROM sources WHERE id = ?;", (source_id,)).fetchone()
            if not row:
                return None
            meta = json.loads(row["metadata_json"] or "{}")
            return Source(
                id=row["id"],
                connector_id=row["connector_id"],
                name=row["name"],
                category=row["category"],
                base_url=row["base_url"],
                authority_tier=AuthorityTier(row["authority_tier"])
                if row["authority_tier"] in AuthorityTier._value2member_map_
                else AuthorityTier.UNKNOWN,
                access_method=row["access_method"],
                policy_url=row["policy_url"],
                enabled=bool(row["enabled"]),
                last_status=row["last_status"],
                last_checked_at=row["last_checked_at"],
                metadata=meta,
            )

    def record_source_access(
        self, source_id: str, state: str, detail: str | None = None, run_id: str | None = None
    ) -> None:
        """Record an entry in the source_access_ledger."""
        import uuid

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO source_access_ledger (id, run_id, source_id, state, detail)
                VALUES (?, ?, ?, ?, ?);
                """,
                (str(uuid.uuid4()), run_id, source_id, state, detail),
            )
            conn.execute(
                """
                UPDATE sources SET last_status = ?, last_checked_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                WHERE id = ?;
                """,
                (state, source_id),
            )

    # ---------------------------------------------------------
    # Opportunities & Evidence
    # ---------------------------------------------------------

    def save_opportunity(self, opp: Opportunity) -> None:
        """Save canonical opportunity along with associated sources, evidence, and verification checks."""
        with self.db.transaction() as conn:
            # 0. Ensure organization exists
            org_id = opp.organization_id
            if not org_id and opp.company_name:
                row = conn.execute("SELECT id FROM organisations WHERE canonical_name = ?;", (opp.company_name,)).fetchone()
                if row:
                    org_id = row[0]
                else:
                    import hashlib
                    org_id = f"org_{hashlib.md5(opp.company_name.lower().encode()).hexdigest()[:8]}"
                    conn.execute(
                        "INSERT OR IGNORE INTO organisations (id, canonical_name, verification_status) VALUES (?, ?, 'PASS');",
                        (org_id, opp.company_name),
                    )
            opp.organization_id = org_id

            # 1. Opportunities table
            conn.execute(
                """
                INSERT INTO opportunities (
                    id, organization_id, title, normalized_title, opportunity_type,
                    employment_type, work_mode, locations_json, description_text, skills_json,
                    compensation_text, compensation_min, compensation_max, currency,
                    deadline, published_at, first_seen_at, last_seen_at, status,
                    admission_class, canonical_application_url, content_hash, created_at, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?
                )
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    normalized_title = excluded.normalized_title,
                    opportunity_type = excluded.opportunity_type,
                    employment_type = excluded.employment_type,
                    work_mode = excluded.work_mode,
                    locations_json = excluded.locations_json,
                    description_text = excluded.description_text,
                    skills_json = excluded.skills_json,
                    compensation_text = excluded.compensation_text,
                    compensation_min = excluded.compensation_min,
                    compensation_max = excluded.compensation_max,
                    currency = excluded.currency,
                    deadline = excluded.deadline,
                    published_at = excluded.published_at,
                    last_seen_at = excluded.last_seen_at,
                    status = excluded.status,
                    admission_class = excluded.admission_class,
                    canonical_application_url = excluded.canonical_application_url,
                    content_hash = excluded.content_hash,
                    updated_at = excluded.updated_at;
                """,
                (
                    opp.id,
                    opp.organization_id,
                    opp.title,
                    opp.normalized_title,
                    opp.opportunity_type,
                    opp.employment_type,
                    opp.work_mode.value if opp.work_mode else None,
                    json.dumps(opp.locations),
                    opp.description_text,
                    json.dumps(opp.skills),
                    opp.compensation_text,
                    opp.compensation_min,
                    opp.compensation_max,
                    opp.currency,
                    opp.deadline,
                    opp.published_at,
                    opp.first_seen_at.isoformat(),
                    opp.last_seen_at.isoformat(),
                    opp.status,
                    opp.admission_class,
                    opp.canonical_application_url,
                    opp.content_hash,
                    opp.created_at.isoformat(),
                    opp.updated_at.isoformat(),
                ),
            )

            # 2. Opportunity Sources
            for src_id in opp.source_ids:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO opportunity_sources (opportunity_id, source_id)
                    VALUES (?, ?);
                    """,
                    (opp.id, src_id),
                )

            # 3. Evidence Records
            for ev in opp.evidence:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO evidence_records (
                        id, source_id, organization_id, opportunity_id, resource_id, evidence_type,
                        claim, original_url, canonical_url, retrieved_at, last_verified_at,
                        http_status, excerpt, document_page, content_hash, extraction_method,
                        retention_policy, metadata_json
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?
                    );
                    """,
                    (
                        ev.id,
                        opp.source_ids[0] if opp.source_ids else None,
                        ev.organization_id,
                        opp.id,
                        ev.resource_id,
                        ev.evidence_type,
                        ev.claim,
                        ev.original_url,
                        ev.canonical_url,
                        ev.retrieved_at.isoformat(),
                        ev.last_verified_at.isoformat() if ev.last_verified_at else None,
                        ev.http_status,
                        ev.excerpt,
                        ev.document_page,
                        ev.content_hash,
                        ev.extraction_method,
                        ev.retention_policy,
                        json.dumps(ev.metadata),
                    ),
                )

            # 4. Verification Checks
            for chk in opp.checks:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO verification_checks (
                        id, opportunity_id, organization_id, check_name, result,
                        explanation, evidence_id, checked_at, checker_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        chk.id,
                        opp.id,
                        chk.organization_id,
                        chk.check_name,
                        chk.result.value,
                        chk.explanation,
                        chk.evidence_id,
                        chk.checked_at.isoformat(),
                        chk.checker_version,
                    ),
                )

            # 5. Full text index update
            conn.execute(
                """
                INSERT OR REPLACE INTO opportunity_fts (opportunity_id, title, description_text, skills)
                VALUES (?, ?, ?, ?);
                """,
                (opp.id, opp.title, opp.description_text or "", ""),
            )

    def list_opportunities(
        self,
        status: str | None = None,
        search_query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Opportunity]:
        """List opportunities with optional status/admission_class filter and full-text search."""
        params: list[Any] = []
        where_clauses: list[str] = []

        if status:
            where_clauses.append("(o.admission_class = ? OR o.status = ?)")
            params.extend([status, status])

        if search_query:
            where_clauses.append("o.id IN (SELECT opportunity_id FROM opportunity_fts WHERE opportunity_fts MATCH ?)")
            params.append(search_query)

        query = """
            SELECT o.*, COALESCE(org.canonical_name, 'Unknown Organization') AS company_name
            FROM opportunities o
            LEFT JOIN organisations org ON o.organization_id = org.id
        """
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        query += " ORDER BY o.created_at DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        with self.db.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            opportunities: list[Opportunity] = []
            for r in rows:
                locs = json.loads(r["locations_json"] or "[]")
                skls = json.loads(r["skills_json"] or "[]")
                opportunities.append(
                    Opportunity(
                        id=r["id"],
                        organization_id=r["organization_id"],
                        company_name=r["company_name"],
                        title=r["title"],
                        normalized_title=r["normalized_title"],
                        opportunity_type=r["opportunity_type"],
                        employment_type=r["employment_type"],
                        work_mode=WorkMode(r["work_mode"]) if r["work_mode"] in WorkMode._value2member_map_ else WorkMode.UNCLEAR,
                        locations=locs,
                        skills=skls,
                        description_text=r["description_text"],
                        compensation_text=r["compensation_text"] or "Not disclosed",
                        compensation_min=r["compensation_min"],
                        compensation_max=r["compensation_max"],
                        currency=r["currency"],
                        deadline=r["deadline"],
                        published_at=r["published_at"],
                        status=r["status"],
                        admission_class=r["admission_class"],
                        canonical_application_url=r["canonical_application_url"] or "",
                        content_hash=r["content_hash"],
                    )
                )
            return opportunities

    def get_opportunity(self, opp_id: str) -> Opportunity | None:
        """Fetch complete opportunity details including evidence and verification checks."""
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT o.*, COALESCE(org.canonical_name, 'Unknown Organization') AS company_name
                FROM opportunities o
                LEFT JOIN organisations org ON o.organization_id = org.id
                WHERE o.id = ?;
                """,
                (opp_id,),
            ).fetchone()
            if not row:
                return None

            locs = json.loads(row["locations_json"] or "[]")
            skls = json.loads(row["skills_json"] or "[]")

            # Fetch evidence
            ev_rows = conn.execute(
                "SELECT * FROM evidence_records WHERE opportunity_id = ?;", (opp_id,)
            ).fetchall()
            evidence_list: list[EvidenceRecord] = []
            for er in ev_rows:
                evidence_list.append(
                    EvidenceRecord(
                        id=er["id"],
                        opportunity_id=er["opportunity_id"],
                        organization_id=er["organization_id"],
                        resource_id=er["resource_id"],
                        evidence_type=er["evidence_type"],
                        claim=er["claim"],
                        original_url=er["original_url"],
                        canonical_url=er["canonical_url"],
                        http_status=er["http_status"],
                        excerpt=er["excerpt"],
                        document_page=er["document_page"],
                        content_hash=er["content_hash"],
                        extraction_method=er["extraction_method"],
                        retention_policy=er["retention_policy"],
                        metadata=json.loads(er["metadata_json"] or "{}"),
                    )
                )

            # Fetch verification checks
            chk_rows = conn.execute(
                "SELECT * FROM verification_checks WHERE opportunity_id = ?;", (opp_id,)
            ).fetchall()
            checks_list: list[VerificationCheck] = []
            for cr in chk_rows:
                checks_list.append(
                    VerificationCheck(
                        id=cr["id"],
                        opportunity_id=cr["opportunity_id"],
                        organization_id=cr["organization_id"],
                        check_name=cr["check_name"],
                        result=VerificationResult(cr["result"]),
                        explanation=cr["explanation"],
                        evidence_id=cr["evidence_id"],
                        checker_version=cr["checker_version"],
                    )
                )

            # Fetch sources
            src_rows = conn.execute(
                "SELECT source_id FROM opportunity_sources WHERE opportunity_id = ?;", (opp_id,)
            ).fetchall()
            source_ids = [sr["source_id"] for sr in src_rows]

            return Opportunity(
                id=row["id"],
                organization_id=row["organization_id"],
                company_name=row["company_name"],
                title=row["title"],
                normalized_title=row["normalized_title"],
                opportunity_type=row["opportunity_type"],
                employment_type=row["employment_type"],
                work_mode=WorkMode(row["work_mode"]) if row["work_mode"] in WorkMode._value2member_map_ else WorkMode.UNCLEAR,
                locations=locs,
                skills=skls,
                description_text=row["description_text"],
                compensation_text=row["compensation_text"] or "Not disclosed",
                compensation_min=row["compensation_min"],
                compensation_max=row["compensation_max"],
                currency=row["currency"],
                deadline=row["deadline"],
                published_at=row["published_at"],
                status=row["status"],
                admission_class=row["admission_class"],
                canonical_application_url=row["canonical_application_url"] or "",
                content_hash=row["content_hash"],
                source_ids=source_ids,
                evidence=evidence_list,
                checks=checks_list,
            )

    # ---------------------------------------------------------
    # System Diagnostics & Stats
    # ---------------------------------------------------------

    def get_stats(self) -> dict[str, int]:
        """Return counts of major entities."""
        with self.db.connection() as conn:
            counts = {}
            for table in [
                "candidate_profiles",
                "sources",
                "source_connectors",
                "organisations",
                "opportunities",
                "evidence_records",
                "verification_checks",
                "crawl_runs",
                "crawl_tasks",
                "rejected_records",
            ]:
                try:
                    cnt = conn.execute(f"SELECT count(*) FROM {table};").fetchone()[0]
                    counts[table] = cnt
                except Exception:
                    counts[table] = 0
            return counts
