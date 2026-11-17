"""Unit tests for configuration loading and directory resolution."""

from pathlib import Path

from openpath.config import Config


def test_default_config_directories(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENPATH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENPATH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OPENPATH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OPENPATH_DB_PATH", str(tmp_path / "data" / "custom.db"))

    cfg = Config.load()
    assert cfg.config_dir == tmp_path / "config"
    assert cfg.data_dir == tmp_path / "data"
    assert cfg.state_dir == tmp_path / "state"
    assert cfg.db_path == tmp_path / "data" / "custom.db"
    assert cfg.snapshots_dir == tmp_path / "data" / "snapshots"
    assert cfg.logs_dir == tmp_path / "state" / "logs"

    # Verify directories were created
    assert cfg.config_dir.is_dir()
    assert cfg.data_dir.is_dir()
    assert cfg.state_dir.is_dir()
    assert cfg.snapshots_dir.is_dir()
    assert cfg.logs_dir.is_dir()


def test_crawler_defaults() -> None:
    cfg = Config.load()
    assert cfg.crawler.request_timeout_seconds == 30.0
    assert cfg.crawler.max_response_bytes == 10 * 1024 * 1024
    assert cfg.crawler.respect_robots_txt is True
    assert cfg.verification.strict_mode is True
