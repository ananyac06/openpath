"""Configuration management for OpenPath adhering to XDG Base Directory specification."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from openpath.exceptions import ConfigurationError


class CrawlerConfig(BaseModel):
    """Configuration for web crawling and network interactions."""

    user_agent: str = "OpenPathResearchEngine/0.1.0 (+https://github.com/openpath/openpath)"
    request_timeout_seconds: float = 30.0
    connect_timeout_seconds: float = 10.0
    max_retries: int = 3
    backoff_factor: float = 1.5
    max_response_bytes: int = 10 * 1024 * 1024  # 10 MB cap
    default_rate_limit_rps: float = 1.0
    ats_rate_limit_rps: float = 2.0
    circuit_breaker_error_threshold: int = 3
    circuit_breaker_cooldown_seconds: int = 300
    respect_robots_txt: bool = True
    enable_javascript_fallback: bool = False


class VerificationConfig(BaseModel):
    """Configuration for authenticity and verification gates."""

    strict_mode: bool = True
    require_company_identity: bool = True
    require_source_authority: bool = True
    require_destination_match: bool = True
    require_active_availability: bool = True
    default_country_filter: str = "India"


class APISecretsConfig(BaseModel):
    """Optional API credentials loaded from config or environment."""

    github_token: str | None = None
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str = "openpath:research:v0.1.0 (by /u/openpath_research)"


class Config(BaseModel):
    """Authoritative system configuration."""

    config_dir: Path = Field(default_factory=lambda: Config.get_default_config_dir())
    data_dir: Path = Field(default_factory=lambda: Config.get_default_data_dir())
    state_dir: Path = Field(default_factory=lambda: Config.get_default_state_dir())
    db_path: Path = Field(default_factory=lambda: Config.get_default_db_path())
    crawler: CrawlerConfig = Field(default_factory=CrawlerConfig)
    verification: VerificationConfig = Field(default_factory=VerificationConfig)
    secrets: APISecretsConfig = Field(default_factory=APISecretsConfig)

    @property
    def snapshots_dir(self) -> Path:
        """Directory for storing raw page snapshots securely."""
        return self.data_dir / "snapshots"

    @property
    def logs_dir(self) -> Path:
        """Directory for execution logs."""
        return self.state_dir / "logs"

    @property
    def log_file(self) -> Path:
        """Primary log file path."""
        return self.logs_dir / "openpath.log"

    @property
    def config_file(self) -> Path:
        """Config file path."""
        return self.config_dir / "config.toml"

    def ensure_directories(self) -> None:
        """Ensure all required local directories exist."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.state_dir.mkdir(parents=True, exist_ok=True)
            self.snapshots_dir.mkdir(parents=True, exist_ok=True)
            self.logs_dir.mkdir(parents=True, exist_ok=True)
        except OSError as err:
            raise ConfigurationError(
                f"Failed to create directory structure: {err}",
                details={"error": str(err)},
            ) from err

    @staticmethod
    def _check_writable_dir(target: Path, sub: str) -> Path:
        """Verify target directory is writable; fallback to workspace .openpath if read-only."""
        try:
            target.mkdir(parents=True, exist_ok=True)
            probe = target / ".probe"
            probe.touch()
            probe.unlink()
            return target
        except (OSError, PermissionError):
            fallback = Path.cwd() / ".openpath" / sub
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback

    @staticmethod
    def get_default_config_dir() -> Path:
        env_val = os.environ.get("OPENPATH_CONFIG_DIR")
        if env_val:
            return Path(env_val).expanduser().resolve()
        ws_openpath = Path.cwd() / ".openpath"
        if ws_openpath.exists():
            d = ws_openpath / "config"
            d.mkdir(parents=True, exist_ok=True)
            return d
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            candidate = Path(xdg_config).expanduser().resolve() / "openpath"
        else:
            candidate = Path.home() / ".config" / "openpath"
        return Config._check_writable_dir(candidate, "config")

    @staticmethod
    def get_default_data_dir() -> Path:
        env_val = os.environ.get("OPENPATH_DATA_DIR")
        if env_val:
            return Path(env_val).expanduser().resolve()
        ws_openpath = Path.cwd() / ".openpath"
        if ws_openpath.exists():
            d = ws_openpath / "data"
            d.mkdir(parents=True, exist_ok=True)
            return d
        xdg_data = os.environ.get("XDG_DATA_HOME")
        if xdg_data:
            candidate = Path(xdg_data).expanduser().resolve() / "openpath"
        else:
            candidate = Path.home() / ".local" / "share" / "openpath"
        return Config._check_writable_dir(candidate, "data")

    @staticmethod
    def get_default_state_dir() -> Path:
        env_val = os.environ.get("OPENPATH_STATE_DIR")
        if env_val:
            return Path(env_val).expanduser().resolve()
        ws_openpath = Path.cwd() / ".openpath"
        if ws_openpath.exists():
            d = ws_openpath / "state"
            d.mkdir(parents=True, exist_ok=True)
            return d
        xdg_state = os.environ.get("XDG_STATE_HOME")
        if xdg_state:
            candidate = Path(xdg_state).expanduser().resolve() / "openpath"
        else:
            candidate = Path.home() / ".local" / "state" / "openpath"
        return Config._check_writable_dir(candidate, "state")

    @staticmethod
    def get_default_db_path() -> Path:
        env_val = os.environ.get("OPENPATH_DB_PATH")
        if env_val:
            return Path(env_val).expanduser().resolve()
        return Config.get_default_data_dir() / "openpath.db"

    @classmethod
    def load(cls) -> Config:
        """Load configuration from files, environment variables, and defaults."""
        config_dir = cls.get_default_config_dir()
        data_dir = cls.get_default_data_dir()
        state_dir = cls.get_default_state_dir()
        db_path = cls.get_default_db_path()

        config_file = config_dir / "config.toml"
        raw_data: dict[str, Any] = {}
        if config_file.is_file():
            try:
                with open(config_file, "rb") as f:
                    raw_data = tomllib.load(f)
            except Exception as err:
                raise ConfigurationError(
                    f"Error reading configuration file at {config_file}: {err}",
                    details={"path": str(config_file)},
                ) from err

        crawler_data = raw_data.get("crawler", {})
        verification_data = raw_data.get("verification", {})
        secrets_data = raw_data.get("secrets", {})

        # Environment variable overrides for secrets
        if "GITHUB_TOKEN" in os.environ:
            secrets_data["github_token"] = os.environ["GITHUB_TOKEN"]
        if "REDDIT_CLIENT_ID" in os.environ:
            secrets_data["reddit_client_id"] = os.environ["REDDIT_CLIENT_ID"]
        if "REDDIT_CLIENT_SECRET" in os.environ:
            secrets_data["reddit_client_secret"] = os.environ["REDDIT_CLIENT_SECRET"]

        cfg = cls(
            config_dir=config_dir,
            data_dir=data_dir,
            state_dir=state_dir,
            db_path=db_path,
            crawler=CrawlerConfig(**crawler_data),
            verification=VerificationConfig(**verification_data),
            secrets=APISecretsConfig(**secrets_data),
        )
        cfg.ensure_directories()
        return cfg


# Global singleton instance cache
_GLOBAL_CONFIG: Config | None = None


def get_config() -> Config:
    """Return the global cached Config instance, loading it if necessary."""
    global _GLOBAL_CONFIG
    if _GLOBAL_CONFIG is None:
        _GLOBAL_CONFIG = Config.load()
    return _GLOBAL_CONFIG
