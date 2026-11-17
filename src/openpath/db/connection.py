"""Database connection manager with WAL mode, foreign keys, and managed write concurrency."""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path

from openpath.exceptions import DatabaseError

logger = logging.getLogger(__name__)

# Reentrant lock for managing serial writes to SQLite in WAL mode
_WRITE_LOCK = threading.RLock()


class DatabaseManager:
    """Manages SQLite connections and thread-safe transactions for OpenPath."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._ensure_db_dir()

    def _ensure_db_dir(self) -> None:
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as err:
            raise DatabaseError(
                f"Failed to create database directory {self.db_path.parent}: {err}",
                details={"path": str(self.db_path)},
            ) from err

    def create_connection(self) -> sqlite3.Connection:
        """Create and configure a new SQLite connection with strict settings."""
        try:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=5.0,
                check_same_thread=False,
                isolation_level=None,  # Autocommit mode; explicit BEGIN/COMMIT used in transactions
            )
            conn.row_factory = sqlite3.Row

            # Configure performance and safety PRAGMAs
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA cache_size = -2000;")  # ~2 MB cache

            return conn
        except sqlite3.Error as err:
            raise DatabaseError(
                f"Failed to connect to database at {self.db_path}: {err}",
                details={"path": str(self.db_path), "error": str(err)},
            ) from err

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection]:
        """Context manager providing an open SQLite connection."""
        conn = self.create_connection()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection]:
        """Context manager providing a thread-safe atomic transaction under a write lock."""
        with _WRITE_LOCK:
            conn = self.create_connection()
            try:
                conn.execute("BEGIN IMMEDIATE;")
                yield conn
                if conn.in_transaction:
                    conn.execute("COMMIT;")
            except Exception as err:
                if conn.in_transaction:
                    with suppress(sqlite3.Error):
                        conn.execute("ROLLBACK;")
                raise DatabaseError(
                    f"Transaction failed: {err}",
                    details={"error": str(err)},
                ) from err
            finally:
                conn.close()

    def check_integrity(self) -> tuple[bool, str]:
        """Execute PRAGMA integrity_check and return (passed, message)."""
        with self.connection() as conn:
            row = conn.execute("PRAGMA integrity_check;").fetchone()
            msg = row[0] if row else "unknown"
            return (msg == "ok", msg)

    def check_fts5_support(self) -> bool:
        """Verify whether SQLite has FTS5 module enabled."""
        try:
            with self.connection() as conn:
                conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _test_fts USING fts5(col);")
                conn.execute("DROP TABLE _test_fts;")
                return True
        except sqlite3.Error:
            return False
