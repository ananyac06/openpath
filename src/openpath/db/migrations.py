"""Database schema migrations engine for OpenPath."""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime

from openpath.exceptions import MigrationError

logger = logging.getLogger(__name__)

MIGRATION_1_SQL = """
-- Core migration metadata table
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- Candidate profiles
CREATE TABLE IF NOT EXISTS candidate_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    eligibility_json TEXT NOT NULL DEFAULT '{}',
    skills_json TEXT NOT NULL DEFAULT '[]',
    languages_json TEXT NOT NULL DEFAULT '[]',
    specialisations_json TEXT NOT NULL DEFAULT '[]',
    preferences_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Source connectors
CREATE TABLE IF NOT EXISTS source_connectors (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    version TEXT NOT NULL,
    config_schema_json TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1))
);

-- Sources
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    connector_id TEXT NOT NULL REFERENCES source_connectors(id),
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    base_url TEXT,
    authority_tier TEXT NOT NULL DEFAULT 'unknown'
        CHECK (authority_tier IN ('official', 'ats', 'community', 'aggregator', 'registry', 'unknown')),
    access_method TEXT NOT NULL DEFAULT 'unknown',
    policy_url TEXT,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    last_status TEXT,
    last_checked_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Organisations
CREATE TABLE IF NOT EXISTS organisations (
    id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    legal_name TEXT,
    country TEXT,
    website_url TEXT,
    registry_id TEXT,
    registry_source TEXT,
    registry_jurisdiction TEXT,
    verification_status TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('PASS', 'FAIL', 'UNKNOWN')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Domains
CREATE TABLE IF NOT EXISTS domains (
    id TEXT PRIMARY KEY,
    hostname TEXT NOT NULL UNIQUE,
    registrable_domain TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Organisation Domain mappings
CREATE TABLE IF NOT EXISTS organization_domains (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    domain_id TEXT NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    relationship TEXT NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    evidence_id TEXT,
    UNIQUE (organization_id, domain_id, relationship)
);

-- ATS Boards
CREATE TABLE IF NOT EXISTS ats_boards (
    id TEXT PRIMARY KEY,
    organization_id TEXT REFERENCES organisations(id) ON DELETE SET NULL,
    provider TEXT NOT NULL,
    board_token TEXT NOT NULL,
    base_url TEXT NOT NULL,
    discovered_from_url TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    first_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (provider, board_token)
);

-- Crawl Runs
CREATE TABLE IF NOT EXISTS crawl_runs (
    id TEXT PRIMARY KEY,
    run_type TEXT NOT NULL CHECK (run_type IN ('full', 'incremental')),
    profile_id TEXT REFERENCES candidate_profiles(id) ON DELETE SET NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    finished_at TEXT,
    config_json TEXT NOT NULL DEFAULT '{}',
    coverage_json TEXT NOT NULL DEFAULT '{}',
    error TEXT
);

-- Crawl Tasks
CREATE TABLE IF NOT EXISTS crawl_tasks (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES crawl_runs(id) ON DELETE CASCADE,
    source_id TEXT REFERENCES sources(id) ON DELETE SET NULL,
    parent_task_id TEXT REFERENCES crawl_tasks(id) ON DELETE SET NULL,
    url TEXT NOT NULL,
    canonical_url TEXT,
    task_type TEXT NOT NULL,
    depth INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'queued'
        CHECK (state IN ('discovered', 'queued', 'fetched', 'parsed', 'skipped',
                         'blocked', 'failed', 'retry_pending')),
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Fetched Resources
CREATE TABLE IF NOT EXISTS fetched_resources (
    id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES crawl_runs(id) ON DELETE SET NULL,
    task_id TEXT REFERENCES crawl_tasks(id) ON DELETE SET NULL,
    source_id TEXT REFERENCES sources(id) ON DELETE SET NULL,
    url TEXT NOT NULL,
    canonical_url TEXT,
    http_status INTEGER,
    content_type TEXT,
    content_hash TEXT,
    byte_size INTEGER,
    headers_json TEXT NOT NULL DEFAULT '{}',
    fetched_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Page Snapshots
CREATE TABLE IF NOT EXISTS page_snapshots (
    id TEXT PRIMARY KEY,
    resource_id TEXT NOT NULL REFERENCES fetched_resources(id) ON DELETE CASCADE,
    storage_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Documents
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    resource_id TEXT NOT NULL REFERENCES fetched_resources(id) ON DELETE CASCADE,
    document_type TEXT NOT NULL,
    extracted_text TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    page_count INTEGER,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Opportunities
CREATE TABLE IF NOT EXISTS opportunities (
    id TEXT PRIMARY KEY,
    organization_id TEXT REFERENCES organisations(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    normalized_title TEXT,
    opportunity_type TEXT,
    employment_type TEXT,
    work_mode TEXT,
    locations_json TEXT NOT NULL DEFAULT '[]',
    description_text TEXT,
    skills_json TEXT NOT NULL DEFAULT '[]',
    compensation_text TEXT,
    compensation_min REAL,
    compensation_max REAL,
    currency TEXT,
    deadline TEXT,
    published_at TEXT,
    first_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    status TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'modified', 'active', 'deadline_approaching', 'expired',
                          'closed', 'withdrawn', 'inaccessible', 'unable_to_reverify')),
    admission_class TEXT NOT NULL DEFAULT 'NEEDS INVESTIGATION'
        CHECK (admission_class IN ('VERIFIED', 'NEEDS INVESTIGATION', 'COMMUNITY LEAD', 'REJECTED')),
    canonical_application_url TEXT,
    content_hash TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Opportunity Sources
CREATE TABLE IF NOT EXISTS opportunity_sources (
    opportunity_id TEXT NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    first_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (opportunity_id, source_id)
);

-- Application Destinations
CREATE TABLE IF NOT EXISTS application_destinations (
    id TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    destination_url TEXT NOT NULL,
    destination_type TEXT NOT NULL,
    matches_position INTEGER,
    verified_at TEXT
);

-- Evidence Records
CREATE TABLE IF NOT EXISTS evidence_records (
    id TEXT PRIMARY KEY,
    source_id TEXT REFERENCES sources(id) ON DELETE SET NULL,
    organization_id TEXT REFERENCES organisations(id) ON DELETE SET NULL,
    opportunity_id TEXT REFERENCES opportunities(id) ON DELETE SET NULL,
    resource_id TEXT REFERENCES fetched_resources(id) ON DELETE SET NULL,
    evidence_type TEXT NOT NULL,
    claim TEXT NOT NULL,
    original_url TEXT NOT NULL,
    canonical_url TEXT,
    retrieved_at TEXT NOT NULL,
    last_verified_at TEXT,
    http_status INTEGER,
    excerpt TEXT,
    document_page INTEGER,
    content_hash TEXT,
    extraction_method TEXT NOT NULL,
    retention_policy TEXT NOT NULL DEFAULT 'metadata_only',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Verification Checks
CREATE TABLE IF NOT EXISTS verification_checks (
    id TEXT PRIMARY KEY,
    opportunity_id TEXT REFERENCES opportunities(id) ON DELETE CASCADE,
    organization_id TEXT REFERENCES organisations(id) ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('PASS', 'FAIL', 'UNKNOWN')),
    explanation TEXT NOT NULL,
    evidence_id TEXT,
    checked_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    checker_version TEXT NOT NULL
);

-- Eligibility Facts
CREATE TABLE IF NOT EXISTS eligibility_facts (
    id TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    dimension TEXT NOT NULL
        CHECK (dimension IN ('degree', 'academic_year', 'discipline', 'experience',
                             'skills', 'location', 'work_authorisation', 'india_accessibility')),
    raw_value TEXT,
    normalized_value TEXT,
    requirement_type TEXT NOT NULL DEFAULT 'unknown'
        CHECK (requirement_type IN ('required', 'preferred', 'excluded', 'unknown')),
    evidence_id TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Candidate Match Evaluations
CREATE TABLE IF NOT EXISTS candidate_match_evaluations (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES candidate_profiles(id) ON DELETE CASCADE,
    opportunity_id TEXT NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    dimension TEXT NOT NULL,
    result TEXT NOT NULL
        CHECK (result IN ('CONFIRMED_ELIGIBLE', 'CONFIRMED_INELIGIBLE', 'UNCLEAR', 'MORE_INFO_REQUIRED')),
    explanation TEXT NOT NULL,
    evidence_id TEXT,
    evaluated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    evaluator_version TEXT NOT NULL
);

-- Duplicate Clusters
CREATE TABLE IF NOT EXISTS duplicate_clusters (
    id TEXT PRIMARY KEY,
    canonical_opportunity_id TEXT NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    match_signals_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Duplicate Members
CREATE TABLE IF NOT EXISTS duplicate_members (
    cluster_id TEXT NOT NULL REFERENCES duplicate_clusters(id) ON DELETE CASCADE,
    opportunity_id TEXT NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    similarity REAL,
    PRIMARY KEY (cluster_id, opportunity_id)
);

-- Opportunity Status History
CREATE TABLE IF NOT EXISTS opportunity_status_history (
    id TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    reason TEXT,
    evidence_id TEXT,
    observed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Rejected Records
CREATE TABLE IF NOT EXISTS rejected_records (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    source_id TEXT REFERENCES sources(id) ON DELETE SET NULL,
    reason TEXT NOT NULL,
    details TEXT,
    first_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_checked_at TEXT
);

-- Request Logs
CREATE TABLE IF NOT EXISTS request_logs (
    id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES crawl_runs(id) ON DELETE SET NULL,
    source_id TEXT REFERENCES sources(id) ON DELETE SET NULL,
    url TEXT NOT NULL,
    method TEXT NOT NULL,
    status_code INTEGER,
    duration_ms INTEGER,
    bytes INTEGER,
    error TEXT,
    requested_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Source Access Ledger
CREATE TABLE IF NOT EXISTS source_access_ledger (
    id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES crawl_runs(id) ON DELETE SET NULL,
    source_id TEXT REFERENCES sources(id) ON DELETE SET NULL,
    state TEXT NOT NULL
        CHECK (state IN ('attempted', 'success', 'credential_required', 'policy_blocked',
                         'failed', 'paused')),
    detail TEXT,
    observed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Full Text Search Table (FTS5)
CREATE VIRTUAL TABLE IF NOT EXISTS opportunity_fts USING fts5(
    opportunity_id UNINDEXED,
    title,
    description_text,
    skills
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_opportunities_status ON opportunities(status);
CREATE INDEX IF NOT EXISTS idx_opportunities_org ON opportunities(organization_id);
CREATE INDEX IF NOT EXISTS idx_crawl_tasks_run_state ON crawl_tasks(run_id, state);
CREATE INDEX IF NOT EXISTS idx_evidence_records_opp ON evidence_records(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_verification_checks_opp ON verification_checks(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_eligibility_facts_opp ON eligibility_facts(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_candidate_match_opp ON candidate_match_evaluations(profile_id, opportunity_id);
"""

MIGRATION_2_SQL = """
-- Seed initial source connectors
INSERT OR IGNORE INTO source_connectors (id, kind, version, config_schema_json, enabled) VALUES
    ('ats.greenhouse', 'greenhouse', '1', '{}', 1),
    ('ats.lever', 'lever', '1', '{}', 1),
    ('ats.ashby', 'ashby', '1', '{}', 1);

-- Seed initial authoritative sources
INSERT OR IGNORE INTO sources (id, connector_id, name, category, base_url, authority_tier, access_method, policy_url, enabled, metadata_json) VALUES
    ('ats.greenhouse.groww', 'ats.greenhouse', 'Groww', 'ats',
     'https://boards-api.greenhouse.io/v1/boards/groww/jobs?content=true',
     'ats', 'public_api', 'https://docs.greenhouse.io/job-board.html', 1,
     '{"board_token": "groww", "company_name": "Groww", "website_url": "https://groww.in", "region": "India"}'),

    ('ats.greenhouse.slice', 'ats.greenhouse', 'Slice', 'ats',
     'https://boards-api.greenhouse.io/v1/boards/slice/jobs?content=true',
     'ats', 'public_api', 'https://docs.greenhouse.io/job-board.html', 1,
     '{"board_token": "slice", "company_name": "Slice", "website_url": "https://www.sliceit.com", "region": "India"}'),

    ('ats.greenhouse.gitlab', 'ats.greenhouse', 'GitLab', 'ats',
     'https://boards-api.greenhouse.io/v1/boards/gitlab/jobs?content=true',
     'ats', 'public_api', 'https://docs.greenhouse.io/job-board.html', 1,
     '{"board_token": "gitlab", "company_name": "GitLab", "website_url": "https://about.gitlab.com", "region": "global"}'),

    ('ats.lever.meesho', 'ats.lever', 'Meesho', 'ats',
     'https://api.lever.co/v0/postings/meesho?mode=json',
     'ats', 'public_api', 'https://github.com/lever/postings-api', 1,
     '{"board_token": "meesho", "company_name": "Meesho", "website_url": "https://www.meesho.io", "region": "India"}'),

    ('ats.lever.cred', 'ats.lever', 'CRED', 'ats',
     'https://api.lever.co/v0/postings/cred?mode=json',
     'ats', 'public_api', 'https://github.com/lever/postings-api', 1,
     '{"board_token": "cred", "company_name": "CRED", "website_url": "https://www.cred.club", "region": "India"}'),

    ('ats.ashby.atlan', 'ats.ashby', 'Atlan', 'ats',
     'https://api.ashbyhq.com/posting-api/job-board/atlan',
     'ats', 'public_api', 'https://developers.ashbyhq.com/docs/public-job-posting-api', 1,
     '{"board_token": "atlan", "company_name": "Atlan", "website_url": "https://atlan.com", "region": "India"}'),

    ('ats.ashby.posthog', 'ats.ashby', 'PostHog', 'ats',
     'https://api.ashbyhq.com/posting-api/job-board/posthog',
     'ats', 'public_api', 'https://developers.ashbyhq.com/docs/public-job-posting-api', 1,
     '{"board_token": "posthog", "company_name": "PostHog", "website_url": "https://posthog.com", "region": "global"}');
"""

MIGRATION_3_SQL = """
-- Migration 3: Seed authoritative global tech giants, S&P 500, and developer platforms
INSERT OR IGNORE INTO organisations (id, canonical_name, website_url, verification_status) VALUES
    ('org_canonical', 'Canonical', 'https://canonical.com', 'PASS'),
    ('org_cloudflare', 'Cloudflare', 'https://cloudflare.com', 'PASS'),
    ('org_mongodb', 'MongoDB', 'https://mongodb.com', 'PASS'),
    ('org_elastic', 'Elastic', 'https://elastic.co', 'PASS'),
    ('org_mozilla', 'Mozilla', 'https://mozilla.org', 'PASS'),
    ('org_supabase', 'Supabase', 'https://supabase.com', 'PASS');

INSERT OR IGNORE INTO sources (id, connector_id, name, category, base_url, authority_tier, access_method, policy_url, enabled, metadata_json) VALUES
    ('ats.greenhouse.canonical', 'ats.greenhouse', 'Canonical', 'ats',
     'https://boards-api.greenhouse.io/v1/boards/canonical/jobs?content=true',
     'ats', 'public_api', 'https://docs.greenhouse.io/job-board.html', 1,
     '{"board_token": "canonical", "company_name": "Canonical", "website_url": "https://canonical.com", "ticker": "Ubuntu / Linux Leader", "region": "global"}'),

    ('ats.greenhouse.cloudflare', 'ats.greenhouse', 'Cloudflare', 'ats',
     'https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs?content=true',
     'ats', 'public_api', 'https://docs.greenhouse.io/job-board.html', 1,
     '{"board_token": "cloudflare", "company_name": "Cloudflare", "website_url": "https://cloudflare.com", "ticker": "NYSE: NET • S&P 500", "region": "global"}'),

    ('ats.greenhouse.mongodb', 'ats.greenhouse', 'MongoDB', 'ats',
     'https://boards-api.greenhouse.io/v1/boards/mongodb/jobs?content=true',
     'ats', 'public_api', 'https://docs.greenhouse.io/job-board.html', 1,
     '{"board_token": "mongodb", "company_name": "MongoDB", "website_url": "https://mongodb.com", "ticker": "NASDAQ: MDB", "region": "global"}'),

    ('ats.greenhouse.elastic', 'ats.greenhouse', 'Elastic', 'ats',
     'https://boards-api.greenhouse.io/v1/boards/elastic/jobs?content=true',
     'ats', 'public_api', 'https://docs.greenhouse.io/job-board.html', 1,
     '{"board_token": "elastic", "company_name": "Elastic", "website_url": "https://elastic.co", "ticker": "NYSE: ESTC", "region": "global"}'),

    ('ats.greenhouse.mozilla', 'ats.greenhouse', 'Mozilla', 'ats',
     'https://boards-api.greenhouse.io/v1/boards/mozilla/jobs?content=true',
     'ats', 'public_api', 'https://docs.greenhouse.io/job-board.html', 1,
     '{"board_token": "mozilla", "company_name": "Mozilla", "website_url": "https://mozilla.org", "ticker": "Open Source Foundation", "region": "global"}'),

    ('ats.ashby.supabase', 'ats.ashby', 'Supabase', 'ats',
     'https://api.ashbyhq.com/posting-api/job-board/supabase',
     'ats', 'public_api', 'https://developers.ashbyhq.com/docs/public-job-posting-api', 1,
     '{"board_token": "supabase", "company_name": "Supabase", "website_url": "https://supabase.com", "ticker": "Y-Combinator Tech Unicorn", "region": "global"}');
"""


def _build_migration_4_sql() -> str:
    """Generate SQL for Migration 4: add category column and seed 1,100+ verified organizations."""
    from openpath.data.verified_directory import VERIFIED_ORGANIZATIONS

    def esc(val: str | None) -> str:
        if val is None:
            return "NULL"
        return "'" + str(val).replace("'", "''") + "'"

    lines = [
        "-- Migration 4: Schema expansion and authoritative verified organizations directory",
        "ALTER TABLE organisations ADD COLUMN category TEXT;",
        "CREATE INDEX IF NOT EXISTS idx_organisations_category ON organisations(category);",
        "CREATE INDEX IF NOT EXISTS idx_organisations_verification ON organisations(verification_status);",
        "-- Enrich existing seeded organizations",
        "UPDATE organisations SET legal_name = 'Cloudflare, Inc.', country = 'United States', category = 'us_sp500', registry_id = 'NYSE: NET • S&P 500', registry_source = 'SEC EDGAR / NYSE', registry_jurisdiction = 'US-DE' WHERE canonical_name = 'Cloudflare';",
        "UPDATE organisations SET legal_name = 'MongoDB, Inc.', country = 'United States', category = 'us_sp500', registry_id = 'NASDAQ: MDB', registry_source = 'SEC EDGAR / NASDAQ', registry_jurisdiction = 'US-DE' WHERE canonical_name = 'MongoDB';",
        "UPDATE organisations SET legal_name = 'Elastic N.V.', country = 'United States', category = 'us_sp500', registry_id = 'NYSE: ESTC', registry_source = 'SEC EDGAR / NYSE', registry_jurisdiction = 'US-DE' WHERE canonical_name = 'Elastic';",
        "UPDATE organisations SET legal_name = 'Canonical Group Limited', country = 'United Kingdom', category = 'open_source', registry_id = 'UK Companies House: 06870835', registry_source = 'UK Companies House', registry_jurisdiction = 'GB' WHERE canonical_name = 'Canonical';",
        "UPDATE organisations SET legal_name = 'GitLab Inc.', country = 'United States', category = 'us_sp500', registry_id = 'NASDAQ: GTLB', registry_source = 'SEC EDGAR / NASDAQ', registry_jurisdiction = 'US-DE' WHERE canonical_name = 'GitLab';",
        "UPDATE organisations SET legal_name = 'Mozilla Corporation / Mozilla Foundation', country = 'United States', category = 'open_source', registry_id = 'IRS 501(c)(3) Nonprofit', registry_source = 'IRS / US Nonprofit', registry_jurisdiction = 'US-CA' WHERE canonical_name = 'Mozilla';",
        "UPDATE organisations SET legal_name = 'Supabase Inc.', country = 'United States', category = 'tech_unicorn', registry_id = 'YC W20 / Tech Unicorn', registry_source = 'Y-Combinator / US Registry', registry_jurisdiction = 'US-DE' WHERE canonical_name = 'Supabase';",
        "UPDATE organisations SET legal_name = 'Fashnear Technologies Private Limited', country = 'India', category = 'tech_unicorn', website_url = 'https://meesho.io', registry_id = 'MCA: U74900KA2015PTC082263 / E-Commerce Unicorn', registry_source = 'MCA India', registry_jurisdiction = 'IN-KA' WHERE canonical_name = 'Meesho';",
        "UPDATE organisations SET legal_name = 'Nextbillion Technology Private Limited', country = 'India', category = 'indian_listed', website_url = 'https://groww.in', registry_id = 'MCA: U65990KA2016PTC092870 / Wealthtech Unicorn', registry_source = 'MCA India', registry_jurisdiction = 'IN-KA' WHERE canonical_name = 'Groww';",
        "UPDATE organisations SET legal_name = 'Dreamplug Technologies Private Limited', country = 'India', category = 'tech_unicorn', website_url = 'https://cred.club', registry_id = 'MCA: U74999KA2018PTC109559 / Fintech Unicorn', registry_source = 'MCA India', registry_jurisdiction = 'IN-KA' WHERE canonical_name = 'CRED';",
        "UPDATE organisations SET legal_name = 'PostHog, Inc.', country = 'United States', category = 'tech_unicorn', website_url = 'https://posthog.com', registry_id = 'YC W20 / Open Source Unicorn', registry_source = 'Y-Combinator / US Registry', registry_jurisdiction = 'US-DE' WHERE canonical_name = 'PostHog';",
    ]

    vals = [
        f"({esc(o['id'])}, {esc(o['canonical_name'])}, {esc(o['legal_name'])}, {esc(o['country'])}, {esc(o['category'])}, {esc(o['website_url'])}, {esc(o['registry_id'])}, {esc(o['registry_source'])}, {esc(o['registry_jurisdiction'])}, {esc(o['verification_status'])})"
        for o in VERIFIED_ORGANIZATIONS
    ]
    lines.append(
        "INSERT OR IGNORE INTO organisations (id, canonical_name, legal_name, country, category, website_url, registry_id, registry_source, registry_jurisdiction, verification_status) VALUES\n"
        + ",\n".join(vals)
        + ";"
    )

    return "\n".join(lines)


MIGRATION_4_SQL = _build_migration_4_sql()

MIGRATIONS: list[tuple[int, str]] = [
    (1, MIGRATION_1_SQL),
    (2, MIGRATION_2_SQL),
    (3, MIGRATION_3_SQL),
    (4, MIGRATION_4_SQL),
]


def get_applied_migrations(conn: sqlite3.Connection) -> set[int]:
    """Retrieve set of already applied migration version numbers."""
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations';"
        )
        if not cur.fetchone():
            return set()
        rows = conn.execute("SELECT version FROM schema_migrations;").fetchall()
        return {int(row[0]) for row in rows}
    except sqlite3.Error as err:
        raise MigrationError(f"Failed to check applied migrations: {err}") from err


def apply_migrations(conn: sqlite3.Connection) -> list[int]:
    """Apply any pending schema migrations in an atomic transaction."""
    applied = get_applied_migrations(conn)
    newly_applied: list[int] = []

    for version, sql in MIGRATIONS:
        if version not in applied:
            logger.info("Applying migration version %d...", version)
            try:
                conn.executescript(sql)
                now_str = datetime.now(UTC).isoformat()
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?);",
                    (version, now_str),
                )
                newly_applied.append(version)
            except sqlite3.Error as err:
                raise MigrationError(
                    f"Migration {version} failed: {err}",
                ) from err

    return newly_applied
