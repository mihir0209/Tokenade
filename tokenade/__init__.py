"""
Tokenade - Production-grade token shifting tool.

A secure, structured tool for extracting, transferring, and testing
browser sessions and authentication tokens across devices.

Modules:
    core.browser: Browser automation abstractions
    core.crypto: Cross-platform cookie encryption/decryption
    core.fingerprint: Browser fingerprint collection and matching
    core.importer: Cookie extraction, packaging, session lifecycle
    handlers: Legacy site handlers (prefer plugins + site_config.json)
    plugin: Plugin API base classes
    tests: Portability testing framework

Usage:
    from tokenade.cli import main
    main()
"""

__version__ = "1.1.51"
__author__ = "MiHiR"
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
from tokenade.core.integration.plugin_loader import (
    PluginLoader,
    LoadedPlugin,
    get_or_create_shared_loader,
    get_shared_loader,
    set_shared_loader,
)
from tokenade.core.integration.plugin_runner import PluginRunner
from tokenade.core.browser.stealth.backend import (
    launch_stealth_browser,
    get_stealth_backend_name,
    is_cloakbrowser_available,
)
from tokenade.core.recommend import (
    Recommendation,
    RecommendationConfig,
    recommend,
    recommend_site,
    recommend_plugin,
    recommend_browser,
)

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
    "PluginLoader",
    "LoadedPlugin",
    "PluginRunner",
    "get_or_create_shared_loader",
    "get_shared_loader",
    "set_shared_loader",
    "launch_stealth_browser",
    "get_stealth_backend_name",
    "is_cloakbrowser_available",
    "Recommendation",
    "RecommendationConfig",
    "recommend",
    "recommend_site",
    "recommend_plugin",
    "recommend_browser",
]
