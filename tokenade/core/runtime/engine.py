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
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from tokenade.core.runtime.tls_matcher import TLSMatcher, create_tls_matcher

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
    
    # TLS fingerprint matching (requires curl-cffi)
    use_tls_match: bool = True
    tls_impersonate: Optional[str] = None  # e.g., "chrome120", "firefox120"
    tls_browser: str = "chrome"
    tls_version: str = "120"


class FingerprintMatcher:
    """
    Matches HTTP requests to a browser fingerprint.

    Generates headers, TLS settings, and other parameters to make
    requests indistinguishable from the target browser.
    """

    # Common header orderings by browser (order matters for JA3/H2 fingerprinting)
    CHROME_HEADERS = [
        ":authority",
        ":method",
        ":path",
        ":scheme",
        "accept",
        "accept-encoding",
        "accept-language",
        "cache-control",
        "cookie",
        "sec-ch-ua",
        "sec-ch-ua-mobile",
        "sec-ch-ua-platform",
        "sec-fetch-dest",
        "sec-fetch-mode",
        "sec-fetch-site",
        "sec-fetch-user",
        "upgrade-insecure-requests",
        "user-agent",
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

    EDGE_HEADERS = [
        "accept",
        "accept-encoding",
        "accept-language",
        "cookie",
        "sec-ch-ua",
        "sec-ch-ua-mobile",
        "sec-ch-ua-platform",
        "sec-fetch-dest",
        "sec-fetch-mode",
        "sec-fetch-site",
        "sec-fetch-user",
        "upgrade-insecure-requests",
        "user-agent",
    ]

    # Chrome sec-ch-ua values by version
    CHROME_UA_BRANDS = {
        "109": '"Not_A Brand";v="99", "Google Chrome";v="109", "Chromium";v="109"',
        "120": '"Not.A/Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "119": '"Google Chrome";v="119", "Chromium";v="119", "Not?A_Brand";v="24"',
        "131": '"Google Chrome";v="131", "Chromium";v="131", "Not?A_Brand";v="24"',
    }

    def __init__(self, fingerprint: Optional[Dict] = None):
        self.fingerprint = fingerprint or {}
        self.ua = self.fingerprint.get("user_agent", "")
        self.platform = self.fingerprint.get("platform", "Win32")
        self.language = self.fingerprint.get("language", "en-US")
        self._browser = self._detect_browser()

    def _detect_browser(self) -> str:
        """Detect browser type from user agent."""
        if "Firefox" in self.ua:
            return "firefox"
        elif "Edg" in self.ua:
            return "edge"
        elif "OPR" in self.ua or "Opera" in self.ua:
            return "opera"
        else:
            return "chrome"

    def _get_chrome_version(self) -> str:
        """Extract Chrome major version from user agent."""
        import re
        match = re.search(r'Chrome/(\d+)', self.ua)
        return match.group(1) if match else "120"

    def _order_headers(self, headers: Dict[str, str]) -> OrderedDict:
        """
        Order headers according to browser-specific ordering.
        
        This is critical for HTTP/2 fingerprinting (H2 SETTINGS frame).
        """
        if self._browser == "firefox":
            order = self.FIREFOX_HEADERS
        elif self._browser == "edge":
            order = self.EDGE_HEADERS
        else:
            order = self.CHROME_HEADERS
        
        ordered = OrderedDict()
        
        # Add headers in browser-specific order
        for key in order:
            if key in headers:
                ordered[key] = headers[key]
        
        # Add any remaining headers not in the order list
        for key, value in headers.items():
            if key not in ordered:
                ordered[key] = value
        
        return ordered

    def get_headers(self, url: str, referer: Optional[str] = None, 
                    method: str = "GET", is_api: bool = False) -> OrderedDict:
        """
        Generate fingerprint-matched headers for a request.

        Args:
            url: Target URL
            referer: Optional referer URL
            method: HTTP method
            is_api: Whether this is an API request (different accept header)

        Returns:
            OrderedDict of HTTP headers in browser-specific order
        """
        headers = {}
        parsed = urlparse(url)
        is_secure = parsed.scheme == "https"

        # User-Agent
        headers["user-agent"] = self.ua or self._default_ua()

        # Accept headers - vary by request type
        if is_api:
            headers["accept"] = "application/json"
        elif parsed.path.endswith((".js", ".css")):
            headers["accept"] = "*/*"
        elif parsed.path.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
            headers["accept"] = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
        else:
            headers["accept"] = (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,image/apng,*/*;"
                "q=0.8,application/signed-exchange;v=b3;q=0.7"
            )
        
        headers["accept-language"] = self.language
        headers["accept-encoding"] = "gzip, deflate, br"

        # Chrome-specific headers
        if self._browser == "chrome":
            version = self._get_chrome_version()
            headers["sec-ch-ua"] = self.CHROME_UA_BRANDS.get(version, 
                self.CHROME_UA_BRANDS.get("120", self.CHROME_UA_BRANDS["131"]))
            headers["sec-ch-ua-mobile"] = "?0"
            headers["sec-ch-ua-platform"] = f'"{self.platform}"'
            headers["upgrade-insecure-requests"] = "1"

            # Sec-Fetch headers
            headers["sec-fetch-dest"] = "document" if not is_api else ""
            headers["sec-fetch-mode"] = "navigate" if not is_api else "cors"
            headers["sec-fetch-site"] = "none" if not referer else "cross-site"
            headers["sec-fetch-user"] = "?1" if not is_api else ""

        # Referer
        if referer:
            headers["referer"] = referer

        # Connection
        headers["connection"] = "keep-alive"
        
        # Cache control for initial page loads
        if not referer:
            headers["cache-control"] = "max-age=0"

        # Remove empty values
        headers = {k: v for k, v in headers.items() if v}

        # Order headers according to browser fingerprint
        return self._order_headers(headers)

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
    Manages cookies with domain/path matching and expiry checking.

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

    def _is_cookie_expired(self, cookie: Dict) -> bool:
        """Check if a cookie has expired."""
        expires = cookie.get("expires", 0)
        if not expires or int(expires) <= 0:
            return False  # Session cookie, never expires
        
        expires_int = int(expires)
        # Convert milliseconds to seconds if needed
        if expires_int > 1262304000000:
            expires_int = expires_int // 1000
        
        return expires_int < time.time()

    def _is_cookie_valid_for_request(self, cookie: Dict, parsed_url) -> bool:
        """Check if a cookie should be sent for a request."""
        # Check expiry
        if self._is_cookie_expired(cookie):
            return False
        
        # Check secure flag
        if cookie.get("secure") and parsed_url.scheme != "https":
            return False
        
        return True

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
            domain_match = False
            if not domain:
                # Empty domain matches the exact host
                domain_match = True
            elif host == domain or host.endswith("." + domain):
                domain_match = True
            
            if domain_match:
                for cookie in cookies:
                    # Check path match
                    cookie_path = cookie.get("path", "/")
                    if path.startswith(cookie_path):
                        # Check if cookie is valid
                        if not self._is_cookie_valid_for_request(cookie, parsed):
                            continue
                        # Skip __Host- cookies with domain set (invalid per spec)
                        cookie_name = cookie.get("name", "")
                        if cookie_name.startswith("__Host-") and cookie.get("domain"):
                            continue
                        matching.append(f"{cookie['name']}={cookie['value']}")

        return "; ".join(matching)
    
    def get_valid_cookies(self, url: str) -> List[Dict]:
        """
        Get all valid cookies for a URL as a list of dicts.
        
        Args:
            url: Target URL
            
        Returns:
            List of cookie dicts
        """
        parsed = urlparse(url)
        host = parsed.hostname or ""
        path = parsed.path or "/"

        matching = []
        for domain, cookies in self.cookies.items():
            if host == domain or host.endswith("." + domain):
                for cookie in cookies:
                    cookie_path = cookie.get("path", "/")
                    if path.startswith(cookie_path):
                        if self._is_cookie_valid_for_request(cookie, parsed):
                            matching.append(cookie)
        return matching

    def to_list(self) -> List[Dict]:
        """Export all cookies as list."""
        result = []
        for cookies in self.cookies.values():
            result.extend(cookies)
        return result
    
    def get_expired_cookies(self) -> List[Dict]:
        """Get all expired cookies."""
        expired = []
        for cookies in self.cookies.values():
            for cookie in cookies:
                if self._is_cookie_expired(cookie):
                    expired.append(cookie)
        return expired
    
    def prune_expired(self) -> int:
        """Remove expired cookies. Returns number removed."""
        count = 0
        for domain in list(self.cookies.keys()):
            before = len(self.cookies[domain])
            self.cookies[domain] = [
                c for c in self.cookies[domain]
                if not self._is_cookie_expired(c)
            ]
            count += before - len(self.cookies[domain])
            if not self.cookies[domain]:
                del self.cookies[domain]
        return count

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
        self._tls_matcher: Optional[TLSMatcher] = None
        self._last_request_time: float = 0
        self._setup_session()
        self._setup_tls_matcher()

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
    
    def _setup_tls_matcher(self) -> None:
        """Setup TLS matcher for fingerprint-matched requests."""
        if not self.config.use_tls_match:
            return
        
        try:
            self._tls_matcher = create_tls_matcher(
                browser=self.config.tls_browser,
                version=self.config.tls_version,
                impersonate=self.config.tls_impersonate
            )
            logger.debug("TLS matcher initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize TLS matcher: {e}")
            self._tls_matcher = None

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
        use_tls: Optional[bool] = None,
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
            use_tls: Force TLS matching (None = auto-detect)

        Returns:
            Response object
        """
        self._apply_rate_limit()

        fp_headers = self._prepare_request(method, url, headers, referer)

        logger.debug(f"Runtime: {method} {url}")
        logger.debug(f"Headers: {json.dumps(fp_headers, indent=2)}")

        # Use TLS matcher if available and requested
        use_tls = use_tls if use_tls is not None else (self._tls_matcher is not None)
        
        if use_tls and self._tls_matcher:
            # Use curl-cffi for TLS fingerprint matching
            logger.debug("Using TLS fingerprint matching")
            
            # Get cookies as dictionary
            cookies_dict = {}
            for cookie in self.cookie_jar.to_list():
                cookies_dict[cookie["name"]] = cookie["value"]
            
            response = self._tls_matcher.request(
                method=method,
                url=url,
                headers=fp_headers,
                cookies=cookies_dict,
                data=data,
                json_data=json_data,
                timeout=self.config.timeout,
            )
            
            # Convert to requests.Response for compatibility
            # Note: curl-cffi response is compatible with requests.Response
        else:
            # Fallback to standard requests
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
        if self._tls_matcher:
            self._tls_matcher.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    @property
    def has_tls_matching(self) -> bool:
        """Check if TLS matching is available."""
        return self._tls_matcher is not None


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
