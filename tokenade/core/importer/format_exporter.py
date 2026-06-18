"""
Multi-format session exporter.

Converts .tokenade session data to Playwright storageState, Puppeteer cookies,
Netscape/curl format, HTTP cookie headers, and raw JSON.
"""

import json
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class FormatExporter:
    """Export session data in multiple formats."""

    def __init__(self, session: Dict):
        self.session = session
        self.cookies = session.get("cookies", [])

    def to_playwright_storagestate(self, include_local_storage: bool = True) -> str:
        """Convert to Playwright storageState JSON format.

        Playwright storageState format:
        {
            "cookies": [
                {
                    "name": "...",
                    "value": "...",
                    "domain": "...",
                    "path": "/",
                    "expires": -1,  # Unix timestamp or -1 for session
                    "httpOnly": false,
                    "secure": false,
                    "sameSite": "Strict" | "Lax" | "None"
                }
            ],
            "origins": [
                {
                    "origin": "https://example.com",
                    "localStorage": [
                        {"name": "key", "value": "value"}
                    ]
                }
            ]
        }
        """
        pw_cookies = []
        for cookie in self.cookies:
            pw_cookie = {
                "name": cookie.get("name", ""),
                "value": cookie.get("value", ""),
                "domain": cookie.get("domain", ""),
                "path": cookie.get("path", "/"),
                "expires": cookie.get("expires", -1),
                "httpOnly": cookie.get("httpOnly", False),
                "secure": cookie.get("secure", False),
                "sameSite": self._normalize_samesite(cookie.get("sameSite", "Lax")),
            }
            pw_cookies.append(pw_cookie)

        storage_state = {"cookies": pw_cookies, "origins": []}

        if include_local_storage:
            local_storage = self.session.get("local_storage", {})
            if local_storage:
                origins_map: Dict[str, List[Dict]] = {}
                for key, value in local_storage.items():
                    if ":" in key:
                        domain, ls_key = key.split(":", 1)
                    else:
                        domain = "https://" + self.session.get("site_name", "unknown.com")
                        ls_key = key

                    origin = domain if domain.startswith("http") else "https://" + domain
                    if origin not in origins_map:
                        origins_map[origin] = []
                    origins_map[origin].append({"name": ls_key, "value": value})

                for origin, items in origins_map.items():
                    storage_state["origins"].append({
                        "origin": origin,
                        "localStorage": items,
                    })

        return json.dumps(storage_state, indent=2, ensure_ascii=False)

    def to_puppeteer_cookies(self) -> List[Dict]:
        """Convert to CDP/Puppeteer Network.Cookie format.

        CDP Cookie format:
        {
            "name": "...",
            "value": "...",
            "domain": "...",
            "path": "/",
            "expires": -1,  # Unix timestamp or -1 for session cookies
            "size": 0,
            "httpOnly": false,
            "secure": false,
            "session": true,
            "sameSite": "Strict" | "Lax" | "None",
            "sameSiteCookiePolicy": "Strict" | "Lax" | "None",
            "priority": "Medium",
            "sameParty": "None",
            "sourceScheme": "Unset",
            "partitionKey": ""
        }
        """
        cdp_cookies = []
        for cookie in self.cookies:
            expires = cookie.get("expires", -1)
            is_session = expires == -1 or expires is None

            cdp_cookie = {
                "name": cookie.get("name", ""),
                "value": cookie.get("value", ""),
                "domain": cookie.get("domain", ""),
                "path": cookie.get("path", "/"),
                "expires": expires if expires else -1,
                "size": len(cookie.get("value", "")),
                "httpOnly": cookie.get("httpOnly", False),
                "secure": cookie.get("secure", False),
                "session": is_session,
                "sameSite": self._normalize_samesite(cookie.get("sameSite", "Lax")),
                "sameSiteCookiePolicy": self._normalize_samesite(cookie.get("sameSite", "Lax")),
                "priority": "Medium",
                "sameParty": "None",
                "sourceScheme": "Secure" if cookie.get("secure") else "Unset",
                "partitionKey": "",
            }
            cdp_cookies.append(cdp_cookie)

        return cdp_cookies

    def to_netscape(self) -> str:
        """Convert to Netscape/curl cookie jar format.

        Format:
        # Netscape HTTP Cookie File
        # http://curl.haxx.se/rfc/cookie_spec.html
        # This file was generated by Tokenade

        .domain.com	TRUE	/	FALSE	1781000000	name	value

        Fields: domain, tailmatch, path, secure, expires, name, value
        """
        lines = [
            "# Netscape HTTP Cookie File",
            "# http://curl.haxx.se/rfc/cookie_spec.html",
            "# This file was generated by Tokenade",
            "",
        ]

        for cookie in self.cookies:
            domain = cookie.get("domain", "")
            path = cookie.get("path", "/")
            secure = "TRUE" if cookie.get("secure", False) else "FALSE"
            expires = cookie.get("expires", 0)
            if expires is None or expires < 0:
                expires = 0
            name = cookie.get("name", "")
            value = cookie.get("value", "")

            # tailmatch: TRUE if domain starts with '.', meaning it matches subdomains
            tailmatch = "TRUE" if domain.startswith(".") else "FALSE"

            lines.append(f"{domain}\t{tailmatch}\t{path}\t{secure}\t{expires}\t{name}\t{value}")

        return "\n".join(lines) + "\n"

    def to_cookie_header(self) -> str:
        """Convert to HTTP Cookie header string.

        Format: "name1=value1; name2=value2; name3=value3"
        """
        pairs = []
        for cookie in self.cookies:
            name = cookie.get("name", "")
            value = cookie.get("value", "")
            pairs.append(f"{name}={value}")
        return "; ".join(pairs)

    def to_json(self, indent: int = 2) -> str:
        """Export as formatted JSON (the native .tokenade format)."""
        return json.dumps(self.session, indent=indent, ensure_ascii=False)

    def to_requests_dict(self) -> Dict:
        """Convert to requests library cookie format.

        Returns dict suitable for requests.Session().cookies.set()
        """
        cookies_dict = {}
        for cookie in self.cookies:
            name = cookie.get("name", "")
            value = cookie.get("value", "")
            if name:
                cookies_dict[name] = value
        return cookies_dict

    @staticmethod
    def _normalize_samesite(value: str) -> str:
        """Normalize sameSite value to Playwright/CDP expected values."""
        if not value:
            return "Lax"
        normalized = value.capitalize()
        if normalized in ("Strict", "Lax", "None"):
            return normalized
        return "Lax"
