"""Research orchestrator coordinating crawl runs, source connectors, and evidence persistence."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

from openpath.config import Config
from openpath.connectors.registry import get_connector
from openpath.crawler.frontier import CrawlFrontier
from openpath.db.connection import DatabaseManager
from openpath.db.repository import Repository
from openpath.network.client import SafeHttpClient

logger = logging.getLogger(__name__)


class RunResult:
    """Summary of a research run."""

    def __init__(
        self,
        run_id: str,
        status: str,
        sources_attempted: int,
        opportunities_extracted: int,
        opportunities_verified: int,
    ) -> None:
        self.run_id = run_id
        self.status = status
        self.sources_attempted = sources_attempted
        self.opportunities_extracted = opportunities_extracted
        self.opportunities_verified = opportunities_verified


class ResearchOrchestrator:
    """Coordinates research runs across declared sources."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.db_mgr = DatabaseManager(config.db_path)
        self.repo = Repository(self.db_mgr)
        self.frontier = CrawlFrontier(self.db_mgr)
        self.http_client = SafeHttpClient(config.crawler)

    async def execute_run(
        self,
        source_id: str | None = None,
        profile_id: str | None = None,
        run_type: str = "incremental",
    ) -> RunResult:
        """Execute a research run for all enabled sources or a specific source."""
        run_id = str(uuid.uuid4())
        started_at = datetime.now(UTC).isoformat()

        # 1. Register run in DB
        with self.db_mgr.transaction() as conn:
            conn.execute(
                """
                INSERT INTO crawl_runs (id, run_type, profile_id, status, started_at)
                VALUES (?, ?, ?, 'running', ?);
                """,
                (run_id, run_type, profile_id, started_at),
            )

        # 2. Select target sources
        if source_id:
            src = self.repo.get_source(source_id)
            sources = [src] if src else []
        else:
            sources = self.repo.list_sources(enabled_only=True)

        sources_attempted = 0
        total_extracted = 0
        total_verified = 0

        try:
            for source in sources:
                sources_attempted += 1
                logger.info("Executing research for source %s (%s)...", source.id, source.connector_id)
                self.repo.record_source_access(source.id, "attempted", run_id=run_id)

                try:
                    connector = get_connector(source.connector_id, self.http_client)
                    opps = await connector.fetch_opportunities(source)

                    for opp in opps:
                        total_extracted += 1
                        if opp.admission_class == "VERIFIED":
                            total_verified += 1
                    self.repo.save_opportunities(opps)

                    self.repo.record_source_access(
                        source.id, "success", detail=f"Extracted {len(opps)} opportunities", run_id=run_id
                    )
                except Exception as err:
                    logger.error("Failed to crawl source %s: %s", source.id, err)
                    self.repo.record_source_access(
                        source.id, "failed", detail=str(err), run_id=run_id
                    )

            finished_at = datetime.now(UTC).isoformat()
            coverage_data = {
                "sources_attempted": sources_attempted,
                "opportunities_extracted": total_extracted,
                "opportunities_verified": total_verified,
            }

            with self.db_mgr.transaction() as conn:
                conn.execute(
                    """
                    UPDATE crawl_runs
                    SET status = 'completed', finished_at = ?, coverage_json = ?
                    WHERE id = ?;
                    """,
                    (finished_at, json.dumps(coverage_data), run_id),
                )

            return RunResult(
                run_id=run_id,
                status="completed",
                sources_attempted=sources_attempted,
                opportunities_extracted=total_extracted,
                opportunities_verified=total_verified,
            )

        finally:
            await self.http_client.close()
