"""Logging configuration for OpenPath."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_INITIALIZED = False


def setup_logging(
    log_file: Path | None = None,
    level: int = logging.INFO,
    verbose: bool = False,
    enable_console: bool = False,
) -> logging.Logger:
    """Configure system logging for OpenPath."""
    global _INITIALIZED
    root_logger = logging.getLogger("openpath")

    if _INITIALIZED:
        return root_logger

    effective_level = logging.DEBUG if verbose else level
    root_logger.setLevel(effective_level)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    if log_file:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                filename=log_file,
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setLevel(effective_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except OSError:
            pass  # Fall back gracefully if cannot open file

    if enable_console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(effective_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    _INITIALIZED = True
    return root_logger
