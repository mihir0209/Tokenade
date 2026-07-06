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

        Args:
            domains: List of domains to match (e.g., ["google.com", "mail.google.com"])

        Returns:
            Handler plugin instance or None
        """
        self._load_handlers()

        for domain in domains:
            url = f"https://{domain}"
            for name, handler in self._handlers.items():
                try:
                    if handler.can_handle(url):
                        logger.info(f"Found handler: {name} for {domain}")
                        return handler
                except Exception:
                    continue

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
            context.add_cookies(all_cookies)

            # Use handler to extract session
            url = f"https://{domains[0]}"
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
                storage=session.get("storage"),
                local_storage=session.get("local_storage"),
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
