"""Tunnel error types."""


class TunnelError(Exception):
    """Base class for tunnel failures."""


class AuthError(TunnelError):
    """Authentication/pairing/token failure (never retried silently)."""


class PairingError(AuthError):
    """Pairing code invalid, reused, or expired."""
