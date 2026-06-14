"""
Multi-format session importer.

Imports session data from Playwright storageState, Netscape, HTTP cookie headers.
"""

import json
import re
from typing import Dict, List, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class FormatImporter:
    """Import session data from various formats."""

    @staticmethod
    def from_playwright_storagestate(file_path: str) -> Dict:
        """Import from Playwright storageState JSON file.

        Returns a minimal .tokenade-compatible session dict with cookies.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        cookies = []
        for pw_cookie in data.get("cookies", []):
            cookie = {
                "name": pw_cookie.get("name", ""),
                "value": pw_cookie.get("value", ""),
                "domain": pw_cookie.get("domain", ""),
                "path": pw_cookie.get("path", "/"),
                "secure": pw_cookie.get("secure", False),
                "httpOnly": pw_cookie.get("httpOnly", False),
                "sameSite": pw_cookie.get("sameSite", "Lax"),
            }
            expires = pw_cookie.get("expires", -1)
            if expires and expires > 0:
                cookie["expires"] = int(expires)
            cookies.append(cookie)

        local_storage = {}
        for origin_data in data.get("origins", []):
            origin = origin_data.get("origin", "")
            for ls_entry in origin_data.get("localStorage", []):
                key = ls_entry.get("name", "")
                value = ls_entry.get("value", "")
                domain = origin.replace("https://", "").replace("http://", "")
                local_storage[f"{domain}:{key}"] = value

        return FormatImporter._build_session(
            cookies=cookies,
            local_storage=local_storage,
            source_format="playwright",
        )

    @staticmethod
    def from_netscape(file_path: str) -> Dict:
        """Import from Netscape/curl cookie jar file.

        Parses the tab-separated format and converts to standard cookie dict.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        cookies = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split("\t")
            if len(parts) >= 7:
                domain = parts[0]
                tailmatch = parts[1]
                cookie_path = parts[2]
                secure_str = parts[3]
                expires_str = parts[4]
                name = parts[5]
                value = parts[6]

                secure = secure_str.upper() == "TRUE"
                try:
                    expires = int(expires_str)
                except (ValueError, TypeError):
                    expires = 0

                # Determine httpOnly from #HttpOnly_ prefix or tailmatch convention
                http_only = domain.startswith("#HttpOnly_")
                if http_only:
                    domain = domain[len("#HttpOnly_"):]

                cookie = {
                    "name": name,
                    "value": value,
                    "domain": domain,
                    "path": cookie_path,
                    "secure": secure,
                    "httpOnly": http_only,
                    "sameSite": "Lax",
                }
                if expires > 0:
                    cookie["expires"] = expires

                cookies.append(cookie)

        return FormatImporter._build_session(
            cookies=cookies,
            local_storage={},
            source_format="netscape",
        )

    @staticmethod
    def from_cookie_header(header: str, domain: str = "") -> Dict:
        """Import from HTTP Cookie header string.

        Parses "name1=value1; name2=value2" format.
        """
        cookies = []
        if not header or not header.strip():
            return FormatImporter._build_session(
                cookies=[],
                local_storage={},
                source_format="cookie_header",
            )

        for pair in header.split(";"):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue

            name, _, value = pair.partition("=")
            name = name.strip()
            value = value.strip()

            if name:
                cookie = {
                    "name": name,
                    "value": value,
                    "domain": domain,
                    "path": "/",
                    "secure": False,
                    "httpOnly": False,
                    "sameSite": "Lax",
                }
                cookies.append(cookie)

        return FormatImporter._build_session(
            cookies=cookies,
            local_storage={},
            source_format="cookie_header",
        )

    @staticmethod
    def from_json(file_path: str) -> Dict:
        """Import from raw JSON (any standard cookie array format)."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            cookies = data
        elif isinstance(data, dict):
            cookies = data.get("cookies", [])
            if not cookies and "name" in data and "value" in data:
                cookies = [data]
        else:
            cookies = []

        normalized = []
        for cookie in cookies:
            normalized.append({
                "name": cookie.get("name", ""),
                "value": cookie.get("value", ""),
                "domain": cookie.get("domain", ""),
                "path": cookie.get("path", "/"),
                "secure": cookie.get("secure", False),
                "httpOnly": cookie.get("httpOnly", False),
                "sameSite": cookie.get("sameSite", "Lax"),
                **({"expires": cookie["expires"]} if cookie.get("expires") else {}),
            })

        return FormatImporter._build_session(
            cookies=normalized,
            local_storage={},
            source_format="json",
        )

    @staticmethod
    def detect_format(file_path: str) -> str:
        """Auto-detect the format of a cookie file.

        Returns: 'playwright', 'netscape', 'json', or 'unknown'
        """
        path = Path(file_path)
        if not path.exists():
            return "unknown"

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read(4096)
        except Exception:
            return "unknown"

        stripped = content.strip()

        # Check for JSON
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                data = json.loads(content)
                if isinstance(data, dict) and ("cookies" in data or "origins" in data):
                    if "origins" in data:
                        return "playwright"
                    return "json"
                if isinstance(data, list):
                    return "json"
            except json.JSONDecodeError:
                pass

        # Check for Netscape format
        if content.startswith("# Netscape HTTP Cookie File") or content.startswith("# HTTP Cookie File"):
            return "netscape"
        if content.startswith("# curl"):
            return "netscape"

        # Check for tab-separated lines with typical Netscape structure
        lines = [l for l in content.splitlines() if l.strip() and not l.startswith("#")]
        if lines:
            first_line = lines[0]
            parts = first_line.split("\t")
            if len(parts) >= 7:
                return "netscape"

        return "unknown"

    @staticmethod
    def _build_session(cookies: List[Dict], local_storage: Dict, source_format: str) -> Dict:
        """Build a minimal .tokenade-compatible session dict."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        return {
            "version": "2.0",
            "created_at": now,
            "source_device": {
                "browser": "unknown",
                "profile": "unknown",
                "platform": "unknown",
                "hostname": "unknown",
            },
            "site_name": "unknown",
            "auth_status": "unknown",
            "cookies": cookies,
            "tokens": [],
            "local_storage": local_storage,
            "fingerprint": None,
            "tls_profile": None,
            "metadata": {
                "extraction_method": f"import_{source_format}",
                "cookie_count": len(cookies),
                "critical_cookie_count": 0,
                "local_storage_count": len(local_storage),
            },
        }
