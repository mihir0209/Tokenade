"""
Tokenade - Production-grade token shifting tool.

A secure, structured tool for extracting, transferring, and testing
browser sessions and authentication tokens across devices.

Modules:
    core.browser: Browser automation abstractions
    core.crypto: Cross-platform cookie encryption/decryption
    core.fingerprint: Browser fingerprint collection and matching
    core.extractor: Token extraction utilities
    handlers: Site-specific handlers (Google, etc.)
    tests: Portability testing framework
    utils: Helper utilities

Usage:
    from tokenade.cli import main
    main()
"""

__version__ = "4.0.0"
__author__ = "Tokenade Team"
__license__ = "MIT"

from tokenade.core.browser.manager import BrowserManager, BrowserConfig, BrowserFactory
from tokenade.core.crypto.cookie_crypto import (
    CookieCrypto, WindowsCookieCrypto, LinuxCookieCrypto, CookieCryptoFactory,
    DecryptedCookie,
)
from tokenade.core.fingerprint.manager import (
    BrowserFingerprint, FingerprintCollector, FingerprintManager,
)
from tokenade.core.security.credentials import (
    AccountCredentials, CredentialManager, SecureSessionStorage,
)
from tokenade.core.runtime.engine import (
    RuntimeConfig, RuntimeEngine, SessionValidator, create_engine_from_session,
)
from tokenade.handlers.base import (
    SiteHandler, HandlerRegistry, SessionData, ExtractedToken,
    AuthStatus, TokenType,
)
from tokenade.core.importer.browser_discovery import (
    BrowserProfileDiscovery, BrowserProfile,
)
from tokenade.core.importer.cookie_extractor import (
    CookieExtractor, SiteFilter, SITE_DETECTION,
)
from tokenade.core.importer.session_packager import SessionPackager
from tokenade.core.importer.session_loader import SessionLoader

__all__ = [
    "BrowserManager",
    "BrowserConfig",
    "BrowserFactory",
    "CookieCrypto",
    "WindowsCookieCrypto",
    "LinuxCookieCrypto",
    "CookieCryptoFactory",
    "DecryptedCookie",
    "BrowserFingerprint",
    "FingerprintCollector",
    "FingerprintManager",
    "AccountCredentials",
    "CredentialManager",
    "SecureSessionStorage",
    "RuntimeConfig",
    "RuntimeEngine",
    "SessionValidator",
    "create_engine_from_session",
    "SiteHandler",
    "HandlerRegistry",
    "SessionData",
    "ExtractedToken",
    "AuthStatus",
    "TokenType",
    "BrowserProfileDiscovery",
    "BrowserProfile",
    "CookieExtractor",
    "SiteFilter",
    "SITE_DETECTION",
    "SessionPackager",
    "SessionLoader",
]
