"""System diagnostics and health checking engine for OpenPath."""

from __future__ import annotations

import platform
import sqlite3
import sys
from datetime import UTC
from typing import Any

from pydantic import BaseModel

from openpath.config import Config
from openpath.db.connection import DatabaseManager
from openpath.db.migrations import get_applied_migrations


class CheckItem(BaseModel):
    name: str
    category: str
    status: str  # 'PASS', 'WARN', 'FAIL'
    message: str
    details: dict[str, Any] = {}


class DiagnosticReport(BaseModel):
    items: list[CheckItem]
    overall_status: str  # 'HEALTHY', 'DEGRADED', 'UNHEALTHY'
    timestamp: str

    @property
    def has_failures(self) -> bool:
        return any(item.status == "FAIL" for item in self.items)


def run_diagnostics(config: Config) -> DiagnosticReport:
    """Run full suite of environment, filesystem, and database diagnostics."""
    from datetime import datetime

    items: list[CheckItem] = []

    # 1. Python Environment Check
    py_version = platform.python_version()
    major, minor = sys.version_info[:2]
    if (major, minor) >= (3, 13):
        items.append(
            CheckItem(
                name="Python Version",
                category="Runtime",
                status="PASS",
                message=f"Python {py_version} (supported baseline >= 3.13)",
                details={"version": py_version, "interpreter": sys.executable},
            )
        )
    else:
        items.append(
            CheckItem(
                name="Python Version",
                category="Runtime",
                status="FAIL",
                message=f"Python {py_version} is below minimum requirement 3.13",
                details={"version": py_version},
            )
        )

    # 2. Operating System Check
    os_name = platform.system()
    items.append(
        CheckItem(
            name="Operating System",
            category="Runtime",
            status="PASS" if os_name.lower() == "linux" else "WARN",
            message=f"{os_name} {platform.release()} ({platform.machine()})",
            details={"platform": platform.platform()},
        )
    )

    # 3. Directory Permissions Check
    dirs_to_check = [
        ("Config Directory", config.config_dir),
        ("Data Directory", config.data_dir),
        ("State Directory", config.state_dir),
        ("Snapshots Directory", config.snapshots_dir),
        ("Logs Directory", config.logs_dir),
    ]
    for label, dir_path in dirs_to_check:
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            test_file = dir_path / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
            items.append(
                CheckItem(
                    name=label,
                    category="Filesystem",
                    status="PASS",
                    message=f"Writable ({dir_path})",
                    details={"path": str(dir_path)},
                )
            )
        except Exception as err:
            items.append(
                CheckItem(
                    name=label,
                    category="Filesystem",
                    status="FAIL",
                    message=f"Not writable: {err}",
                    details={"path": str(dir_path), "error": str(err)},
                )
            )

    # 4. Database Checks
    db_mgr = DatabaseManager(config.db_path)
    if not config.db_path.exists():
        items.append(
            CheckItem(
                name="Database File",
                category="Database",
                status="WARN",
                message=f"Database file not yet created at {config.db_path}",
                details={"path": str(config.db_path)},
            )
        )
    else:
        db_size_kb = config.db_path.stat().st_size / 1024
        items.append(
            CheckItem(
                name="Database File",
                category="Database",
                status="PASS",
                message=f"Present ({db_size_kb:.1f} KB at {config.db_path})",
                details={"path": str(config.db_path), "size_kb": db_size_kb},
            )
        )

        # Integrity Check
        try:
            ok, msg = db_mgr.check_integrity()
            items.append(
                CheckItem(
                    name="Database Integrity",
                    category="Database",
                    status="PASS" if ok else "FAIL",
                    message=f"Integrity check: {msg}",
                    details={"result": msg},
                )
            )
        except Exception as err:
            items.append(
                CheckItem(
                    name="Database Integrity",
                    category="Database",
                    status="FAIL",
                    message=f"Integrity check failed: {err}",
                )
            )

        # FTS5 Check
        has_fts5 = db_mgr.check_fts5_support()
        items.append(
            CheckItem(
                name="FTS5 Full-Text Search",
                category="Database",
                status="PASS" if has_fts5 else "FAIL",
                message="SQLite FTS5 module enabled and active"
                if has_fts5
                else "FTS5 not supported by SQLite",
            )
        )

        # Migrations Check
        try:
            with db_mgr.connection() as conn:
                applied = get_applied_migrations(conn)
                items.append(
                    CheckItem(
                        name="Database Migrations",
                        category="Database",
                        status="PASS" if applied else "WARN",
                        message=f"{len(applied)} migrations applied (versions: {sorted(applied)})",
                        details={"applied_versions": list(applied)},
                    )
                )

                # Row counts for key tables
                counts: dict[str, int] = {}
                for tbl in [
                    "organisations",
                    "sources",
                    "source_connectors",
                    "opportunities",
                    "candidate_profiles",
                ]:
                    try:
                        c = conn.execute(f"SELECT count(*) FROM {tbl};").fetchone()[0]
                        counts[tbl] = c
                    except sqlite3.Error:
                        counts[tbl] = -1

                items.append(
                    CheckItem(
                        name="Database Entities",
                        category="Database",
                        status="PASS",
                        message=f"Organizations: {counts.get('organisations', 0)}, Sources: {counts.get('sources', 0)}, Connectors: {counts.get('source_connectors', 0)}, Opportunities: {counts.get('opportunities', 0)}",
                        details=counts,
                    )
                )
        except Exception as err:
            items.append(
                CheckItem(
                    name="Database Connectivity",
                    category="Database",
                    status="FAIL",
                    message=f"Failed to query database: {err}",
                )
            )

    # Determine overall status
    if any(i.status == "FAIL" for i in items):
        overall = "UNHEALTHY"
    elif any(i.status == "WARN" for i in items):
        overall = "DEGRADED"
    else:
        overall = "HEALTHY"

    return DiagnosticReport(
        items=items,
        overall_status=overall,
        timestamp=datetime.now(UTC).isoformat(),
    )
