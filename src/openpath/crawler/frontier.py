"""Persistent, resumable crawl frontier backed by SQLite."""

from __future__ import annotations

import logging
import uuid

from openpath.db.connection import DatabaseManager

logger = logging.getLogger(__name__)


class CrawlTaskRecord:
    def __init__(
        self,
        task_id: str,
        run_id: str,
        source_id: str | None,
        url: str,
        task_type: str,
        depth: int,
        state: str,
        attempts: int,
    ) -> None:
        self.task_id = task_id
        self.run_id = run_id
        self.source_id = source_id
        self.url = url
        self.task_type = task_type
        self.depth = depth
        self.state = state
        self.attempts = attempts


class CrawlFrontier:
    """Manages crawl task state transitions and scheduling in SQLite."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def enqueue_task(
        self,
        run_id: str,
        url: str,
        task_type: str = "board_listing",
        source_id: str | None = None,
        parent_task_id: str | None = None,
        depth: int = 0,
    ) -> str:
        """Enqueue a new crawl task if not already queued."""
        task_id = str(uuid.uuid4())
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO crawl_tasks (
                    id, run_id, source_id, parent_task_id, url, task_type, depth, state, attempts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', 0);
                """,
                (task_id, run_id, source_id, parent_task_id, url, task_type, depth),
            )
        return task_id

    def get_next_queued_task(self, run_id: str) -> CrawlTaskRecord | None:
        """Fetch the next available queued task."""
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT id, run_id, source_id, url, task_type, depth, state, attempts
                FROM crawl_tasks
                WHERE run_id = ? AND state = 'queued'
                ORDER BY depth ASC, attempts ASC, created_at ASC
                LIMIT 1;
                """,
                (run_id,),
            ).fetchone()
            if not row:
                return None
            return CrawlTaskRecord(
                task_id=row["id"],
                run_id=row["run_id"],
                source_id=row["source_id"],
                url=row["url"],
                task_type=row["task_type"],
                depth=row["depth"],
                state=row["state"],
                attempts=row["attempts"],
            )

    def mark_task(self, task_id: str, state: str, error: str | None = None) -> None:
        """Update task state and record error if any."""
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE crawl_tasks
                SET state = ?, attempts = attempts + 1, last_error = ?,
                    updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                WHERE id = ?;
                """,
                (state, error, task_id),
            )

    def get_queue_stats(self, run_id: str) -> dict[str, int]:
        """Return counts of tasks in each state for a run."""
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT state, count(*) FROM crawl_tasks
                WHERE run_id = ?
                GROUP BY state;
                """,
                (run_id,),
            ).fetchall()
            return {r[0]: r[1] for r in rows}
