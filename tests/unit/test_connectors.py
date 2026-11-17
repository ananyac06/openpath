"""Unit tests for Greenhouse, Lever, and Ashby ATS connectors."""

from unittest.mock import AsyncMock, patch

import pytest

from openpath.config import CrawlerConfig
from openpath.connectors.ashby import AshbyConnector
from openpath.connectors.greenhouse import GreenhouseConnector
from openpath.connectors.lever import LeverConnector
from openpath.models.entities import AuthorityTier, Source, WorkMode
from openpath.network.client import FetchResult, SafeHttpClient
from tests.fixtures.synthetic_ats import (
    SYNTHETIC_ASHBY_PAYLOAD,
    SYNTHETIC_GREENHOUSE_PAYLOAD,
    SYNTHETIC_LEVER_PAYLOAD,
)


@pytest.mark.asyncio
async def test_greenhouse_connector_parsing() -> None:
    client = SafeHttpClient(CrawlerConfig())
    connector = GreenhouseConnector(client)

    source = Source(
        id="ats.greenhouse.synthetic",
        connector_id="ats.greenhouse",
        name="Synthetic Corp",
        category="ats",
        authority_tier=AuthorityTier.ATS,
        metadata={"board_token": "synthetic_corp", "company_name": "Synthetic Corp"},
    )

    fake_result = FetchResult(
        url="https://boards-api.greenhouse.io/v1/boards/synthetic_corp/jobs?content=true",
        final_url="https://boards-api.greenhouse.io/v1/boards/synthetic_corp/jobs?content=true",
        status_code=200,
        headers={"content-type": "application/json"},
        content=SYNTHETIC_GREENHOUSE_PAYLOAD.encode(),
        duration_ms=45,
    )

    with patch.object(client, "fetch", new_callable=AsyncMock, return_value=fake_result):
        opps = await connector.fetch_opportunities(source)

    assert len(opps) == 2
    # First job: Bangalore, India -> Verified
    job1 = opps[0]
    assert job1.title == "Software Engineering Intern"
    assert job1.company_name == "Synthetic Corp"
    assert job1.work_mode == WorkMode.ONSITE
    assert job1.admission_class == "VERIFIED"
    assert len(job1.evidence) == 1
    assert len(job1.checks) == 4

    # Second job: US only -> Rejected
    job2 = opps[1]
    assert job2.title == "US Site Reliability Engineer"
    assert job2.admission_class == "REJECTED"


@pytest.mark.asyncio
async def test_lever_connector_parsing() -> None:
    client = SafeHttpClient(CrawlerConfig())
    connector = LeverConnector(client)

    source = Source(
        id="ats.lever.synthetic",
        connector_id="ats.lever",
        name="Synthetic Lever Corp",
        category="ats",
        authority_tier=AuthorityTier.ATS,
        metadata={"board_token": "synthetic_lever", "company_name": "Synthetic Lever Corp"},
    )

    fake_result = FetchResult(
        url="https://api.lever.co/v0/postings/synthetic_lever?mode=json",
        final_url="https://api.lever.co/v0/postings/synthetic_lever?mode=json",
        status_code=200,
        headers={"content-type": "application/json"},
        content=SYNTHETIC_LEVER_PAYLOAD.encode(),
        duration_ms=50,
    )

    with patch.object(client, "fetch", new_callable=AsyncMock, return_value=fake_result):
        opps = await connector.fetch_opportunities(source)

    assert len(opps) == 1
    job = opps[0]
    assert job.title == "Backend Engineering Trainee"
    assert job.company_name == "Synthetic Lever Corp"
    assert job.admission_class == "VERIFIED"
    assert "FastAPI" in (job.description_text or "")


@pytest.mark.asyncio
async def test_ashby_connector_parsing() -> None:
    client = SafeHttpClient(CrawlerConfig())
    connector = AshbyConnector(client)

    source = Source(
        id="ats.ashby.synthetic",
        connector_id="ats.ashby",
        name="Synthetic Ashby Org",
        category="ats",
        authority_tier=AuthorityTier.ATS,
        metadata={"board_token": "synthetic_ashby", "company_name": "Synthetic Ashby Org"},
    )

    fake_result = FetchResult(
        url="https://api.ashbyhq.com/posting-api/job-board/synthetic_ashby?includeCompensation=true",
        final_url="https://api.ashbyhq.com/posting-api/job-board/synthetic_ashby?includeCompensation=true",
        status_code=200,
        headers={"content-type": "application/json"},
        content=SYNTHETIC_ASHBY_PAYLOAD.encode(),
        duration_ms=60,
    )

    with patch.object(client, "fetch", new_callable=AsyncMock, return_value=fake_result):
        opps = await connector.fetch_opportunities(source)

    assert len(opps) == 1
    job = opps[0]
    assert job.title == "AI Research Fellow"
    assert job.work_mode == WorkMode.REMOTE
    assert job.compensation_raw == "$25,000 - $35,000 / year"
    assert job.admission_class == "VERIFIED"
