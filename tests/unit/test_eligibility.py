"""Unit tests for non-inferential candidate eligibility evaluation."""

from openpath.eligibility.engine import EligibilityEngine
from openpath.models.entities import (
    CandidateProfile,
    MatchResult,
    Opportunity,
    WorkMode,
)


def test_eligibility_freshers_accepted() -> None:
    engine = EligibilityEngine()
    profile = CandidateProfile(
        name="CSE Student",
        degree="B.Tech",
        academic_year=3,
        years_experience=0.0,
        skills=["Python", "FastAPI"],
    )

    opp = Opportunity(
        id="opp-1",
        company_name="Tech Corp",
        title="Software Engineering Intern",
        work_mode=WorkMode.ONSITE,
        locations=["Bangalore, India"],
        description_text="Looking for 3rd year B.Tech students with Python and FastAPI skills. No prior experience required.",
        canonical_application_url="https://example.com/apply",
        admission_class="VERIFIED",
    )

    report = engine.evaluate(profile, opp)
    assert report.overall_result == MatchResult.CONFIRMED_ELIGIBLE

    dim_map = {d.dimension: d.result for d in report.dimension_evaluations}
    assert dim_map["academic_year"] == MatchResult.CONFIRMED_ELIGIBLE
    assert dim_map["degree"] == MatchResult.CONFIRMED_ELIGIBLE
    assert dim_map["skills"] == MatchResult.CONFIRMED_ELIGIBLE
    assert dim_map["india_accessibility"] == MatchResult.CONFIRMED_ELIGIBLE


def test_eligibility_experience_mismatch_fails() -> None:
    engine = EligibilityEngine()
    profile = CandidateProfile(
        name="Fresher",
        degree="B.Tech",
        academic_year=4,
        years_experience=0.0,
    )

    opp = Opportunity(
        id="opp-2",
        company_name="Enterprise Corp",
        title="Senior Backend Engineer",
        work_mode=WorkMode.ONSITE,
        locations=["Bangalore, India"],
        description_text="Requires 4+ years of experience in distributed systems.",
        canonical_application_url="https://example.com/apply",
        admission_class="VERIFIED",
    )

    report = engine.evaluate(profile, opp)
    assert report.overall_result == MatchResult.CONFIRMED_INELIGIBLE
    dim_map = {d.dimension: d.result for d in report.dimension_evaluations}
    assert dim_map["experience"] == MatchResult.CONFIRMED_INELIGIBLE


def test_eligibility_missing_year_remains_unclear() -> None:
    """Non-negotiable rule: Missing academic-year restriction is NOT proof that every academic year is accepted."""
    engine = EligibilityEngine()
    profile = CandidateProfile(
        name="Student",
        degree="B.Tech",
        academic_year=2,
        years_experience=0.0,
        skills=["Python"],
    )

    opp = Opportunity(
        id="opp-3",
        company_name="Startup",
        title="Developer Intern",
        work_mode=WorkMode.ONSITE,
        locations=["Bangalore, India"],
        description_text="Work on Python backend features. Flexible timings.",
        canonical_application_url="https://example.com/apply",
        admission_class="VERIFIED",
    )

    report = engine.evaluate(profile, opp)
    dim_map = {d.dimension: d.result for d in report.dimension_evaluations}
    # Academic year must be UNCLEAR, not confirmed!
    assert dim_map["academic_year"] == MatchResult.UNCLEAR
    assert report.overall_result == MatchResult.UNCLEAR
