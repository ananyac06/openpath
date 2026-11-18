"""Unit tests for repository data access layer."""

from pathlib import Path

from openpath.db.connection import DatabaseManager
from openpath.db.migrations import apply_migrations
from openpath.db.repository import Repository
from openpath.models.entities import (
    CandidateProfile,
    EvidenceRecord,
    Opportunity,
    VerificationCheck,
    VerificationResult,
    WorkMode,
)


def test_repository_candidate_profiles(tmp_path: Path) -> None:
    db_mgr = DatabaseManager(tmp_path / "repo.db")
    with db_mgr.transaction() as conn:
        apply_migrations(conn)
    repo = Repository(db_mgr)

    profile = CandidateProfile(
        name="CSE Student",
        degree="B.Tech",
        academic_year=3,
        skills=["Python", "FastAPI"],
    )
    repo.upsert_profile(profile)

    profiles = repo.list_profiles()
    assert len(profiles) == 1
    assert profiles[0].name == "CSE Student"
    assert profiles[0].degree == "B.Tech"
    assert profiles[0].academic_year == 3
    assert "Python" in profiles[0].skills


def test_repository_save_and_retrieve_opportunity(tmp_path: Path) -> None:
    db_mgr = DatabaseManager(tmp_path / "repo.db")
    with db_mgr.transaction() as conn:
        apply_migrations(conn)
    repo = Repository(db_mgr)

    opp = Opportunity(
        id="test-opp-1",
        company_name="Test FinTech",
        title="Software Engineer - Backend",
        locations=["Bangalore, India"],
        work_mode=WorkMode.ONSITE,
        description_text="Building high performance distributed trading systems in Python and Go.",
        compensation_text="₹18,00,000 / year",
        canonical_application_url="https://careers.testfintech.in/jobs/1",
        admission_class="VERIFIED",
        status="active",
        source_ids=["ats.greenhouse.groww"],
        evidence=[
            EvidenceRecord(
                id="ev-1",
                opportunity_id="test-opp-1",
                evidence_type="api_json_field",
                claim="job_posting",
                original_url="https://boards-api.greenhouse.io/v1/boards/groww/jobs/1",
                excerpt="Building high performance distributed trading systems",
                content_hash="abc123hash",
                extraction_method="greenhouse_v1_api",
            )
        ],
        checks=[
            VerificationCheck(
                id="chk-1",
                opportunity_id="test-opp-1",
                check_name="listing_existence",
                result=VerificationResult.PASS,
                explanation="Confirmed via live ATS endpoint",
            )
        ],
    )

    repo.save_opportunity(opp)

    # List
    listed = repo.list_opportunities(status="VERIFIED")
    assert len(listed) == 1
    assert listed[0].id == "test-opp-1"
    assert listed[0].title == "Software Engineer - Backend"

    # Full retrieval with evidence & checks
    retrieved = repo.get_opportunity("test-opp-1")
    assert retrieved is not None
    assert len(retrieved.evidence) == 1
    assert retrieved.evidence[0].claim == "job_posting"
    assert len(retrieved.checks) == 1
    assert retrieved.checks[0].check_name == "listing_existence"

    # Full text search test
    search_hits = repo.list_opportunities(search_query="distributed trading")
    assert len(search_hits) == 1
    assert search_hits[0].id == "test-opp-1"

    no_hits = repo.list_opportunities(search_query="nonexistentkeyword")
    assert len(no_hits) == 0


def test_repository_verified_organisations_directory(tmp_path: Path) -> None:
    db_mgr = DatabaseManager(tmp_path / "repo.db")
    with db_mgr.transaction() as conn:
        apply_migrations(conn)
    repo = Repository(db_mgr)

    # 1. Total verified organizations count is at least 1,000
    total_count = repo.get_organisation_count()
    assert total_count >= 1000

    # 2. List organizations returns complete metadata
    all_orgs = repo.list_organisations(limit=50)
    assert len(all_orgs) == 50
    first = all_orgs[0]
    assert "canonical_name" in first
    assert "legal_name" in first
    assert "registry_id" in first
    assert "verification_status" in first
    assert first["verification_status"] == "PASS"

    # 3. Filter by category
    sp500 = repo.list_organisations(category="us_sp500", limit=100)
    assert len(sp500) > 0
    assert all(o["category"] == "us_sp500" for o in sp500)

    indian_listed = repo.list_organisations(category="indian_listed", limit=100)
    assert len(indian_listed) > 0
    assert all(o["category"] == "indian_listed" for o in indian_listed)

    # 4. Search query matching
    search_nvda = repo.list_organisations(search_query="Nvidia")
    assert len(search_nvda) >= 1
    assert any("Nvidia" in o["canonical_name"] for o in search_nvda)

    search_tcs = repo.list_organisations(search_query="Tata Consultancy")
    assert len(search_tcs) >= 1
    assert any("Tata Consultancy" in o["canonical_name"] for o in search_tcs)
