"""Unit tests for SQLite crawl frontier."""

from pathlib import Path

from openpath.crawler.frontier import CrawlFrontier
from openpath.db.connection import DatabaseManager
from openpath.db.migrations import apply_migrations


def test_crawl_frontier_lifecycle(tmp_path: Path) -> None:
    db_mgr = DatabaseManager(tmp_path / "frontier.db")
    with db_mgr.transaction() as conn:
        apply_migrations(conn)

    frontier = CrawlFrontier(db_mgr)
    run_id = "run-test-1"

    # Create crawl run first to satisfy foreign key constraint
    with db_mgr.transaction() as conn:
        conn.execute(
            "INSERT INTO crawl_runs (id, run_type, status) VALUES (?, 'incremental', 'running');",
            (run_id,),
        )

    # Enqueue tasks
    task1 = frontier.enqueue_task(run_id, "https://example.com/jobs", task_type="seed", depth=0)
    task2 = frontier.enqueue_task(
        run_id, "https://example.com/jobs/1", task_type="job_detail", depth=1
    )

    # First task popped should be depth 0
    next_task = frontier.get_next_queued_task(run_id)
    assert next_task is not None
    assert next_task.task_id == task1
    assert next_task.depth == 0

    # Mark task1 as fetched
    frontier.mark_task(task1, state="fetched")

    # Next task popped should be task2
    next_task2 = frontier.get_next_queued_task(run_id)
    assert next_task2 is not None
    assert next_task2.task_id == task2
    assert next_task2.depth == 1

    # Mark task2 as failed
    frontier.mark_task(task2, state="failed", error="HTTP 500 Server Error")

    # Queue should now have no queued tasks
    assert frontier.get_next_queued_task(run_id) is None

    stats = frontier.get_queue_stats(run_id)
    assert stats.get("fetched") == 1
    assert stats.get("failed") == 1
