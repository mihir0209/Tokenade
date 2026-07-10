"""
Example: Custom Site Handler Plugin

Site metadata (domains, critical cookies, URLs) lives in site_config.json
next to plugin.json — the SiteHandlerPlugin base class loads it automatically.

Layout:
    my_site_handler/
    ├── plugin.json
    ├── site_config.json   # required for product sites
    └── plugin.py

Install:
    cp -r my_site_handler ~/.tokenade/plugins/my-site-handler
    tokenade plugin list
    tokenade export --browser-name firefox --plugin my-site-handler -o example.tokenade
"""

import logging
from typing import Any

from tokenade.plugin import SiteHandlerPlugin, PluginResult

logger = logging.getLogger(__name__)


class MySiteHandlerPlugin(SiteHandlerPlugin):
    """ExampleSite handler — domains/cookies from site_config.json."""

    name = "my-site-handler"
    version = "1.1.0"
    description = "Example: Custom handler for ExampleSite"
    author = "MiHiR"
    API_VERSION = "1.1.0"

    def extract_session(self, browser_context: Any, url: str) -> PluginResult:
        logger.info("Extracting session from %s (domains=%s)", url, self.get_export_domains())
        # Real plugins: navigate, wait, browser_context.cookies(), filter by domains
        return PluginResult(
            success=True,
            data={
                "cookies": [],
                "storage": {},
                "site_name": self.get_site_config().get("name", "example-site"),
            },
        )

    def inject_session(self, browser_context: Any, session: dict) -> PluginResult:
        cookies = session.get("cookies") or []
        logger.info("Would inject %d cookies for %s", len(cookies), session.get("site_name"))
        return PluginResult(success=True, data={"injected_count": len(cookies)})
