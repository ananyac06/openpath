"""Text extraction, HTML cleaning, and data normalisation utilities."""

from __future__ import annotations

import re

import trafilatura
from lxml import html

from openpath.models.entities import WorkMode


def extract_clean_text(html_content: str) -> str:
    """Extract clean body text from raw HTML using Trafilatura with lxml fallback."""
    if not html_content or not html_content.strip():
        return ""

    # Primary: Trafilatura boilerplate-free extraction
    extracted = trafilatura.extract(
        html_content,
        include_links=False,
        include_images=False,
        include_tables=True,
        no_fallback=False,
    )
    if extracted and extracted.strip():
        return extracted.strip()

    # Fallback: lxml direct text extraction
    try:
        tree = html.fromstring(html_content)
        # Remove script and style elements
        for element in tree.xpath("//script | //style | //noscript"):
            element.drop_tree()
        text = tree.text_content()
        # Clean excessive whitespace
        return re.sub(r"\s+", " ", text).strip()
    except Exception:
        return ""


def normalize_work_mode(raw_location: str | None, text_content: str | None = None) -> WorkMode:
    """Determine WorkMode (REMOTE, HYBRID, ONSITE, UNCLEAR) from location and description."""
    combined = f"{raw_location or ''} {text_content or ''}".lower()

    if "remote" in combined or "work from home" in combined or "telecommute" in combined:
        if "hybrid" in combined or "flexible onsite" in combined:
            return WorkMode.HYBRID
        return WorkMode.REMOTE
    if "hybrid" in combined:
        return WorkMode.HYBRID
    if "onsite" in combined or "in-office" in combined or "in office" in combined:
        return WorkMode.ONSITE
    if raw_location and any(city in raw_location.lower() for city in ["bangalore", "bengaluru", "hyderabad", "pune", "mumbai", "delhi", "noida", "gurgaon"]):
        return WorkMode.ONSITE

    return WorkMode.UNCLEAR


def detect_india_accessibility(raw_location: str | None, text_content: str | None = None) -> bool | None:
    """
    Check if opportunity is accessible to candidates residing in India.
    Returns:
      True  -> Confirmed India accessible.
      False -> Excluded (e.g., explicit US-only, UK-only, must be in California).
      None  -> Unclear / Unknown.
    """
    combined = f"{raw_location or ''} {text_content or ''}".lower()

    # Explicit exclusions
    exclusions = [
        "must be located in the us",
        "us only",
        "united states only",
        "us work authorization required",
        "must reside in the united states",
        "uk only",
        "canada only",
        "must be legally authorized to work in the united states without sponsorship",
        "eu work authorization required",
    ]
    for exc in exclusions:
        if exc in combined:
            return False

    # Positive India indicators
    india_indicators = [
        "india",
        "bangalore",
        "bengaluru",
        "hyderabad",
        "pune",
        "mumbai",
        "gurgaon",
        "gurugram",
        "noida",
        "delhi",
        "chennai",
        "kolkata",
        "worldwide",
        "anywhere in the world",
        "global remote",
    ]
    for ind in india_indicators:
        if ind in combined:
            return True

    return None
