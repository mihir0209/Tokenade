"""
Custom Runtime Engine - Lightweight fingerprint-matched HTTP client.

Provides a browser-less way to use extracted sessions by creating HTTP
requests with matching fingerprints (headers, TLS, etc.).

Use cases:
- Server environments without browser support
- High-throughput API testing
- Cookie validity checks without browser overhead
- Background session monitoring

Features:
- Fingerprint-matched HTTP headers
- Cookie jar management
- TLS/JA3 fingerprint matching (via curl-impersonate or similar)
- Request/response logging
- Rate limiting
"""

import json
import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


@dataclass
class RuntimeConfig:
    """Configuration for the custom runtime engine."""
    fingerprint: Optional[Dict] = None
    cookies: List[Dict] = field(default_factory=list)
    tokens: List[Dict] = field(default_factory=list)
    user_agent: str = ""
    timeout: int = 30
    retries: int = 3
    backoff_factor: float = 0.5
    rate_limit: float = 0.0  # Seconds between requests
    verify_ssl: bool = True
    proxy: Optional[str] = None
    custom_headers: Dict[str, str] = field(default_factory=dict)


class FingerprintMatcher:
    """
    Matches HTTP requests to a browser fingerprint.

    Generates headers, TLS settings, and other parameters to make
    requests indistinguishable from the target browser.
    """

    # Common header orderings by browser
    CHROME_HEADERS = [
        "sec-ch-ua",
        "sec-ch-ua-mobile",
        "sec-ch-ua-platform",
        "upgrade-insecure-requests",
        "user-agent",
        "accept",
        "sec-fetch-site",
        "sec-fetch-mode",
        "sec-fetch-user",
        "sec-fetch-dest",
        "accept-encoding",
        "accept-language",
        "cookie",
    ]

    FIREFOX_HEADERS = [
        "user-agent",
        "accept",
        "accept-language",
        "accept-encoding",
        "referer",
        "connection",
        "upgrade-insecure-requests",
        "sec-fetch-dest",
        "sec-fetch-mode",
        "sec-fetch-site",
        "sec-fetch-user",
        "cookie",
    ]

    # Chrome sec-ch-ua values by version
    CHROME_UA_BRANDS = [
        '"Not_A Brand";v="99", "Google Chrome";v="109", "Chromium";v="109"',
        '"Not.A/Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        '"Google Chrome";v="119", "Chromium";v="119", "Not?A_Brand";v="24"',
    ]

    def __init__(self, fingerprint: Optional[Dict] = None):
        self.fingerprint = fingerprint or {}
        self.ua = self.fingerprint.get("user_agent", "")
        self.platform = self.fingerprint.get("platform", "Win32")
        self.language = self.fingerprint.get("language", "en-US")

    def get_headers(self, url: str, referer: Optional[str] = None) -> Dict[str, str]:
        """
        Generate fingerprint-matched headers for a request.

        Args:
            url: Target URL
            referer: Optional referer URL

        Returns:
            Dictionary of HTTP headers
        """
        headers = {}
        parsed = urlparse(url)
        is_secure = parsed.scheme == "https"

        # Determine browser type from UA
        if "Firefox" in self.ua:
            browser = "firefox"
        elif "Edg" in self.ua:
            browser = "edge"
        else:
            browser = "chrome"

        # User-Agent
        headers["user-agent"] = self.ua or self._default_ua()

        # Accept headers
        headers["accept"] = (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;"
            "q=0.8,application/signed-exchange;v=b3;q=0.7"
        )
        headers["accept-language"] = self.language
        headers["accept-encoding"] = "gzip, deflate, br"

        # Chrome-specific headers
        if browser == "chrome":
            headers["sec-ch-ua"] = random.choice(self.CHROME_UA_BRANDS)
            headers["sec-ch-ua-mobile"] = "?0"
            headers["sec-ch-ua-platform"] = f'"{self.platform}"'
            headers["upgrade-insecure-requests"] = "1"

            # Sec-Fetch headers
            headers["sec-fetch-dest"] = "document"
            headers["sec-fetch-mode"] = "navigate"
            headers["sec-fetch-site"] = "none" if not referer else "cross-site"
            headers["sec-fetch-user"] = "?1"

        # Referer
        if referer:
            headers["referer"] = referer

        # Connection
        headers["connection"] = "keep-alive"

        return headers

    def _default_ua(self) -> str:
        """Generate a default user agent."""
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

    def get_tls_config(self) -> Dict:
        """
        Get TLS configuration to match fingerprint.

        Note: Full JA3 fingerprint matching requires curl-impersonate
        or similar tools. This provides the basic configuration.
        """
        return {
            "ssl_version": "TLSv1.2",
            "cipher_suite": "ECDHE-RSA-AES128-GCM-SHA256",
            "extensions": [
                "server_name",
                "extended_master_secret",
                "renegotiation_info",
                "supported_groups",
                "ec_point_formats",
                "session_ticket",
                "application_layer_protocol_negotiation",
                "status_request",
                "signature_algorithms",
                "signed_certificate_timestamp",
                "key_share",
                "supported_versions",
                "cookie",
                "psk_key_exchange_modes",
                "certificate_authorities",
                "compress_certificate",
            ],
        }


class CookieJar:
    """
    Manages cookies with domain/path matching.

    Similar to browser cookie storage but for HTTP requests.
    """

    def __init__(self):
        self.cookies: Dict[str, List[Dict]] = {}  # domain -> cookies

    def add_cookie(self, cookie: Dict) -> None:
        """Add a cookie to the jar."""
        domain = cookie.get("domain", "").lstrip(".")
        if domain not in self.cookies:
            self.cookies[domain] = []

        # Remove existing cookie with same name
        self.cookies[domain] = [
            c for c in self.cookies[domain]
            if c.get("name") != cookie.get("name")
        ]
        self.cookies[domain].append(cookie)

    def add_cookies(self, cookies: List[Dict]) -> None:
        """Add multiple cookies."""
        for cookie in cookies:
            self.add_cookie(cookie)

    def get_for_request(self, url: str) -> str:
        """
        Get cookie header value for a URL.

        Args:
            url: Target URL

        Returns:
            Cookie header string
        """
        parsed = urlparse(url)
        host = parsed.hostname or ""
        path = parsed.path or "/"

        matching = []
        for domain, cookies in self.cookies.items():
            # Check domain match
            if host == domain or host.endswith("." + domain):
                for cookie in cookies:
                    # Check path match
                    cookie_path = cookie.get("path", "/")
                    if path.startswith(cookie_path):
                        # Check secure
                        if cookie.get("secure") and parsed.scheme != "https":
                            continue
                        # Check httpOnly (we can't check from here)
                        matching.append(f"{cookie['name']}={cookie['value']}")

        return "; ".join(matching)

    def to_list(self) -> List[Dict]:
        """Export all cookies as list."""
        result = []
        for cookies in self.cookies.values():
            result.extend(cookies)
        return result

    def clear(self) -> None:
        """Clear all cookies."""
        self.cookies.clear()


class RuntimeEngine:
    """
    Custom runtime for fingerprint-matched HTTP requests.

    Usage:
        engine = RuntimeEngine(config)
        response = engine.get("https://api.github.com/user")
        if response.status_code == 200:
            print(response.json())
    """

    def __init__(self, config: RuntimeConfig):
        self.config = config
        self.fingerprint = FingerprintMatcher(config.fingerprint)
        self.cookie_jar = CookieJar()
        self.cookie_jar.add_cookies(config.cookies)
        self.tokens = {t.get("token_type", "unknown"): t for t in config.tokens}
        self._session: Optional[requests.Session] = None
        self._last_request_time: float = 0
        self._setup_session()

    def _setup_session(self) -> None:
        """Configure requests session with retries and proxy."""
        self._session = requests.Session()

        # Retry strategy
        retry = Retry(
            total=self.config.retries,
            backoff_factor=self.config.backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

        # Proxy
        if self.config.proxy:
            self._session.proxies = {
                "http": self.config.proxy,
                "https": self.config.proxy,
            }

        # SSL verification
        self._session.verify = self.config.verify_ssl

    def _apply_rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        if self.config.rate_limit > 0:
            elapsed = time.time() - self._last_request_time
            if elapsed < self.config.rate_limit:
                time.sleep(self.config.rate_limit - elapsed)
        self._last_request_time = time.time()

    def _prepare_request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict] = None,
        referer: Optional[str] = None,
    ) -> Dict:
        """Prepare request with fingerprint-matched headers and cookies."""
        # Get fingerprint headers
        fp_headers = self.fingerprint.get_headers(url, referer)

        # Add cookies
        cookies = self.cookie_jar.get_for_request(url)
        if cookies:
            fp_headers["cookie"] = cookies

        # Merge with custom headers
        if headers:
            fp_headers.update(headers)

        # Add custom config headers
        fp_headers.update(self.config.custom_headers)

        return fp_headers

    def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict] = None,
        data: Optional[Any] = None,
        json_data: Optional[Dict] = None,
        referer: Optional[str] = None,
    ) -> requests.Response:
        """
        Make a fingerprint-matched HTTP request.

        Args:
            method: HTTP method
            url: Target URL
            headers: Additional headers
            data: Form data
            json_data: JSON payload
            referer: Referer URL

        Returns:
            Response object
        """
        self._apply_rate_limit()

        fp_headers = self._prepare_request(method, url, headers, referer)

        logger.debug(f"Runtime: {method} {url}")
        logger.debug(f"Headers: {json.dumps(fp_headers, indent=2)}")

        response = self._session.request(
            method=method,
            url=url,
            headers=fp_headers,
            data=data,
            json=json_data,
            timeout=self.config.timeout,
        )

        # Update cookie jar with response cookies
        if response.cookies:
            for cookie in response.cookies:
                self.cookie_jar.add_cookie({
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain or urlparse(url).hostname,
                    "path": cookie.path or "/",
                    "secure": cookie.secure,
                })

        logger.debug(f"Response: {response.status_code} {len(response.content)} bytes")
        return response

    def get(self, url: str, headers: Optional[Dict] = None, referer: Optional[str] = None) -> requests.Response:
        """GET request."""
        return self.request("GET", url, headers, referer=referer)

    def post(self, url: str, headers: Optional[Dict] = None, data: Optional[Any] = None,
             json_data: Optional[Dict] = None, referer: Optional[str] = None) -> requests.Response:
        """POST request."""
        return self.request("POST", url, headers, data, json_data, referer)

    def put(self, url: str, headers: Optional[Dict] = None, data: Optional[Any] = None,
            json_data: Optional[Dict] = None, referer: Optional[str] = None) -> requests.Response:
        """PUT request."""
        return self.request("PUT", url, headers, data, json_data, referer)

    def delete(self, url: str, headers: Optional[Dict] = None, referer: Optional[str] = None) -> requests.Response:
        """DELETE request."""
        return self.request("DELETE", url, headers, referer=referer)

    def close(self) -> None:
        """Close the session."""
        if self._session:
            self._session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class SessionValidator:
    """
    Validates session validity using the runtime engine.

    Tests if cookies/tokens are still valid by making API requests.
    """

    def __init__(self, engine: RuntimeEngine):
        self.engine = engine

    def validate_google_session(self) -> Dict:
        """
        Validate Google session by checking Labs API.

        Returns:
            Validation result dictionary
        """
        try:
            # Try to access Google Labs API
            response = self.engine.get("https://labs.google/fx/api/trpc/labs.listProjects")

            if response.status_code == 200:
                data = response.json()
                return {
                    "valid": True,
                    "status_code": response.status_code,
                    "projects": len(data.get("result", {}).get("data", [])),
                }
            elif response.status_code in (401, 403):
                return {
                    "valid": False,
                    "status_code": response.status_code,
                    "error": "Authentication failed",
                }
            else:
                return {
                    "valid": False,
                    "status_code": response.status_code,
                    "error": f"Unexpected status: {response.status_code}",
                }

        except Exception as e:
            return {
                "valid": False,
                "error": str(e),
            }

    def validate_github_session(self) -> Dict:
        """
        Validate GitHub session via API.

        Returns:
            Validation result dictionary
        """
        try:
            # Use OAuth token if available
            token = self.engine.tokens.get("oauth_access", {}).get("value")
            headers = {}
            if token:
                headers["Authorization"] = f"token {token}"

            response = self.engine.get(
                "https://api.github.com/user",
                headers=headers,
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "valid": True,
                    "login": data.get("login"),
                    "name": data.get("name"),
                }
            elif response.status_code == 401:
                return {
                    "valid": False,
                    "error": "Token expired or invalid",
                }
            else:
                return {
                    "valid": False,
                    "status_code": response.status_code,
                }

        except Exception as e:
            return {
                "valid": False,
                "error": str(e),
            }

    def validate_generic(self, url: str, success_codes: List[int] = [200]) -> Dict:
        """
        Generic session validation.

        Args:
            url: URL to test
            success_codes: HTTP codes indicating success

        Returns:
            Validation result
        """
        try:
            response = self.engine.get(url)
            return {
                "valid": response.status_code in success_codes,
                "status_code": response.status_code,
                "content_length": len(response.content),
            }
        except Exception as e:
            return {
                "valid": False,
                "error": str(e),
            }


def create_engine_from_session(session_file: str) -> RuntimeEngine:
    """
    Create a runtime engine from a saved session file.

    Args:
        session_file: Path to session JSON file

    Returns:
        Configured RuntimeEngine
    """
    with open(session_file, "r") as f:
        session = json.load(f)

    config = RuntimeConfig(
        fingerprint=session.get("fingerprint"),
        cookies=session.get("cookies", []),
        tokens=session.get("tokens", []),
        user_agent=session.get("fingerprint", {}).get("user_agent", ""),
    )

    return RuntimeEngine(config)
