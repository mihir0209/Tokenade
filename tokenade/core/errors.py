"""Custom exception hierarchy for Tokenade.

All exceptions inherit from TokenadeError for easy catching.
Each exception carries context (operation, file, browser, domain) for debugging.
"""

from __future__ import annotations


class TokenadeError(Exception):
    """Base exception for all Tokenade errors."""

    def __init__(self, message: str, *, operation: str | None = None, cause: Exception | None = None):
        self.operation = operation
        self._cause = cause
        super().__init__(message)
        if cause:
            self.__cause__ = cause


class ExtractionError(TokenadeError):
    """Raised when cookie/session extraction fails."""


class InjectionError(TokenadeError):
    """Raised when session injection into browser fails."""


class EncryptionError(TokenadeError):
    """Raised when encryption/decryption fails."""


class DecryptionError(EncryptionError, ValueError):
    """Raised when decryption fails (wrong password, corrupted data).

    Inherits from both EncryptionError and ValueError for backward compatibility.
    """


class SessionNotFoundError(TokenadeError):
    """Raised when a session file cannot be found or loaded."""


class BrowserNotFoundError(TokenadeError):
    """Raised when a browser profile cannot be discovered."""


class ProxyError(TokenadeError):
    """Raised when proxy operation fails."""


class DependencyError(TokenadeError):
    """Raised when a required optional/runtime dependency is missing.

    Prefer hard dependencies in packaging; use this when a feature is
    requested but the library cannot be imported (broken install).
    """


class ConfigurationError(TokenadeError):
    """Raised when configuration is invalid or missing."""


class ValidationError(TokenadeError):
    """Raised when session validation fails."""


class PluginError(TokenadeError):
    """Raised when plugin loading or execution fails."""


class NetworkError(TokenadeError):
    """Raised when network operations fail (webhooks, API calls)."""


class FormatError(TokenadeError):
    """Raised when format conversion fails."""
