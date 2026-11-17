"""Typed domain exception hierarchy for OpenPath."""

from typing import Any


class OpenPathError(Exception):
    """Base exception for all OpenPath errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(OpenPathError):
    """Raised when configuration is invalid or missing."""


class DatabaseError(OpenPathError):
    """Raised on database connection, migration, or query failure."""


class MigrationError(DatabaseError):
    """Raised when database schema migration fails."""


class NetworkError(OpenPathError):
    """Raised when an outbound network request fails."""


class SSRFSecurityViolation(NetworkError):
    """Raised when an outbound URL violates SSRF boundaries (private IP, cloud metadata, etc.)."""


class RateLimitExceeded(NetworkError):
    """Raised when a remote server returns HTTP 429 or rate limits are exceeded."""


class ConnectorError(OpenPathError):
    """Raised when a source connector encounters an unrecoverable error."""


class ExtractionError(OpenPathError):
    """Raised when document or HTML extraction fails."""


class VerificationError(OpenPathError):
    """Raised when an opportunity verification process fails or produces invalid states."""
