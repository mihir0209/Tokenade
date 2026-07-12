"""Plugin-format adapters for legacy site handlers.

Converts existing legacy handlers (Google, GitHub, Generic OAuth2) to
SiteHandlerPlugin format without changing their internal logic.

The adapter pattern:
- Subclass SiteHandlerPlugin (plugin interface)
- Delegate to legacy handler logic (browser-based extraction/injection)
- Return PluginResult instead of raw dicts/bools

Site config (domains, critical cookies, URLs) is provided via
site_config.json files that ship alongside these adapters.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from tokenade.plugin.api import PluginResult
from tokenade.plugin.base import SiteHandlerPlugin

logger = logging.getLogger(__name__)


class LegacyHandlerAdapter(SiteHandlerPlugin):
    """Base adapter wrapping a legacy ``tokenade.handlers.base.SiteHandler``.

    Subclasses set ``_legacy_cls`` and provide a ``site_config.json`` in
    their plugin directory. ``extract_session()`` / ``inject_session()``
    delegate to the legacy handler's cookie extraction/injection helpers.

    The legacy handler is instantiated with ``browser_manager`` from the
    context passed to ``extract_session()``.
    """

    _legacy_cls: Any = None

    def __init__(self):
        super().__init__()
        self._legacy: Optional[Any] = None

    def _get_legacy(self, browser_context: Any = None) -> Any:
        """Get or create the legacy handler instance.

        Args:
            browser_context: Optional browser context to attach.

        Returns:
            Legacy handler instance.
        """
        if self._legacy is None and self._legacy_cls is not None:
            self._legacy = self._legacy_cls()
        if self._legacy and browser_context is not None:
            self._legacy.browser = browser_context
        return self._legacy

    def extract_session(
        self, _browser_context: Any, url: str = ""
    ) -> PluginResult:
        """Extract cookies + storage via legacy handler, return PluginResult.

        Args:
            _browser_context: The browser context (Playwright or CDP).
            url: Target URL (used for domain filtering).

        Returns:
            PluginResult with data={"cookies": [...]}
        """
        legacy = self._get_legacy(_browser_context)
        if legacy is None:
            return PluginResult(success=False, error="Legacy handler not available")

        try:
            cookies = legacy.extract_cookies()
            return PluginResult(
                success=True,
                data={"cookies": cookies, "url": url},
            )
        except Exception as e:
            logger.error(f"{self.name}: extract_session failed: {e}")
            return PluginResult(success=False, error=str(e))

    def inject_session(
        self, _browser_context: Any, session: dict
    ) -> PluginResult:
        """Inject cookies into browser via legacy handler.

        Args:
            _browser_context: The browser context.
            session: Session data with "cookies" key.

        Returns:
            PluginResult with data={"injected_count": N}
        """
        legacy = self._get_legacy(_browser_context)
        if legacy is None:
            return PluginResult(success=False, error="Legacy handler not available")

        cookies = session.get("cookies", [])
        try:
            if hasattr(legacy, "_add_cookies"):
                legacy._add_cookies(cookies)
            return PluginResult(
                success=True,
                data={"injected_count": len(cookies)},
            )
        except Exception as e:
            logger.error(f"{self.name}: inject_session failed: {e}")
            return PluginResult(success=False, error=str(e))

    def validate(self, session: dict) -> PluginResult:
        """Validate session via legacy handler."""
        legacy = self._get_legacy()
        if legacy is None:
            return PluginResult(success=False, error="Legacy handler not available")

        cookies = session.get("cookies", [])
        try:
            valid = legacy.validate_session(cookies)
            return PluginResult(
                success=True,
                data={"valid": bool(valid), "score": 100.0 if valid else 0.0},
            )
        except Exception as e:
            return PluginResult(
                success=True,
                data={"valid": False, "score": 0.0},
                error=str(e),
            )


class GoogleHandlerAdapter(LegacyHandlerAdapter):
    """Google site handler plugin (adapter around GoogleHandler)."""

    name = "google-handler"
    version = "1.0.0"
    description = "Google (Labs/Gmail) session extraction/injection"
    author = "MiHiR"
    API_VERSION = "1.1.0"

    def __init__(self):
        # Import lazily to avoid circular imports
        from tokenade.handlers.google import GoogleHandler

        GoogleHandlerAdapter._legacy_cls = GoogleHandler
        super().__init__()


class GitHubHandlerAdapter(LegacyHandlerAdapter):
    """GitHub site handler plugin (adapter around GitHubHandler)."""

    name = "github-handler"
    version = "1.0.0"
    description = "GitHub session extraction/injection"
    author = "MiHiR"
    API_VERSION = "1.1.0"

    def __init__(self):
        from tokenade.handlers.github import GitHubHandler

        GitHubHandlerAdapter._legacy_cls = GitHubHandler
        super().__init__()


class GenericOAuth2HandlerAdapter(LegacyHandlerAdapter):
    """Generic OAuth2 site handler plugin (adapter around GenericOAuth2Handler)."""

    name = "generic-oauth-handler"
    version = "1.0.0"
    description = "Generic OAuth2 session extraction/injection"
    author = "MiHiR"
    API_VERSION = "1.1.0"

    def __init__(self):
        from tokenade.handlers.generic_oauth import GenericOAuth2Handler

        GenericOAuth2HandlerAdapter._legacy_cls = GenericOAuth2Handler
        super().__init__()
