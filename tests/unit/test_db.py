"""Unit tests for SQLite database manager, PRAGMAs, and transaction safety."""

from pathlib import Path

import pytest

from openpath.db.connection import DatabaseManager
from openpath.exceptions import DatabaseError


def test_database_connection_pragmas(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    mgr = DatabaseManager(db_path)

    with mgr.connection() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert journal_mode.lower() == "wal"

        foreign_keys = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        assert foreign_keys == 1

        busy_timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        assert busy_timeout == 5000


def test_database_transactions_and_rollback(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    mgr = DatabaseManager(db_path)

    with mgr.connection() as conn:
        conn.execute("CREATE TABLE items (id TEXT PRIMARY KEY, val TEXT);")

    # Successful commit
    with mgr.transaction() as conn:
        conn.execute("INSERT INTO items (id, val) VALUES ('1', 'alpha');")

    with mgr.connection() as conn:
        row = conn.execute("SELECT val FROM items WHERE id = '1';").fetchone()
        assert row is not None
        assert row[0] == "alpha"

    # Transaction rollback on error
    with pytest.raises(DatabaseError), mgr.transaction() as conn:
        conn.execute("INSERT INTO items (id, val) VALUES ('2', 'beta');")
        raise ValueError("Forced error to trigger rollback")

    with mgr.connection() as conn:
        row2 = conn.execute("SELECT val FROM items WHERE id = '2';").fetchone()
        assert row2 is None


def test_database_integrity_and_fts5(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    mgr = DatabaseManager(db_path)

    ok, msg = mgr.check_integrity()
    assert ok is True
    assert msg == "ok"

    fts_ok = mgr.check_fts5_support()
    assert fts_ok is True
