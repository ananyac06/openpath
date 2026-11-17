"""Core Pydantic domain models for OpenPath."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class WorkMode(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNCLEAR = "unclear"


class OpportunityStatus(StrEnum):
    DISCOVERED = "discovered"
    VERIFIED = "verified"
    NEEDS_INVESTIGATION = "needs_investigation"
    COMMUNITY_LEAD = "community_lead"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CLOSED = "closed"


class VerificationResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class MatchResult(StrEnum):
    CONFIRMED_ELIGIBLE = "CONFIRMED_ELIGIBLE"
    CONFIRMED_INELIGIBLE = "CONFIRMED_INELIGIBLE"
    UNCLEAR = "UNCLEAR"
    MORE_INFO_REQUIRED = "MORE_INFO_REQUIRED"


class AuthorityTier(StrEnum):
    OFFICIAL = "official"
    ATS = "ats"
    COMMUNITY = "community"
    AGGREGATOR = "aggregator"
    REGISTRY = "registry"
    UNKNOWN = "unknown"


class CandidateProfile(BaseModel):
    """Structured representation of a candidate's background and preferences."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Default Candidate"
    degree: str | None = None
    academic_year: int | None = None  # e.g., 1, 2, 3, 4
    graduation_year: int | None = None
    discipline: str | None = "Computer Science"
    years_experience: float = 0.0
    skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    specialisations: list[str] = Field(default_factory=list)
    work_modes: list[WorkMode] = Field(
        default_factory=lambda: [WorkMode.REMOTE, WorkMode.HYBRID, WorkMode.ONSITE]
    )
    preferred_cities: list[str] = Field(default_factory=list)
    india_work_authorized: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_db_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "eligibility_json": json.dumps(
                {
                    "degree": self.degree,
                    "academic_year": self.academic_year,
                    "graduation_year": self.graduation_year,
                    "discipline": self.discipline,
                    "years_experience": self.years_experience,
                    "india_work_authorized": self.india_work_authorized,
                }
            ),
            "skills_json": json.dumps(self.skills),
            "languages_json": json.dumps(self.languages),
            "specialisations_json": json.dumps(self.specialisations),
            "preferences_json": json.dumps(
                {
                    "work_modes": [m.value for m in self.work_modes],
                    "preferred_cities": self.preferred_cities,
                }
            ),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> CandidateProfile:
        eligibility = json.loads(row.get("eligibility_json") or "{}")
        preferences = json.loads(row.get("preferences_json") or "{}")
        work_modes = [
            WorkMode(m) for m in preferences.get("work_modes", []) if m in WorkMode._value2member_map_
        ] or [WorkMode.REMOTE, WorkMode.HYBRID, WorkMode.ONSITE]

        return cls(
            id=row["id"],
            name=row["name"],
            degree=eligibility.get("degree"),
            academic_year=eligibility.get("academic_year"),
            graduation_year=eligibility.get("graduation_year"),
            discipline=eligibility.get("discipline", "Computer Science"),
            years_experience=float(eligibility.get("years_experience", 0.0)),
            skills=json.loads(row.get("skills_json") or "[]"),
            languages=json.loads(row.get("languages_json") or "[]"),
            specialisations=json.loads(row.get("specialisations_json") or "[]"),
            work_modes=work_modes,
            preferred_cities=preferences.get("preferred_cities", []),
            india_work_authorized=bool(eligibility.get("india_work_authorized", True)),
        )


class Source(BaseModel):
    """Source registry record."""

    id: str
    connector_id: str
    name: str
    category: str
    base_url: str | None = None
    authority_tier: AuthorityTier = AuthorityTier.UNKNOWN
    access_method: str = "unknown"
    policy_url: str | None = None
    enabled: bool = True
    last_status: str | None = None
    last_checked_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceRecord(BaseModel):
    """Immutable evidence unit supporting an extracted fact or claim."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    opportunity_id: str | None = None
    organization_id: str | None = None
    resource_id: str | None = None
    evidence_type: str  # e.g. 'html_excerpt', 'api_json_field', 'pdf_page'
    claim: str  # e.g. 'title', 'location', 'current_availability', 'stipend'
    original_url: str
    canonical_url: str | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_verified_at: datetime | None = None
    http_status: int | None = None
    excerpt: str | None = None
    document_page: int | None = None
    content_hash: str | None = None
    extraction_method: str = "direct"
    retention_policy: str = "metadata_only"
    metadata: dict[str, Any] = Field(default_factory=dict)


class VerificationCheck(BaseModel):
    """Specific verification gate result for an opportunity or organization."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    opportunity_id: str | None = None
    organization_id: str | None = None
    check_name: str
    result: VerificationResult
    explanation: str
    evidence_id: str | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    checker_version: str = "1.0.0"


class Opportunity(BaseModel):
    """Canonical opportunity record aligned with research database schema."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    organization_id: str | None = None
    company_name: str
    title: str
    normalized_title: str | None = None
    opportunity_type: str | None = None
    employment_type: str | None = None
    work_mode: WorkMode = WorkMode.UNCLEAR
    locations: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    description_text: str | None = None
    compensation_text: str = "Not disclosed"
    compensation_min: float | None = None
    compensation_max: float | None = None
    currency: str | None = None
    deadline: str | None = None
    published_at: str | None = None
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: str = "active"
    admission_class: str = "VERIFIED"
    canonical_application_url: str
    content_hash: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Provenance tracking
    source_ids: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    checks: list[VerificationCheck] = Field(default_factory=list)

    @property
    def location_raw(self) -> str | None:
        return self.locations[0] if self.locations else None

    @property
    def application_url(self) -> str:
        return self.canonical_application_url

    @property
    def compensation_raw(self) -> str:
        return self.compensation_text
