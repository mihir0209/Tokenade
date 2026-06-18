"""
TLS/JA3 Fingerprint Matching Engine.

Uses curl-cffi to make HTTP requests with matching TLS fingerprints,
bypassing Cloudflare and other anti-bot services that check JA3/JA4.
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class TLSFingerprint:
    """TLS fingerprint configuration."""
    browser: str = "chrome"
    version: str = "120"
    platform: str = "windows"
    impersonate: str = "chrome120"


# Browser version to curl-cffi impersonation target mapping
IMPERSONATE_TARGETS = {
    # Chrome versions
    "chrome107": "chrome107",
    "chrome110": "chrome110",
    "chrome116": "chrome116",
    "chrome119": "chrome119",
    "chrome120": "chrome120",
    "chrome123": "chrome123",
    "chrome124": "chrome124",
    "chrome131": "chrome131",

    # Firefox versions
    "firefox109": "firefox109",
    "firefox117": "firefox117",
    "firefox119": "firefox119",
    "firefox120": "firefox120",
    "firefox128": "firefox128",

    # Safari versions
    "safari15_3": "safari15_3",
    "safari15_5": "safari15_5",
    "safari17_0": "safari17_0",
    "safari17_2_1": "safari17_2_1",

    # Edge versions
    "edge101": "edge101",
    "edge118": "edge118",
    "edge120": "edge120",
    "edge131": "edge131",
}

# Browser name to default impersonation mapping
BROWSER_DEFAULTS = {
    "chrome": "chrome120",
    "firefox": "firefox120",
    "safari": "safari17_0",
    "edge": "edge120",
    "brave": "chrome120",  # Brave uses Chromium
    "opera": "chrome120",  # Opera uses Chromium
}


class TLSMatcher:
    """
    TLS fingerprint matcher using curl-cffi.

    Makes HTTP requests with matching TLS fingerprints to bypass
    Cloudflare and other anti-bot protections.

    Usage:
        matcher = TLSMatcher()
        response = matcher.get("https://chatgpt.com/backend-api/models")
    """

    def __init__(self, fingerprint: Optional[TLSFingerprint] = None):
        self.fingerprint = fingerprint or TLSFingerprint()
        self._session = None
        self._setup_session()

    def _setup_session(self) -> None:
        """Setup curl-cffi session with impersonation."""
        try:
            from curl_cffi import requests as curl_requests

            # Try the requested impersonation first
            try:
                self._session = curl_requests.Session(
                    impersonate=self.fingerprint.impersonate
                )
                logger.debug(f"TLSMatcher initialized with impersonation: {self.fingerprint.impersonate}")
            except Exception as e:
                # Firefox impersonation may not be supported, fallback to Chrome
                if "firefox" in self.fingerprint.impersonate.lower():
                    logger.warning(f"Firefox impersonation not supported, falling back to Chrome: {e}")
                    self._session = curl_requests.Session(impersonate="chrome120")
                    self.fingerprint.impersonate = "chrome120"
                else:
                    raise

        except ImportError:
            logger.warning("curl-cffi not installed. TLS fingerprint matching disabled.")
            self._session = None

    def _get_impersonate_target(self, browser: str, version: str) -> str:
        """Get the impersonation target for a browser version."""
        key = f"{browser}{version}"
        if key in IMPERSONATE_TARGETS:
            return IMPERSONATE_TARGETS[key]

        # Fallback to browser default
        return BROWSER_DEFAULTS.get(browser, "chrome120")

    def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict] = None,
        cookies: Optional[Dict] = None,
        data: Optional[Any] = None,
        json_data: Optional[Dict] = None,
        timeout: int = 30,
        **kwargs
    ) -> Any:
        """
        Make a TLS fingerprint-matched HTTP request.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Target URL
            headers: Additional headers
            cookies: Cookie dictionary
            data: Form data
            json_data: JSON payload
            timeout: Request timeout in seconds

        Returns:
            Response object
        """
        if not self._session:
            raise RuntimeError(
                "curl-cffi not installed. Install with: pip install curl-cffi"
            )

        logger.debug(f"TLS Request: {method} {url}")

        response = self._session.request(
            method=method,
            url=url,
            headers=headers or {},
            cookies=cookies or {},
            data=data,
            json=json_data,
            timeout=timeout,
            **kwargs
        )

        logger.debug(f"TLS Response: {response.status_code} {len(response.content)} bytes")
        return response

    def get(
        self,
        url: str,
        headers: Optional[Dict] = None,
        cookies: Optional[Dict] = None,
        timeout: int = 30,
        **kwargs
    ) -> Any:
        """GET request with TLS fingerprint matching."""
        return self.request("GET", url, headers, cookies, timeout=timeout, **kwargs)

    def post(
        self,
        url: str,
        headers: Optional[Dict] = None,
        cookies: Optional[Dict] = None,
        data: Optional[Any] = None,
        json_data: Optional[Dict] = None,
        timeout: int = 30,
        **kwargs
    ) -> Any:
        """POST request with TLS fingerprint matching."""
        return self.request("POST", url, headers, cookies, data, json_data, timeout=timeout, **kwargs)

    def put(
        self,
        url: str,
        headers: Optional[Dict] = None,
        cookies: Optional[Dict] = None,
        data: Optional[Any] = None,
        json_data: Optional[Dict] = None,
        timeout: int = 30,
        **kwargs
    ) -> Any:
        """PUT request with TLS fingerprint matching."""
        return self.request("PUT", url, headers, cookies, data, json_data, timeout=timeout, **kwargs)

    def delete(
        self,
        url: str,
        headers: Optional[Dict] = None,
        cookies: Optional[Dict] = None,
        timeout: int = 30,
        **kwargs
    ) -> Any:
        """DELETE request with TLS fingerprint matching."""
        return self.request("DELETE", url, headers, cookies, timeout=timeout, **kwargs)

    def close(self) -> None:
        """Close the session."""
        if self._session:
            self._session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def create_tls_matcher(
    browser: str = "chrome",
    version: str = "120",
    impersonate: Optional[str] = None
) -> TLSMatcher:
    """
    Create a TLS matcher for a specific browser.

    Args:
        browser: Browser name (chrome, firefox, safari, edge, brave, opera)
        version: Browser version
        impersonate: Specific impersonation target (overrides browser/version)

    Returns:
        Configured TLSMatcher
    """
    if impersonate:
        target = impersonate
    else:
        target = BROWSER_DEFAULTS.get(browser, "chrome120")

    fingerprint = TLSFingerprint(
        browser=browser,
        version=version,
        impersonate=target
    )

    return TLSMatcher(fingerprint)
