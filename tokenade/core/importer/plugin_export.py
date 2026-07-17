"""
Plugin-First Export — automatically use site handler plugins when available.

When exporting for a site, checks if a handler plugin exists.
If yes, uses the plugin for full ecosystem extraction.
If no, falls back to default extraction.

Usage:
    exporter = PluginExporter()
    result = exporter.export(
        browser_name="brave",
        domains=["google.com", "mail.google.com"],
        output_file="gmail.tokenade",
    )
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _site_handler_metadata(handler: Any, *, auto_discovered: bool = True) -> Dict[str, Any]:
    """Build reproducible export lineage metadata for a Site Handler."""
    plugin_name = getattr(handler, "name", None) or type(handler).__name__
    metadata = {
        "plugin_name": plugin_name,
        "plugin_version": getattr(handler, "version", None) or "unknown",
        "handler_name": getattr(handler, "name", None) or plugin_name,
        "handler_class": type(handler).__name__,
        "auto_discovered": bool(auto_discovered),
    }
    try:
        metadata["export_domains"] = list(handler.get_export_domains() or [])
    except Exception:
        metadata["export_domains"] = []
    try:
        metadata["storage_origins"] = list(handler.get_storage_origins() or [])
    except Exception:
        metadata["storage_origins"] = []
    return metadata


class PluginExporter:
    """Export sessions using site handler plugins when available."""

    def __init__(self):
        self._handlers = {}

    def _load_handlers(self):
        """Load all site handler plugins."""
        if self._handlers:
            return
        try:
            from tokenade.core.integration.plugin_loader import PluginLoader
            loader = PluginLoader()
            loader.load_all()
            handlers = loader.list_handlers()
            for name, handler in handlers.items():
                self._handlers[name] = handler
        except Exception as e:
            logger.debug(f"Failed to load handler plugins: {e}")

    def find_handler(self, domains: List[str]) -> Optional[Any]:
        """Find a site handler plugin for the given domains.

        Prefers specific site handlers over catch-all ``generic-handler``
        (generic always returns True from can_handle and must not win by default).

        Args:
            domains: List of domains to match (e.g., ["google.com", "mail.google.com"])

        Returns:
            Handler plugin instance or None
        """
        self._load_handlers()

        specific: List[Any] = []
        generic: List[Any] = []

        for domain in domains:
            if not domain:
                continue
            host = str(domain).lstrip(".")
            url = f"https://{host}" if "://" not in host else host
            for name, handler in self._handlers.items():
                try:
                    if not handler.can_handle(url):
                        continue
                except Exception:
                    continue
                hname = (getattr(handler, "name", None) or name or "").lower()
                if hname in ("generic-handler", "generic") or name.lower() in (
                    "generic-handler",
                    "generic",
                ):
                    generic.append(handler)
                else:
                    specific.append(handler)

        if specific:
            # Prefer google-handler / github-handler style names that match domains
            domain_blob = " ".join(str(d).lower() for d in domains)
            for handler in specific:
                hname = (getattr(handler, "name", "") or "").lower()
                site_key = hname.replace("-handler", "").replace("_handler", "")
                if site_key and site_key in domain_blob:
                    logger.info(f"Found handler: {hname} for {domains}")
                    return handler
            chosen = specific[0]
            logger.info(
                f"Found handler: {getattr(chosen, 'name', type(chosen).__name__)} for {domains}"
            )
            return chosen

        if generic:
            chosen = generic[0]
            logger.info(
                f"Found handler: {getattr(chosen, 'name', 'generic')} for {domains}"
            )
            return chosen

        return None

    def get_handler(self, name: str) -> Optional[Any]:
        """Get a loaded site handler by plugin name (loads plugins if needed)."""
        self._load_handlers()
        if name in self._handlers:
            return self._handlers[name]
        # Also match by instance.name
        for key, handler in self._handlers.items():
            if getattr(handler, "name", None) == name or key == name:
                return handler
        return None

    def export(
        self,
        browser_name: str,
        domains: List[str],
        output_file: str,
        use_plugin: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """Export session, using plugin if available.

        Args:
            browser_name: Source browser name
            domains: Domains to filter
            output_file: Output .tokenade file path
            use_plugin: Whether to try plugin first
            **kwargs: Additional options

        Returns:
            Dict with success, method (plugin/default), file path, stats
        """
        # Try plugin first
        if use_plugin:
            handler = self.find_handler(domains)
            if handler:
                return self._export_with_plugin(
                    handler, browser_name, domains, output_file, **kwargs
                )

        # Fallback to default
        return self._export_default(browser_name, domains, output_file, **kwargs)

    def _export_with_plugin(
        self,
        handler: Any,
        browser_name: str,
        domains: List[str],
        output_file: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """Export using a site handler plugin."""
        try:
            from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery
            from tokenade.core.importer.cookie_extractor import CookieExtractor
            from tokenade.core.importer.local_storage_extractor import LocalStorageExtractor

            # Discover browser profile
            discovery = BrowserProfileDiscovery()
            profiles = discovery.discover_all()
            browser_path = None
            for browser, browser_profiles in profiles.items():
                if browser == browser_name:
                    if browser_profiles:
                        browser_path = str(browser_profiles[0].path)
                        break

            if not browser_path:
                return {
                    "success": False,
                    "method": "plugin",
                    "error": f"No {browser_name} profile found",
                }

            # Use handler to extract
            from playwright.sync_api import sync_playwright
            pw = sync_playwright().start()
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context()

            # Load cookies into context
            extractor = CookieExtractor(browser_path, browser=browser_name)
            all_cookies = extractor.extract()
            filtered_cookies = self._filter_cookies(all_cookies, domains)
            context.add_cookies(filtered_cookies)

            # Site handlers declare the browser origins whose localStorage is
            # part of their session. Keep this site-specific instead of
            # guessing from the first cookie domain.
            storage_origins = list(getattr(handler, "get_storage_origins", lambda: [])() or [])
            storage = {"local": {}, "session": {}}
            if storage_origins:
                storage_extractor = LocalStorageExtractor(browser_path, browser=browser_name)
                for origin in storage_origins:
                    entries = storage_extractor.extract(origin_filter=origin)
                    if entries:
                        storage["local"][origin] = entries

                for origin, entries in storage["local"].items():
                    page = context.new_page()
                    page.goto(origin, wait_until="domcontentloaded")
                    page.evaluate(
                        "([items]) => Object.entries(items).forEach(([key, value]) => "
                        "localStorage.setItem(key, value))",
                        [entries],
                    )

            # Use handler to extract session
            url = f"https://{domains[0]}"
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded")
            result = handler.extract_session(context, url)

            # Handle PluginResult or dict (backward compat)
            if hasattr(result, 'success'):
                if not result.success:
                    browser.close()
                    pw.stop()
                    return {
                        "success": False,
                        "method": "plugin",
                        "handler": handler.name,
                        "error": result.error or "Handler extraction failed",
                    }
                session = result.data
            else:
                session = result

            # Save
            from tokenade.core.importer.session_packager import SessionPackager
            packager = SessionPackager()
            package = packager.package(
                cookies=session.get("cookies", []),
                browser=browser_name,
                profile=browser_path,
                storage=session.get("storage") or storage,
                local_storage=session.get("local_storage"),
                metadata={
                    "extraction_method": "site_handler",
                    "site_handler": _site_handler_metadata(handler),
                },
            )
            packager.save(package, output_file)

            browser.close()
            pw.stop()

            # Validate
            validation = handler.validate(session) if hasattr(handler, "validate") else {}

            return {
                "success": True,
                "method": "plugin",
                "handler": handler.name,
                "file": output_file,
                "cookies": len(session.get("cookies", [])),
                "validation": validation,
            }

        except Exception as e:
            logger.error(f"Plugin export failed: {e}")
            # Fallback to default
            return self._export_default(browser_name, domains, output_file)

    @staticmethod
    def _filter_cookies(cookies: List[Dict[str, Any]], domains: List[str]) -> List[Dict[str, Any]]:
        """Keep cookies matching the requested domains and their subdomains."""
        filtered = []
        normalized = [str(domain).lstrip(".").lower() for domain in domains if domain]
        for cookie in cookies:
            host = str(cookie.get("domain", "")).lstrip(".").lower()
            if any(host == domain or host.endswith("." + domain) for domain in normalized):
                filtered.append(cookie)
        return filtered

    def _export_default(
        self,
        browser_name: str,
        domains: List[str],
        output_file: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """Export using default extraction."""
        try:
            from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery
            from tokenade.core.importer.cookie_extractor import CookieExtractor
            from tokenade.core.importer.session_packager import SessionPackager

            # Discover browser profile
            discovery = BrowserProfileDiscovery()
            profiles = discovery.discover_all()
            browser_path = None
            for browser, browser_profiles in profiles.items():
                if browser == browser_name:
                    if browser_profiles:
                        browser_path = str(browser_profiles[0].path)
                        break

            if not browser_path:
                return {
                    "success": False,
                    "method": "default",
                    "error": f"No {browser_name} profile found",
                }

            # Extract cookies
            extractor = CookieExtractor(browser_path, browser=browser_name)
            cookies = extractor.extract()

            # Filter by domains
            filtered = []
            for c in cookies:
                domain = c.get("domain", "")
                for d in domains:
                    if d.startswith("."):
                        if domain.endswith(d) or domain == d[1:]:
                            filtered.append(c)
                            break
                    else:
                        if domain == d or domain.endswith("." + d):
                            filtered.append(c)
                            break

            # Package and save
            packager = SessionPackager()
            package = packager.package(
                cookies=filtered,
                browser=browser_name,
                profile=browser_path,
            )
            packager.save(package, output_file)

            return {
                "success": True,
                "method": "default",
                "file": output_file,
                "cookies": len(filtered),
            }

        except Exception as e:
            return {
                "success": False,
                "method": "default",
                "error": str(e),
            }

    def list_handlers(self) -> List[Dict[str, str]]:
        """List available site handler plugins."""
        self._load_handlers()
        return [
            {
                "name": name,
                "description": getattr(h, "description", ""),
                "version": getattr(h, "version", "?"),
            }
            for name, h in self._handlers.items()
        ]
