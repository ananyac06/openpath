"""Unit tests for multi-signal deduplication and URL normalization."""

from pathlib import Path

from openpath.db.connection import DatabaseManager
from openpath.db.migrations import apply_migrations
from openpath.db.repository import Repository
from openpath.dedup.engine import DeduplicationEngine, normalize_url_for_dedup
from openpath.models.entities import Opportunity, WorkMode


def test_url_normalization_strips_tracking() -> None:
    raw_url = "https://jobs.lever.co/company/abc-123/?utm_source=linkedin&ref=jobboard&utm_medium=cpc"
    normalized = normalize_url_for_dedup(raw_url)
    assert normalized == "https://jobs.lever.co/company/abc-123"


def test_dedup_exact_url_match(tmp_path: Path) -> None:
    db_mgr = DatabaseManager(tmp_path / "dedup.db")
    with db_mgr.transaction() as conn:
        apply_migrations(conn)

    repo = Repository(db_mgr)
    dedup = DeduplicationEngine(db_mgr)

    opp1 = Opportunity(
        id="opp-original",
        company_name="Acme Tech",
        title="Software Engineer",
        canonical_application_url="https://boards.greenhouse.io/acme/jobs/100",
        work_mode=WorkMode.ONSITE,
        locations=["Bangalore"],
    )

    opp2 = Opportunity(
        id="opp-duplicate",
        company_name="Acme Tech",
        title="Software Engineer",
        canonical_application_url="https://boards.greenhouse.io/acme/jobs/100?utm_source=telegram",
        work_mode=WorkMode.ONSITE,
        locations=["Bangalore"],
    )

    repo.save_opportunity(opp1)
    repo.save_opportunity(opp2)

    match = dedup.find_duplicate(opp2, [opp1])
    assert match is not None
    assert match.canonical_id == "opp-original"
    assert match.score == 1.0

    cluster_id = dedup.record_cluster(match)
    assert cluster_id is not None
