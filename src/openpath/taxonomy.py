"""Shared opportunity classification taxonomy.

OpenPath shows opportunities to a human who may be anywhere on the beginner-to-pro
spectrum, so every listing needs a *stated* place in two dimensions:

1. **Career stage** - internship, new grad, entry level, professional, leadership.
   A title that matches no signal is reported as ``UNSPECIFIED``. Nothing is inferred:
   "Senior Advocate Manager" is not claimed to be junior just because it is unknown.
2. **Function area** - engineering, data & AI, security, product & design, customer
   success, go-to-market, finance & legal, people & workplace, research.

Both dimensions are derived only from the listing title text that the source
published. When a signal is missing the code reports the missing signal instead of
guessing, which keeps the eligibility rules in
:mod:`openpath.eligibility` authoritative for candidate decisions.

Collections are small curated slices ("Start Here", "Internships", "Remote",
"India-eligible") built on top of the two dimensions so the TUI, the local web
viewer and the CLI all group and filter listings identically.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from openpath.models.entities import Opportunity, WorkMode

# ---------------------------------------------------------------------------
# Dimension 1: career stage
# ---------------------------------------------------------------------------


class CareerStage(StrEnum):
    """Where a role sits on the beginner-to-pro spectrum, as stated in its title."""

    INTERNSHIP = "internship"
    NEW_GRAD = "new_grad"
    ENTRY = "entry"
    PROFESSIONAL = "professional"
    LEADERSHIP = "leadership"
    UNSPECIFIED = "unspecified"


_INTERNSHIP_RE = re.compile(
    r"\b(intern(ship)?|apprentice(ship)?|trainee|co-?op|student researcher)\b", re.IGNORECASE
)
_NEW_GRAD_RE = re.compile(
    r"\b(new grad|newly graduated|university grad|graduate|grad programme|grad program)\b",
    re.IGNORECASE,
)
_LEADERSHIP_RE = re.compile(
    r"\b(vice president|director|\bhead\b|chief|\bvp\b|leader of)\b", re.IGNORECASE
)
_ENTRY_RE = re.compile(
    r"\b(junior|entry[- ]level|entry|\bassociate\b|\bl1\b|level 1|fresher|beginner|early career)\b",
    re.IGNORECASE,
)
_MID_TITLE_RE = re.compile(
    r"\b(manager|architect|specialist|consultant|lead of|team lead|operations)\b", re.IGNORECASE
)
_EXPERIENCED_RE = re.compile(
    r"\b(senior|staff|principal|lead|expert|mid[ -]level|experienced|"
    r"\b(ii+|iv)\b|level [2-9])\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Dimension 2: function area
# ---------------------------------------------------------------------------


class FunctionArea(StrEnum):
    """What a role actually does, when the title states it."""

    ENGINEERING = "engineering"
    DATA_AI = "data_ai"
    SECURITY = "security"
    RESEARCH = "research"
    PRODUCT_DESIGN = "product_design"
    CUSTOMER_SUCCESS = "customer_success"
    GO_TO_MARKET = "go_to_market"
    FINANCE_LEGAL = "finance_legal"
    PEOPLE_WORKPLACE = "people_workplace"
    GENERAL = "general"


_FUNCTION_PATTERNS: tuple[tuple[FunctionArea, re.Pattern[str]], ...] = (
    (FunctionArea.SECURITY, re.compile(r"\b(security|threat|vulnerability|infosec|soc|abuse|fraud)\b", re.IGNORECASE)),
    (FunctionArea.RESEARCH, re.compile(r"\b(research|scientist|科研)\b", re.IGNORECASE)),
    (FunctionArea.DATA_AI, re.compile(r"\b(data|analytics|analytic|machine learning|\bml\b|intelligence|statistic|forecast)\b", re.IGNORECASE)),
    (
        FunctionArea.CUSTOMER_SUCCESS,
        re.compile(r"\b(customer success|customer experience|customer care|support|technical success)\b", re.IGNORECASE),
    ),
    (
        FunctionArea.PRODUCT_DESIGN,
        re.compile(
            r"\b(design|designer|illustrator|creative|brand|motion|\bux\b|product manager|product marketing)\b",
            re.IGNORECASE,
        ),
    ),
    (
        FunctionArea.PEOPLE_WORKPLACE,
        re.compile(r"\b(workplace|\bhr\b|human resources|talent|recruit|people|facilities|office admin)\b", re.IGNORECASE),
    ),
    (
        FunctionArea.GO_TO_MARKET,
        re.compile(
            r"\b(sales|marketing|account|business development|partnership|partner|growth|\bsdr\b|accounting for sales)\b",
            re.IGNORECASE,
        ),
    ),
    (
        FunctionArea.FINANCE_LEGAL,
        re.compile(r"\b(finance|financial|accounting|audit|legal|tax|payroll|treasury|compliance)\b", re.IGNORECASE),
    ),
    (
        FunctionArea.ENGINEERING,
        re.compile(
            r"\b(engineer|engineering|developer|software|infrastructure|site reliability|\bsre\b|platform|systems|kernel|qa|quality assurance|devops|cloud|network)\b",
            re.IGNORECASE,
        ),
    ),
)


# ---------------------------------------------------------------------------
# Location semantics
# ---------------------------------------------------------------------------

_WORK_MODE_TOKENS = re.compile(
    r"^(remote|hybrid|onsite|on-site|in-office|in -office|work from home|home based|"
    r"homebased|distributed|worldwide|global|anywhere|telecommute|flexible)$",
    re.IGNORECASE,
)

_INDIA_RE = re.compile(
    r"\b(india|indian)\b",
    re.IGNORECASE,
)
_INDIA_CITY_RE = re.compile(
    r"\b(bengaluru|bangalore|bombay|mumbai|pune|hyderabad|chennai|kolkata|delhi|"
    r"gurugram|gurgaon|noida|ahmedabad|jaipur|indore|kochi|coimbatore|mysore|"
    r"mangaluru|mangalore|lucknow|chandigarh|thiruvananthapuram|trivandrum|bhubaneshwar|"
    r"thane|navi mumbai|ncr|vadodara|nagpur)\b",
    re.IGNORECASE,
)


def is_work_mode_location(locations: list[str]) -> bool:
    """True when the recorded location is a work mode, not a real place.

    Many ATS feeds publish ``locations = ["Hybrid"]`` or ``["Remote"]``. Those are
    work modes that accidentally land in the location column; showing them as if
    they were cities makes the interface look sloppy and hides real geography.
    """
    if not locations:
        return True
    return all(_WORK_MODE_TOKENS.match(loc.strip()) is not None for loc in locations)


def is_india_eligible_location(locations: list[str]) -> bool:
    """True only when a location explicitly mentions India or an Indian city.

    Deliberately conservative: "Remote, United States" and "Home based - Worldwide"
    return False. The eligibility engine remains the authoritative gate for whether
    an Indian resident may apply; this is a browsing shortcut with visible caveats.
    """
    if not locations:
        return False
    for loc in locations:
        text = loc.strip()
        if not text:
            continue
        if _INDIA_RE.search(text) or _INDIA_CITY_RE.search(text):
            return True
    return False


# ---------------------------------------------------------------------------
# Classification results
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RoleClassification:
    """Two-dimension classification with the exact matched signal retained."""

    stage: CareerStage
    function: FunctionArea
    stage_signal: str | None
    function_signal: str | None

    @property
    def stage_label(self) -> str:
        return CAREER_STAGE_LABELS.get(self.stage, "Unspecified")

    @property
    def function_label(self) -> str:
        return FUNCTION_AREA_LABELS.get(self.function, "General")


CAREER_STAGE_LABELS: dict[CareerStage, str] = {
    CareerStage.INTERNSHIP: "Internship / Trainee",
    CareerStage.NEW_GRAD: "New Grad",
    CareerStage.ENTRY: "Entry Level (0-2 yrs)",
    CareerStage.PROFESSIONAL: "Professional",
    CareerStage.LEADERSHIP: "Leadership",
    CareerStage.UNSPECIFIED: "Unspecified",
}

FUNCTION_AREA_LABELS: dict[FunctionArea, str] = {
    FunctionArea.ENGINEERING: "Engineering",
    FunctionArea.DATA_AI: "Data & AI",
    FunctionArea.SECURITY: "Security & Trust",
    FunctionArea.RESEARCH: "Research",
    FunctionArea.PRODUCT_DESIGN: "Product & Design",
    FunctionArea.CUSTOMER_SUCCESS: "Customer Success",
    FunctionArea.GO_TO_MARKET: "Go-To-Market",
    FunctionArea.FINANCE_LEGAL: "Finance & Legal",
    FunctionArea.PEOPLE_WORKPLACE: "People & Workplace",
    FunctionArea.GENERAL: "General",
}

CAREER_STAGE_ORDER: tuple[CareerStage, ...] = (
    CareerStage.INTERNSHIP,
    CareerStage.NEW_GRAD,
    CareerStage.ENTRY,
    CareerStage.PROFESSIONAL,
    CareerStage.LEADERSHIP,
    CareerStage.UNSPECIFIED,
)


def classify_role(title: str) -> RoleClassification:
    """Classify a listing title into a career stage and a function area.

    Only the title text published by the source is inspected. Unknown signals stay
    unknown: they surface as ``UNSPECIFIED`` / ``GENERAL`` with ``signal=None`` so the
    interface can display "not stated" instead of a confident guess.
    """
    text = (title or "").strip()

    if not text:
        return RoleClassification(CareerStage.UNSPECIFIED, FunctionArea.GENERAL, None, None)

    stage: CareerStage
    stage_signal: str | None
    match = _INTERNSHIP_RE.search(text)
    if match:
        stage, stage_signal = CareerStage.INTERNSHIP, match.group(0)
    else:
        match = _NEW_GRAD_RE.search(text)
        if match:
            stage, stage_signal = CareerStage.NEW_GRAD, match.group(0)
        else:
            match = _LEADERSHIP_RE.search(text)
            if match:
                stage, stage_signal = CareerStage.LEADERSHIP, match.group(0)
            else:
                match = _ENTRY_RE.search(text)
                if match:
                    stage, stage_signal = CareerStage.ENTRY, match.group(0)
                else:
                    match = _EXPERIENCED_RE.search(text)
                    if match:
                        stage, stage_signal = CareerStage.PROFESSIONAL, match.group(0)
                    else:
                        match = _MID_TITLE_RE.search(text)
                        if match:
                            stage, stage_signal = CareerStage.PROFESSIONAL, match.group(0)
                        else:
                            stage, stage_signal = CareerStage.UNSPECIFIED, None

    function = FunctionArea.GENERAL
    function_signal: str | None = None
    for area, pattern in _FUNCTION_PATTERNS:
        found = pattern.search(text)
        if found:
            function, function_signal = area, found.group(0)
            break

    return RoleClassification(stage, function, stage_signal, function_signal)


@dataclass(frozen=True, slots=True)
class ClassifiedOpportunity:
    """An opportunity plus its derived presentation metadata (no eligibility claims)."""

    opportunity: Opportunity
    classification: RoleClassification
    location_is_work_mode: bool
    india_eligible: bool

    @property
    def role_title(self) -> str:
        return self.opportunity.title

    @property
    def company(self) -> str:
        return self.opportunity.company_name

    @property
    def work_mode_label(self) -> str:
        mode = self.opportunity.work_mode
        return mode.value if mode in WorkMode._value2member_map_ else "unspecified"

    @property
    def location_label(self) -> str:
        """Best human label for the location column."""
        locs = self.opportunity.locations
        if not locs:
            return "Not disclosed"
        if self.location_is_work_mode:
            first = locs[0].strip()
            return first if first else "Not disclosed"
        return ", ".join(locs[:2])

    @property
    def stage(self) -> CareerStage:
        return self.classification.stage


def classify_opportunity(opportunity: Opportunity) -> ClassifiedOpportunity:
    """Attach presentation metadata to a stored opportunity record."""
    locations = list(opportunity.locations or [])
    return ClassifiedOpportunity(
        opportunity=opportunity,
        classification=classify_role(opportunity.title),
        location_is_work_mode=is_work_mode_location(locations),
        india_eligible=is_india_eligible_location(locations),
    )


def classify_opportunities(opportunities: list[Opportunity]) -> list[ClassifiedOpportunity]:
    return [classify_opportunity(opp) for opp in opportunities]


# ---------------------------------------------------------------------------
# Collections: small curated slices
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Collection:
    """One filterable slice of the catalogue."""

    id: str
    label: str
    blurb: str
    icon: str
    group: str
    matcher: Callable[[ClassifiedOpportunity], bool] = field(repr=False)


def _stages(*stages: CareerStage) -> Callable[[ClassifiedOpportunity], bool]:
    wanted = set(stages)
    return lambda item: item.classification.stage in wanted


def _function(area: FunctionArea) -> Callable[[ClassifiedOpportunity], bool]:
    return lambda item: item.classification.function is area


_COLLECTION_DEFS: tuple[Collection, ...] = (
    Collection(
        id="all",
        label="Everything",
        blurb="Complete catalogue, newest first",
        icon="*",
        group="curated",
        matcher=lambda _: True,
    ),
    Collection(
        id="start_here",
        label="Start Here (0-2 yrs)",
        blurb="Internships, new grad and junior roles - the beginner-friendly shelf",
        icon="s",
        group="curated",
        matcher=_stages(
            CareerStage.INTERNSHIP, CareerStage.NEW_GRAD, CareerStage.ENTRY
        ),
    ),
    Collection(
        id="internships",
        label="Internships & Trainees",
        blurb="Internship, apprenticeship and trainee programmes",
        icon="i",
        group="curated",
        matcher=_stages(CareerStage.INTERNSHIP),
    ),
    Collection(
        id="new_grad",
        label="New Grad & Junior",
        blurb="Graduate programmes and early-career openings",
        icon="n",
        group="curated",
        matcher=_stages(CareerStage.NEW_GRAD, CareerStage.ENTRY),
    ),
    Collection(
        id="remote",
        label="Remote & Hybrid",
        blurb="Roles the source labels remote or hybrid",
        icon="r",
        group="curated",
        matcher=lambda item: item.work_mode_label in ("remote", "hybrid"),
    ),
    Collection(
        id="india",
        label="India-based",
        blurb="Listing text mentions India or an Indian city (verify eligibility)",
        icon="I",
        group="curated",
        matcher=lambda item: item.india_eligible,
    ),
    Collection(
        id="experienced",
        label="Senior & Leadership",
        blurb="Professional, principal and leadership postings",
        icon="L",
        group="curated",
        matcher=_stages(CareerStage.PROFESSIONAL, CareerStage.LEADERSHIP),
    ),
    Collection(
        id="level_not_stated",
        label="Level Not Stated",
        blurb="Titles with no stated level - open the listing to check the requirement",
        icon="?",
        group="curated",
        matcher=_stages(CareerStage.UNSPECIFIED),
    ),
)

_FUNCTION_COLLECTION_IDS: dict[FunctionArea, str] = {
    FunctionArea.ENGINEERING: "engineering",
    FunctionArea.DATA_AI: "data_ai",
    FunctionArea.SECURITY: "security",
    FunctionArea.RESEARCH: "research",
    FunctionArea.PRODUCT_DESIGN: "product_design",
    FunctionArea.CUSTOMER_SUCCESS: "customer_success",
    FunctionArea.GO_TO_MARKET: "go_to_market",
    FunctionArea.FINANCE_LEGAL: "finance_legal",
    FunctionArea.PEOPLE_WORKPLACE: "people_workplace",
    FunctionArea.GENERAL: "general",
}


def _build_function_collections() -> tuple[Collection, ...]:
    definitions: list[Collection] = []
    for area in FunctionArea:
        definitions.append(
            Collection(
                id=_FUNCTION_COLLECTION_IDS[area],
                label=FUNCTION_AREA_LABELS[area],
                blurb=f"Roles in {FUNCTION_AREA_LABELS[area].lower()}",
                icon=_FUNCTION_COLLECTION_IDS[area][:1].upper(),
                group="function",
                matcher=_function(area),
            )
        )
    return tuple(definitions)


COLLECTIONS: tuple[Collection, ...] = _COLLECTION_DEFS + _build_function_collections()

_COLLECTION_INDEX: dict[str, Collection] = {c.id: c for c in COLLECTIONS}


def collection_for_id(collection_id: str) -> Collection | None:
    """Return a collection definition by id, or None when the id is unknown."""
    return _COLLECTION_INDEX.get(collection_id)


def collections_by_group(group: str) -> tuple[Collection, ...]:
    return tuple(c for c in COLLECTIONS if c.group == group)


@dataclass(frozen=True, slots=True)
class CollectionSummary:
    id: str
    label: str
    icon: str
    group: str
    count: int
    blurb: str


def build_collection_summary(
    opportunities: list[Opportunity] | list[ClassifiedOpportunity],
) -> list[CollectionSummary]:
    """Count how many opportunities fall into each collection.

    Accepts raw or pre-classified opportunities so callers can classify once.
    """
    items: list[ClassifiedOpportunity] = [
        item if isinstance(item, ClassifiedOpportunity) else classify_opportunity(item)
        for item in opportunities
    ]
    summaries: list[CollectionSummary] = []
    for collection in COLLECTIONS:
        count = sum(1 for item in items if collection.matcher(item))
        summaries.append(
            CollectionSummary(
                id=collection.id,
                label=collection.label,
                icon=collection.icon,
                group=collection.group,
                count=count,
                blurb=collection.blurb,
            )
        )
    return summaries


def filter_by_collection(
    opportunities: list[Opportunity] | list[ClassifiedOpportunity],
    collection_id: str,
) -> list[Opportunity]:
    """Filter opportunities down to one collection.

    An unknown collection id yields an empty list rather than silently returning
    everything, so a UI desync can never dump the whole catalogue back on screen.
    """
    collection = collection_for_id(collection_id)
    if collection is None:
        return []
    out: list[Opportunity] = []
    for item in opportunities:
        classified = item if isinstance(item, ClassifiedOpportunity) else classify_opportunity(item)
        if collection.matcher(classified):
            out.append(classified.opportunity)
    return out


def collection_overview(opportunities: list[Opportunity]) -> list[str]:
    """Short human-readable lines for a whole catalogue (used by the dashboard)."""
    classified = classify_opportunities(opportunities)
    lines: list[str] = []
    for summary in build_collection_summary(classified):
        if summary.group != "curated":
            continue
        lines.append(f"{summary.icon} {summary.label}: {summary.count}")
    return lines
