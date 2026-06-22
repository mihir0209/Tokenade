"""
Example: Custom Site Handler Plugin

This plugin demonstrates how to create a site handler plugin
for a website that needs custom extraction/login logic.

Use cases:
- Sites with complex login flows (2FA, CAPTCHA)
- Sites that use non-standard cookie storage
- Sites that need JavaScript execution before extraction

To use this plugin:
1. Copy the my_site_handler/ directory to ~/.tokenade/plugins/
2. Run: tokenade plugin list
3. Run: tokenade extract --url https://example.com --plugin my-site-handler
"""

import logging
from typing import Any

from tokenade.plugin import SiteHandlerPlugin

logger = logging.getLogger(__name__)


class MySiteHandlerPlugin(SiteHandlerPlugin):
    """Handle session extraction for ExampleSite.

    This example shows:
    - How to check if a URL belongs to your site
    - How to extract session data from a browser context
    - How to inject session data into a browser
    """

    name = "my-site-handler"
    version = "1.0.0"
    description = "Example: Custom handler for ExampleSite"
    author = "Tokenade Examples"

    def can_handle(self, url: str) -> bool:
        """Check if this plugin handles the given URL."""
        return "example.com" in url or "www.example.com" in url

    def extract_session(self, browser_context: Any, url: str) -> dict:
        """Extract session data from a browser context.

        Args:
            browser_context: Playwright BrowserContext or CDP connection
            url: The URL to extract from

        Returns:
            Session dict with cookies, localStorage, etc.
        """
        logger.info(f"Extracting session from {url}")

        # In a real plugin, you would:
        # 1. Navigate to the URL
        # 2. Wait for the page to load
        # 3. Extract cookies via browser API
        # 4. Extract localStorage via JavaScript
        # 5. Extract any tokens from the page

        session = {
            "version": "2.0",
            "site_name": "example-site",
            "cookies": [],
            "local_storage": {},
            "session_storage": {},
            "metadata": {
                "extractor": "my-site-handler",
            },
        }

        # Example: extract cookies
        # cookies = browser_context.cookies()
        # session["cookies"] = cookies

        # Example: extract localStorage
        # local_storage = browser_context.evaluate("() => { ... }")
        # session["local_storage"] = local_storage

        return session

    def inject_session(self, browser_context: Any, session: dict) -> bool:
        """Inject session data into a browser context.

        Args:
            browser_context: Playwright BrowserContext or CDP connection
            session: Session data to inject

        Returns:
            True if injection was successful
        """
        logger.info(f"Injecting session for {session.get('site_name', 'unknown')}")

        # In a real plugin, you would:
        # 1. Add cookies to the browser context
        # 2. Set localStorage values via JavaScript
        # 3. Navigate to the site to verify the session works

        cookies = session.get("cookies", [])
        if cookies:
            # Example: inject cookies
            # browser_context.add_cookies(cookies)
            logger.info(f"Would inject {len(cookies)} cookies")

        local_storage = session.get("local_storage", {})
        if local_storage:
            # Example: inject localStorage
            # for key, value in local_storage.items():
            #     browser_context.evaluate(f"localStorage.setItem('{key}', '{value}')")
            logger.info(f"Would inject {len(local_storage)} localStorage items")

        return True
