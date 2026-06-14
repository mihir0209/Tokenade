"""
CDP artifact removal.

Removes Playwright/Puppeteer detection artifacts from the browser context.
"""

import logging
from typing import List

logger = logging.getLogger(__name__)


class CDPCleaner:
    """Remove CDP detection artifacts."""

    # Scripts to inject on every page
    STEALTH_SCRIPTS: List[str] = [
        # Remove window.cdc_* artifacts
        """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        """,
        # Override navigator.webdriver
        """
        if (window.navigator.webdriver) {
            Object.defineProperty(window.navigator, 'webdriver', {
                get: () => false
            });
        }
        """,
        # Remove Chrome DevTools Protocol artifacts
        """
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
        """,
        # Fix navigator.plugins length
        """
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
        """,
        # Fix navigator.languages
        """
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });
        """,
    ]

    @classmethod
    def get_stealth_scripts(cls) -> List[str]:
        """Return list of JavaScript stealth scripts to inject."""
        return cls.STEALTH_SCRIPTS

    @classmethod
    def get_init_script(cls) -> str:
        """Return combined init script for Playwright page.add_init_script()."""
        return "\n".join(cls.STEALTH_SCRIPTS)
