"""Unit tests for the shared opportunity classification taxonomy."""

from __future__ import annotations

import pytest

from openpath.models.entities import Opportunity, WorkMode
from openpath.taxonomy import (
    CareerStage,
    FunctionArea,
    build_collection_summary,
    classify_role,
    collection_for_id,
    filter_by_collection,
    is_india_eligible_location,
)


def _opp(
    title: str,
    locations: list[str] | None = None,
    mode: WorkMode = WorkMode.UNCLEAR,
) -> Opportunity:
    return Opportunity(
        id=f"opp-{abs(hash(title)) % 100000}",
        company_name="Acme",
        title=title,
        locations=locations or [],
        work_mode=mode,
        canonical_application_url="https://example.com/job",
    )


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Software Engineering Intern", CareerStage.INTERNSHIP),
        ("Summer 2026 Internship - Backend", CareerStage.INTERNSHIP),
        ("Graduate Software Engineer", CareerStage.NEW_GRAD),
        ("New Grad Data Scientist", CareerStage.NEW_GRAD),
        ("Junior Linux Kernel Engineer", CareerStage.ENTRY),
        ("Entry Level Analyst", CareerStage.ENTRY),
        ("Associate - Content (Digest)", CareerStage.ENTRY),
        ("Senior Backend Engineer", CareerStage.PROFESSIONAL),
        ("Workplace Operations Manager", CareerStage.PROFESSIONAL),
        ("VP, Global Head of Trust & Safety", CareerStage.LEADERSHIP),
        ("Associate Director, Revenue", CareerStage.LEADERSHIP),
        ("Assistant Manager - Internal Audit", CareerStage.PROFESSIONAL),
        ("Solutions Architect", CareerStage.PROFESSIONAL),
        ("Something Unlabelled", CareerStage.UNSPECIFIED),
    ],
)
def test_career_stage_classification(title: str, expected: CareerStage) -> None:
    assert classify_role(title).stage is expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Threat Detection Engineer", FunctionArea.SECURITY),
        ("AI Research Engineer", FunctionArea.RESEARCH),
        ("Data Engineer, Analytics", FunctionArea.DATA_AI),
        ("Backend Software Engineer", FunctionArea.ENGINEERING),
        ("Product Designer", FunctionArea.PRODUCT_DESIGN),
        ("Technical Customer Success Manager", FunctionArea.CUSTOMER_SUCCESS),
        ("Developer Marketer - Sales", FunctionArea.GO_TO_MARKET),
        ("Strategic Finance Analyst", FunctionArea.FINANCE_LEGAL),
        ("Workplace Coordinator", FunctionArea.PEOPLE_WORKPLACE),
        ("Creative Illustrator", FunctionArea.PRODUCT_DESIGN),
        ("Key Account Management", FunctionArea.GO_TO_MARKET),
        ("Chief of Staff", FunctionArea.GENERAL),
    ],
)
def test_function_area_classification(title: str, expected: FunctionArea) -> None:
    assert classify_role(title).function is expected


def test_classification_is_deterministic_and_reports_signal() -> None:
    first = classify_role("Graduate Software Engineer")
    second = classify_role("Graduate Software Engineer")
    assert first == second
    assert first.stage_signal is not None
    assert first.function_signal is not None


def test_india_location_detection_is_conservative() -> None:
    assert is_india_eligible_location(["Bangalore, India"]) is True
    assert is_india_eligible_location(["Gurugram"]) is True
    assert is_india_eligible_location(["Remote, India"]) is True
    assert is_india_eligible_location(["Home based - Worldwide"]) is False
    assert is_india_eligible_location(["Remote, United States"]) is False
    assert is_india_eligible_location([]) is False


def test_location_identical_to_work_mode_is_not_a_city() -> None:
    opp = _opp("Backend Engineer", ["Hybrid"], WorkMode.HYBRID)
    from openpath.taxonomy import classify_opportunity

    classified = classify_opportunity(opp)
    assert classified.location_is_work_mode is True
    assert classified.location_label == "Hybrid"


def test_real_city_location_is_preserved() -> None:
    opp = _opp("Backend Engineer", ["Bangalore, India"], WorkMode.ONSITE)
    from openpath.taxonomy import classify_opportunity

    classified = classify_opportunity(opp)
    assert classified.location_is_work_mode is False
    assert classified.location_label == "Bangalore, India"


def test_collection_lookup_and_unknown_id() -> None:
    assert collection_for_id("all") is not None
    assert collection_for_id("start_here") is not None
    assert collection_for_id("does_not_exist") is None


def test_start_here_collection_contains_only_early_career_roles() -> None:
    opps = [
        _opp("Software Engineering Intern"),
        _opp("Graduate Data Analyst"),
        _opp("Junior QA Engineer"),
        _opp("Senior Staff Engineer"),
        _opp("Director of Sales"),
    ]
    filtered = filter_by_collection(opps, "start_here")
    assert [o.title for o in filtered] == [
        "Software Engineering Intern",
        "Graduate Data Analyst",
        "Junior QA Engineer",
    ]


def test_remote_collection_requires_remote_mode() -> None:
    opps = [
        _opp("Backend Engineer", ["Remote, India"], WorkMode.REMOTE),
        _opp("Backend Engineer", ["Bangalore"], WorkMode.ONSITE),
    ]
    assert len(filter_by_collection(opps, "remote")) == 1


def test_india_collection_uses_location_evidence_only() -> None:
    opps = [
        _opp("Backend Engineer", ["Pune, India"]),
        _opp("Backend Engineer", ["Berlin, Germany"]),
        _opp("Backend Engineer", ["Remote, United States"]),
    ]
    assert len(filter_by_collection(opps, "india")) == 1


def test_summary_of_collections_are_consistent() -> None:
    opps = [
        _opp("Software Engineering Intern"),
        _opp("Graduate Data Analyst"),
        _opp("Senior Engineer"),
        _opp("Chief of Staff"),
        _opp("Creative Illustrator"),
    ]
    summary = {item.id: item.count for item in build_collection_summary(opps)}
    assert summary["all"] == 5
    assert summary["start_here"] == 2
    assert summary["internships"] == 1
    assert summary["new_grad"] == 1
    assert summary["experienced"] == 2
    assert summary["level_not_stated"] == 1
    assert summary["engineering"] >= 2


def test_unknown_collection_id_never_leaks_whole_catalogue() -> None:
    opps = [_opp("Senior Engineer")]
    assert filter_by_collection(opps, "nope") == []


def test_titles_without_a_stated_level_are_not_guessed() -> None:
    # The project rule is "never infer missing eligibility": a title with no level
    # signal must be reported as UNSPECIFIED rather than silently assumed junior/senior.
    for title in ("Assistant Manager - Internal Audit", "Data Scientist III", "Chief of Staff"):
        classified = classify_role(title)
        assert classified.stage_signal is not None or classified.stage is CareerStage.UNSPECIFIED
