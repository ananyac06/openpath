"""Unit tests for OpenPath Typer CLI commands."""

from pathlib import Path

from typer.testing import CliRunner

from openpath.cli import app
from openpath.db.connection import DatabaseManager
from openpath.db.migrations import apply_migrations

runner = CliRunner()


def test_cli_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "OpenPath version" in result.stdout


def test_cli_doctor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENPATH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENPATH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OPENPATH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OPENPATH_DB_PATH", str(tmp_path / "data" / "openpath.db"))

    # First migrate db
    db_mgr = DatabaseManager(tmp_path / "data" / "openpath.db")
    with db_mgr.transaction() as conn:
        apply_migrations(conn)

    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "System Diagnostics" in result.stdout
    assert "Python Version" in result.stdout
    assert "FTS5 Full-Text Search" in result.stdout


def test_cli_sources_list(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENPATH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENPATH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OPENPATH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OPENPATH_DB_PATH", str(tmp_path / "data" / "openpath.db"))

    db_mgr = DatabaseManager(tmp_path / "data" / "openpath.db")
    with db_mgr.transaction() as conn:
        apply_migrations(conn)

    result = runner.invoke(app, ["sources", "list"])
    assert result.exit_code == 0
    assert "Groww" in result.stdout
    assert "Meesho" in result.stdout
    assert "Atlan" in result.stdout


def test_cli_profiles_add_and_list(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENPATH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENPATH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OPENPATH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OPENPATH_DB_PATH", str(tmp_path / "data" / "openpath.db"))

    db_mgr = DatabaseManager(tmp_path / "data" / "openpath.db")
    with db_mgr.transaction() as conn:
        apply_migrations(conn)

    add_res = runner.invoke(
        app,
        ["profiles", "add", "--name", "Test Candidate", "--degree", "B.Tech", "--year", "3", "--skills", "Python,Docker"],
    )
    assert add_res.exit_code == 0
    assert "successfully created" in add_res.stdout

    list_res = runner.invoke(app, ["profiles", "list"])
    assert list_res.exit_code == 0
    assert "Test Candidate" in list_res.stdout
