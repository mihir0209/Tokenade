"""
Abstract base classes for Tokenade plugins (API v1.3).

All plugins must subclass PluginBase and implement the required methods.
Plugin types add specific capabilities on top of the base.

Plugin layout (site handlers):
    my-handler/
    ├── plugin.json       # manifest (required)
    ├── plugin.py         # entry class (required)
    └── site_config.json  # domains, critical cookies, URLs (site handlers)

Plugin Manifest (plugin.json):
{
    "name": "my-plugin",
    "version": "1.0.0",
    "api_version": "1.0.0",
    "description": "Does something useful",
    "author": "Your Name",
    "type": "session_refresh",
    "entry_point": "plugin.py",
    "entry_class": "MyPlugin",
    "dependencies": []
}
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from tokenade.plugin.api import API_VERSION, PluginResult, PluginConfig


class PluginBase(ABC):
    """Base class for all Tokenade plugins (API v1.3).

    Every plugin MUST:
    - Subclass PluginBase (or a subclass of it)
    - Set API_VERSION = "1.3.0"
    - Set name, version, description

    Lifecycle hooks:
    - on_load(): Called when plugin is loaded
    - on_configure(config): Called with PluginConfig after load
    - on_unload(): Called when plugin is unloaded

    All methods should return PluginResult for consistent error handling.
    """

    API_VERSION: str = API_VERSION
    name: str = ""
    version: str = "0.0.0"
    description: str = ""
    author: str = ""
    dependencies: List[str] = []

    def __init__(self):
        self._config: Optional[PluginConfig] = None
        self._plugin_dir: Optional[Path] = None

    def set_plugin_dir(self, path: Union[str, Path]) -> None:
        """Bind plugin install directory (called by PluginLoader)."""
        self._plugin_dir = Path(path)

    @property
    def plugin_dir(self) -> Optional[Path]:
        """Directory containing plugin.json (if set by loader)."""
        return self._plugin_dir

    def on_load(self) -> None:
        """Called when the plugin is loaded. Override for initialization."""

    def on_unload(self) -> None:
        """Called when the plugin is unloaded. Override for cleanup."""

    def on_configure(self, config: PluginConfig) -> None:
        """Called with PluginConfig after load. Override to validate config."""
        self._config = config

    def get_info(self) -> Dict[str, Any]:
        """Return plugin metadata."""
        return {
            "name": self.name,
            "version": self.version,
            "api_version": self.API_VERSION,
            "description": self.description,
            "author": self.author,
            "dependencies": self.dependencies,
        }

    def get_metadata(self):
        """Return PluginMetadata object."""
        from tokenade.plugin.api import PluginMetadata
        return PluginMetadata(
            name=self.name,
            version=self.version,
            api_version=self.API_VERSION,
            author=self.author,
            description=self.description,
            dependencies=self.dependencies,
        )

    def health_check(self) -> bool:
        """Check if the plugin is healthy. Override for custom checks."""
        return True


class SessionRefreshPlugin(PluginBase):
    """Plugin that can refresh sessions (OAuth2, API tokens, etc.).

    Implement can_refresh() to declare which sessions this plugin handles,
    and refresh() to perform the actual refresh.

    Example:
        class GoogleOAuth2Plugin(SessionRefreshPlugin):
            name = "google-oauth2"
            version = "1.0.0"
            description = "Refresh Google sessions via OAuth2"

            def can_refresh(self, session):
                return any(c.get("domain", "").endswith(".google.com")
                          for c in session.get("cookies", []))

            def refresh(self, session, credentials):
                # Use refresh_token to get new access_token
                return PluginResult(success=True, data={"session": session})
    """

    @abstractmethod
    def can_refresh(self, session: dict) -> bool:
        """Check if this plugin can refresh the given session.

        Args:
            session: The .tokenade session data (cookies, metadata, etc.)

        Returns:
            True if this plugin can handle the session
        """

    @abstractmethod
    def refresh(self, session: dict, credentials: dict) -> PluginResult:
        """Refresh the session.

        Args:
            session: Current session data
            credentials: Plugin-specific credentials

        Returns:
            PluginResult with data={"session": updated_session}
        """

    def get_credentials_args(self) -> List[Dict[str, str]]:
        """Define CLI arguments needed for credentials.

        Returns:
            List of dicts with keys: name, help, required, type
        """
        return []


class SiteHandlerPlugin(PluginBase):
    """Plugin that handles a specific website's extraction/injection.

    **Site config (Sprint 0):** place ``site_config.json`` next to ``plugin.json``.
    The base class loads it on ``set_plugin_dir()`` / ``on_load()`` and uses it as
    the default source for domains, critical cookies, and URLs.

    Plugin layout::

        google-handler/
        ├── plugin.json
        ├── plugin.py
        └── site_config.json   # required for product sites

    Implement extract_session() / inject_session(). Override getters only when
    you need logic beyond the JSON file. can_handle() defaults to domain match
    against get_export_domains().

    Example site_config.json::

        {
          "name": "google",
          "domains": ["google.com", "accounts.google.com", "mail.google.com"],
          "critical_cookies": ["SID", "HSID", "__Secure-1PSID"],
          "login_url": "https://accounts.google.com/signin",
          "dashboard_url": "https://mail.google.com",
          "wait_seconds": 5
        }
    """

    def __init__(self):
        super().__init__()
        self._site_config: Dict[str, Any] = {}

    def set_plugin_dir(self, path: Union[str, Path]) -> None:
        """Bind plugin directory and load site_config.json if present."""
        super().set_plugin_dir(path)
        self._load_site_config_file()

    def on_load(self) -> None:
        """Ensure site_config.json is loaded when the plugin is activated."""
        if not getattr(self, "_site_config", None) and self._plugin_dir:
            self._load_site_config_file()

    def _load_site_config_file(self) -> None:
        """Load site_config.json from the plugin root into ``_site_config``."""
        if not self._plugin_dir:
            return
        path = self._plugin_dir / "site_config.json"
        if not path.is_file():
            return
        try:
            from tokenade.core.importer.site_configs import load_site_config_file

            self._site_config = load_site_config_file(
                path, plugin_name=self.name or ""
            )
        except Exception:
            import json

            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._site_config = raw
            except (OSError, json.JSONDecodeError):
                self._site_config = {}

    def get_site_config(self) -> Dict[str, Any]:
        """Return the loaded site config (from site_config.json + overrides).

        Core and CLI call this (via site_configs.get_site_config) to resolve
        domains, health cookies, and URLs for a site.
        """
        if not hasattr(self, "_site_config"):
            self._site_config = {}
        if not self._site_config and getattr(self, "_plugin_dir", None):
            self._load_site_config_file()
        return dict(self._site_config)

    def can_handle(self, url: str) -> bool:
        """True if URL matches any export domain from site_config.json.

        Override for non-domain matching (path prefixes, multi-tenant hosts).
        """
        url_lower = (url or "").lower()
        if not url_lower:
            return False
        for domain in self.get_export_domains():
            clean = str(domain).lstrip(".").lower()
            if clean and clean in url_lower:
                return True
        return False

    @abstractmethod
    def extract_session(self, _browser_context: Any, url: str) -> PluginResult:
        """Extract session data from a browser context.

        Args:
            browser_context: The browser context (Playwright or CDP)
            url: The target URL

        Returns:
            PluginResult with data={"cookies": [...], "storage": {...}}
        """

    @abstractmethod
    def inject_session(self, _browser_context: Any, session: dict) -> PluginResult:
        """Inject session data into a browser context.

        Args:
            browser_context: The browser context
            session: Session data to inject

        Returns:
            PluginResult with data={"injected_count": N}
        """

    def validate(self, session: dict) -> PluginResult:
        """Validate a session for this site.

        Args:
            session: Session data to validate

        Returns:
            PluginResult with data={"valid": bool, "score": float, "issues": [...]}
        """
        return PluginResult(
            success=True,
            data={"valid": True, "score": 100.0, "issues": []},
        )

    # ── Export Specification (API v1.1) — defaults from site_config.json ──

    def get_export_domains(self) -> List[str]:
        """Domains to export cookies for (from site_config.json ``domains``)."""
        cfg = self.get_site_config()
        domains = cfg.get("domains") or []
        return list(domains) if isinstance(domains, list) else []

    def get_critical_cookies(self) -> List[str]:
        """Critical cookie names (from site_config.json ``critical_cookies``)."""
        cfg = self.get_site_config()
        cookies = cfg.get("critical_cookies") or []
        return list(cookies) if isinstance(cookies, list) else []

    def get_critical_storage(self) -> Dict[str, Dict[str, List[str]]]:
        """Critical localStorage/sessionStorage keys from site_config.json."""
        cfg = self.get_site_config()
        storage = cfg.get("critical_storage")
        if isinstance(storage, dict):
            return storage
        return {"local": {}, "session": {}}

    # ── Login Verification (API v1.1) — defaults from site_config.json ──

    def get_login_url(self) -> str:
        """Login URL from site_config.json ``login_url``."""
        return str(self.get_site_config().get("login_url") or "")

    def get_dashboard_url(self) -> str:
        """Dashboard URL from site_config.json ``dashboard_url`` or ``validate_url``."""
        cfg = self.get_site_config()
        return str(cfg.get("dashboard_url") or cfg.get("validate_url") or "")

    def get_session_check_url(self) -> str:
        """Fast session-check API URL from site_config.json."""
        return str(self.get_site_config().get("session_check_url") or "")

    def get_logged_in_selectors(self) -> List[str]:
        """CSS selectors for logged-in state from site_config.json."""
        cfg = self.get_site_config()
        sels = cfg.get("logged_in_selectors") or []
        return list(sels) if isinstance(sels, list) else []

    def get_logged_out_selectors(self) -> List[str]:
        """CSS selectors for logged-out state from site_config.json."""
        cfg = self.get_site_config()
        sels = cfg.get("logged_out_selectors") or []
        if isinstance(sels, list) and sels:
            return list(sels)
        indicator = cfg.get("login_indicator_css")
        if isinstance(indicator, str) and indicator:
            return [indicator]
        return []

    def get_storage_origins(self) -> List[str]:
        """Return browser origins whose localStorage belongs in an export.

        Handlers for sites that keep authentication outside cookies should
        override this. The exporter preserves these origins in the session
        package instead of inferring one from an unrelated cookie domain.
        """
        return []

    def export_profile_data(self, profile_path: str, browser: str) -> PluginResult:
        """Export site-specific browser profile data not covered by Web Storage."""
        return PluginResult(success=True, data={})

    def restore_profile_data(
        self,
        session: dict,
        profile_path: str,
        browser: str,
    ) -> PluginResult:
        """Restore site-specific profile data before the target browser starts."""
        return PluginResult(success=True, data={})

    def validate_launch_requirements(self, session: dict, browser: str) -> PluginResult:
        """Validate site-specific prerequisites before the browser is started."""
        return PluginResult(success=True, data={})

    def verify_login(self, browser_context: Any) -> PluginResult:
        """Verify if the browser is logged into this site.

        Default implementation:
        1. Navigate to dashboard_url
        2. Check for logged_in_selectors
        3. Check for logged_out_selectors
        4. Return PluginResult with data={"logged_in": bool, "method": str}

        Override for custom verification (e.g., API endpoint check).

        Args:
            browser_context: The browser context

        Returns:
            PluginResult with data={"logged_in": bool, "method": str, "details": str}
        """
        dashboard_url = self.get_dashboard_url()
        if not dashboard_url:
            return PluginResult(
                success=True,
                data={"logged_in": False, "method": "none", "details": "No dashboard URL"},
            )

        logged_in_selectors = self.get_logged_in_selectors()
        logged_out_selectors = self.get_logged_out_selectors()

        try:
            page = browser_context.new_page()
            page.goto(dashboard_url, timeout=15000)
            page.wait_for_load_state("networkidle", timeout=10000)

            # Check for logged-in indicators
            for selector in logged_in_selectors:
                try:
                    element = page.query_selector(selector)
                    if element:
                        page.close()
                        return PluginResult(
                            success=True,
                            data={"logged_in": True, "method": "selector", "details": selector},
                        )
                except Exception:
                    continue

            # Check for logged-out indicators
            for selector in logged_out_selectors:
                try:
                    element = page.query_selector(selector)
                    if element:
                        page.close()
                        return PluginResult(
                            success=True,
                            data={"logged_in": False, "method": "selector", "details": selector},
                        )
                except Exception:
                    continue

            page.close()
            return PluginResult(
                success=True,
                data={"logged_in": False, "method": "unknown", "details": "No matching selectors"},
            )

        except Exception as e:
            return PluginResult(
                success=False,
                error=f"Login verification failed: {e}",
                data={"logged_in": False, "method": "error"},
            )


class ExportFormatPlugin(PluginBase):
    """Plugin that adds a custom export format."""

    @abstractmethod
    def get_format_name(self) -> str:
        """Return the format name (e.g., 'curl', 'python-requests')."""

    @abstractmethod
    def export(self, session: dict, output_path: str) -> str:
        """Export session in the custom format.

        Args:
            session: Session data
            output_path: Where to write the output

        Returns:
            Path to the exported file
        """


class SessionValidatorPlugin(PluginBase):
    """Plugin that validates session health with custom rules."""

    @abstractmethod
    def validate(self, session: dict) -> PluginResult:
        """Validate a session.

        Args:
            session: Session data to validate

        Returns:
            Dict with keys: valid (bool), score (float 0-100), issues (list of str)
        """


class StealthPlugin(PluginBase):
    """Plugin that provides browser stealth patches.

    Implement get_patches() to return JavaScript injection scripts
    that bypass bot detection systems.

    Example:
        class BasicStealthPlugin(StealthPlugin):
            name = "stealth-basic"
            version = "1.0.0"
            description = "Basic stealth patches"

            def get_patches(self):
                return ["navigator.webdriver = undefined"]
    """

    @abstractmethod
    def get_patches(self) -> List[str]:
        """Return list of JavaScript patches to inject.

        Returns:
            List of JavaScript strings to inject into pages
        """

    def get_tls_config(self) -> Optional[Dict[str, Any]]:
        """Return TLS fingerprint configuration (optional).

        Returns:
            Dict with keys: impersonate, ciphers, extensions, or None
        """
        return None

    def get_browser_args(self) -> List[str]:
        """Return additional browser launch arguments (optional).

        Returns:
            List of Chrome/Firefox command-line arguments
        """
        return []


class CaptchaPlugin(PluginBase):
    """Plugin that solves CAPTCHAs.

    Implement solve() to solve a specific CAPTCHA type.

    Example:
        class TwoCaptchaPlugin(CaptchaPlugin):
            name = "captcha-2captcha"
            version = "1.0.0"
            description = "2Captcha integration"

            def get_supported_types(self):
                return ["recaptcha_v2", "hcaptcha", "turnstile"]

            def solve(self, captcha_type, site_key, page_url):
                # Call 2Captcha API
                return {"success": True, "token": "..."}
    """

    @abstractmethod
    def get_supported_types(self) -> List[str]:
        """Return list of supported CAPTCHA types.

        Returns:
            List of CAPTCHA type strings (e.g., "recaptcha_v2", "hcaptcha", "turnstile")
        """

    @abstractmethod
    def solve(self, captcha_type: str, site_key: Optional[str] = None,
              _page_url: Optional[str] = None) -> Dict[str, Any]:
        """Solve a CAPTCHA.

        Args:
            captcha_type: Type of CAPTCHA (e.g., "recaptcha_v2")
            site_key: Site key from the CAPTCHA widget
            page_url: URL of the page with the CAPTCHA

        Returns:
            Dict with keys: success (bool), token (str), error (str, optional)
        """

    def get_balance(self) -> Optional[float]:
        """Get remaining balance for paid CAPTCHA services (optional).

        Returns:
            Balance amount or None if not applicable
        """


class ProxyProviderPlugin(PluginBase):
    """Plugin for commercial proxy providers (AnyIP, BrightData, etc.).

    Providers implement this to integrate their proxy service with Tokenade.
    Users install via: tokenade plugin install anyip-proxy

    Example:
        class AnyIPProxyPlugin(ProxyProviderPlugin):
            API_VERSION = "1.0.0"
            name = "anyip-proxy"
            version = "1.0.0"
            description = "AnyIP residential proxy"
            author = "AnyIP Inc."
            supports_sticky = True
            supports_rotation = True
            countries = ["US", "UK", "DE"]

            def get_proxy(self, options=None):
                return PluginResult(success=True, data={
                    "host": "proxy.anyip.io", "port": 1080,
                    "protocol": "http", "username": "user", "password": "pass"
                })

            def rotate(self, session_id=None):
                return PluginResult(success=True, data={
                    "host": "proxy2.anyip.io", "port": 1080,
                    "protocol": "http", "username": "user", "password": "pass"
                })
    """

    supports_sticky: bool = False
    supports_rotation: bool = False
    countries: List[str] = []
    website: str = ""

    @abstractmethod
    def get_proxy(self, options: Optional[Dict[str, Any]] = None) -> PluginResult:
        """Get a proxy (backward compatible).

        Args:
            options: Provider-specific options (country, session_id, etc.)

        Returns:
            PluginResult with data={"host", "port", "protocol", "username", "password"}
        """

    def get_sticky_proxy(self, session_id: str = None) -> PluginResult:
        """Get a sticky proxy (same IP for same session).

        Args:
            session_id: Session ID for sticky binding

        Returns:
            PluginResult with proxy config data
        """
        return self.get_proxy({"session_id": session_id, "mode": "sticky"})

    def get_rotating_proxy(self) -> PluginResult:
        """Get a rotating proxy (different IP per call).

        Returns:
            PluginResult with proxy config data
        """
        return self.get_proxy({"mode": "rotating"})

    @abstractmethod
    def rotate(self, session_id: Optional[str] = None) -> PluginResult:
        """Rotate to a new proxy.

        Args:
            session_id: Optional session ID for sticky rotation

        Returns:
            PluginResult with new proxy config
        """

    def check_health(self, proxy: Dict[str, Any]) -> PluginResult:
        """Check if a proxy is healthy.

        Args:
            proxy: Proxy config dict

        Returns:
            PluginResult with data={"healthy": bool, "latency_ms": float}
        """
        return PluginResult(success=True, data={"healthy": True, "latency_ms": 0})

    def get_provider_info(self) -> Dict[str, Any]:
        """Return provider information."""
        return {
            "provider": self.name,
            "website": self.website,
            "supports_sticky": self.supports_sticky,
            "supports_rotation": self.supports_rotation,
            "countries": self.countries,
        }


class ChallengeDetectorPlugin(PluginBase):
    """Plugin for automated Bot Protection & Challenge Detection (Cloudflare, Akamai, DataDome, etc.).

    Challenge detector plugins observe page state, response headers, DOM selectors,
    or CDP network traffic to identify whether a page is stuck behind a challenge,
    interstitial wall, or anti-bot gate.

    Example:
        class CloudflareTurnstileDetector(ChallengeDetectorPlugin):
            name = "cloudflare-turnstile-detector"
            version = "1.0.0"
            provider = "cloudflare"

            def detect_challenge(self, page_context: Any) -> PluginResult:
                # Inspect page HTML, status code, or DOM elements
                return PluginResult(success=True, data={"detected": True, "type": "turnstile"})
    """

    provider: str = "generic"

    @abstractmethod
    def detect_challenge(self, page_context: Any) -> PluginResult:
        """Inspect a browser page/context to detect challenge state.

        Args:
            page_context: Browser page or dict containing page metadata/DOM/headers

        Returns:
            PluginResult with data={
                "detected": bool,
                "provider": str,
                "challenge_type": str,  # "turnstile", "managed_challenge", "interstitial", "captcha", "waf_block"
                "confidence": float,     # 0.0 - 1.0
                "details": Dict[str, Any]
            }
        """

    def can_solve(self, challenge_type: str) -> bool:
        """Check if this plugin or its companion solver can handle the detected challenge."""
        return False

    def solve_challenge(self, page_context: Any, challenge_data: Dict[str, Any]) -> PluginResult:
        """Attempt to solve or bypass the detected challenge."""
        return PluginResult(success=False, error="Solving not implemented by this detector")


class NotificationPlugin(PluginBase):
    """Plugin for notification providers (Slack, Discord, Email, etc.).

    Providers implement this to send notifications on session events.

    Example:
        class SlackNotifyPlugin(NotificationPlugin):
            API_VERSION = "1.0.0"
            name = "slack-notify"
            version = "1.0.0"
            description = "Slack notifications"
            author = "MiHiR"

            def send(self, event, data):
                # Send Slack message
                return PluginResult(success=True)

            def get_supported_events(self):
                return ["session_expired", "refresh_failed", "refresh_success"]
    """

    @abstractmethod
    def send(self, event: str, data: Dict[str, Any]) -> PluginResult:
        """Send a notification.

        Args:
            event: Event type (session_expired, refresh_failed, etc.)
            data: Event data

        Returns:
            PluginResult
        """

    @abstractmethod
    def get_supported_events(self) -> List[str]:
        """Return list of supported event types."""
        return None
