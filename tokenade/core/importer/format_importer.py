"""
Multi-format session importer.

Imports session data from industry cookie / storage formats into .tokenade.
"""

import csv
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Formats shown in CLI / TUI (auto always first)
SUPPORTED_FORMATS: Tuple[str, ...] = (
    "auto",
    "json",
    "netscape",
    "curl",
    "playwright",
    "puppeteer",
    "cookie-editor",
    "editthiscookie",
    "cypress",
    "selenium",
    "header",
    "set-cookie",
    "har",
    "csv",
)


class FormatImporter:
    """Import session data from various formats."""

    @staticmethod
    def from_playwright_storagestate(file_path: str) -> Dict:
        """Import from Playwright storageState JSON file."""
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
            if not origin:
                continue
            entries = local_storage.setdefault(origin, {})
            for ls_entry in origin_data.get("localStorage", []):
                key = ls_entry.get("name", "")
                value = ls_entry.get("value", "")
                if key:
                    entries[key] = value

        return FormatImporter._build_session(
            cookies=cookies,
            local_storage=local_storage,
            source_format="playwright",
        )

    @staticmethod
    def from_netscape(file_path: str) -> Dict:
        """Import from Netscape/curl cookie jar file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        cookies = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                # #HttpOnly_domain\t... is a netscape extension
                if line.startswith("#HttpOnly_"):
                    line = line[len("#HttpOnly_"):]
                    http_only_forced = True
                else:
                    continue
            else:
                http_only_forced = False

            parts = line.split("\t")
            if len(parts) >= 7:
                domain = parts[0]
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

                http_only = http_only_forced or domain.startswith("#HttpOnly_")
                if domain.startswith("#HttpOnly_"):
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
        """Import from HTTP Cookie header string (name1=value1; name2=value2)."""
        cookies = []
        if not header or not header.strip():
            return FormatImporter._build_session(
                cookies=[],
                local_storage={},
                source_format="cookie_header",
            )

        text = header.strip()
        # Strip optional "Cookie:" prefix
        if text.lower().startswith("cookie:"):
            text = text.split(":", 1)[1].strip()

        for pair in text.split(";"):
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
    def from_header_file(file_path: str, domain: str = "") -> Dict:
        """Import Cookie request-header from a text file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        # Prefer a line that looks like Cookie: ...
        for line in text.splitlines():
            s = line.strip()
            if s.lower().startswith("cookie:"):
                return FormatImporter.from_cookie_header(s, domain=domain)
        return FormatImporter.from_cookie_header(text, domain=domain)

    @staticmethod
    def from_set_cookie_file(file_path: str, domain: str = "") -> Dict:
        """Import one or more Set-Cookie response header lines."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        text = path.read_text(encoding="utf-8", errors="replace")
        cookies = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("set-cookie:"):
                line = line.split(":", 1)[1].strip()
            c = FormatImporter._parse_set_cookie(line, default_domain=domain)
            if c:
                cookies.append(c)
        return FormatImporter._build_session(
            cookies=cookies,
            local_storage={},
            source_format="set-cookie",
        )

    @staticmethod
    def _parse_set_cookie(header: str, default_domain: str = "") -> Optional[Dict]:
        if not header or "=" not in header:
            return None
        parts = [p.strip() for p in header.split(";")]
        name, _, value = parts[0].partition("=")
        name = name.strip()
        value = value.strip()
        if not name:
            return None
        cookie: Dict = {
            "name": name,
            "value": value,
            "domain": default_domain,
            "path": "/",
            "secure": False,
            "httpOnly": False,
            "sameSite": "Lax",
        }
        for attr in parts[1:]:
            if "=" in attr:
                k, _, v = attr.partition("=")
                k = k.strip().lower()
                v = v.strip()
                if k == "domain":
                    cookie["domain"] = v
                elif k == "path":
                    cookie["path"] = v or "/"
                elif k == "expires":
                    # RFC date — leave unset if unparsable (session cookie ok)
                    pass
                elif k == "max-age":
                    try:
                        import time
                        cookie["expires"] = int(time.time()) + int(v)
                    except (TypeError, ValueError):
                        pass
                elif k == "samesite":
                    cookie["sameSite"] = v.capitalize() if v else "Lax"
            else:
                a = attr.strip().lower()
                if a == "secure":
                    cookie["secure"] = True
                elif a == "httponly":
                    cookie["httpOnly"] = True
        return cookie

    @staticmethod
    def from_json(file_path: str) -> Dict:
        """Import from raw JSON (cookie array / object / extension export)."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        cookies_raw, local_storage, source = FormatImporter._extract_cookies_from_json(data)
        normalized = [FormatImporter._normalize_cookie(c) for c in cookies_raw]
        normalized = [c for c in normalized if c.get("name")]

        return FormatImporter._build_session(
            cookies=normalized,
            local_storage=local_storage,
            source_format=source,
        )

    @staticmethod
    def from_har(file_path: str) -> Dict:
        """Extract cookies from a HAR (HTTP Archive) export."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        by_key: Dict[Tuple[str, str, str], Dict] = {}
        log = data.get("log") or {}
        for entry in log.get("entries") or []:
            req = entry.get("request") or {}
            for c in req.get("cookies") or []:
                n = FormatImporter._normalize_cookie(c)
                if n.get("name"):
                    key = (n.get("domain", ""), n["name"], n.get("path", "/"))
                    by_key[key] = n
            # Cookie header
            for h in req.get("headers") or []:
                if str(h.get("name", "")).lower() == "cookie":
                    sess = FormatImporter.from_cookie_header(str(h.get("value", "")))
                    for n in sess.get("cookies") or []:
                        key = (n.get("domain", ""), n["name"], n.get("path", "/"))
                        by_key[key] = n
            resp = entry.get("response") or {}
            for c in resp.get("cookies") or []:
                n = FormatImporter._normalize_cookie(c)
                if n.get("name"):
                    key = (n.get("domain", ""), n["name"], n.get("path", "/"))
                    by_key[key] = n
            for h in resp.get("headers") or []:
                if str(h.get("name", "")).lower() == "set-cookie":
                    sc = FormatImporter._parse_set_cookie(str(h.get("value", "")))
                    if sc and sc.get("name"):
                        key = (sc.get("domain", ""), sc["name"], sc.get("path", "/"))
                        by_key[key] = sc

        cookies = list(by_key.values())
        return FormatImporter._build_session(
            cookies=cookies,
            local_storage={},
            source_format="har",
        )

    @staticmethod
    def from_csv(file_path: str) -> Dict:
        """Import cookies from CSV (name,value,domain,path,...)."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        cookies = []
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
            sample = f.read(4096)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(f, dialect=dialect)
            if not reader.fieldnames:
                return FormatImporter._build_session([], {}, "csv")
            # Normalize headers
            fields = {(h or "").strip().lower(): h for h in reader.fieldnames}
            for row in reader:
                def g(*names, default=""):
                    for n in names:
                        key = fields.get(n)
                        if key is not None and row.get(key) not in (None, ""):
                            return row[key]
                    return default

                raw = {
                    "name": g("name", "cookie", "key"),
                    "value": g("value", "val"),
                    "domain": g("domain", "host", "host_key"),
                    "path": g("path", default="/") or "/",
                    "secure": g("secure", "is_secure"),
                    "httpOnly": g("httponly", "http_only", "is_httponly"),
                    "sameSite": g("samesite", "same_site", default="Lax"),
                    "expires": g("expires", "expiry", "expiration", "expirationdate"),
                }
                n = FormatImporter._normalize_cookie(raw)
                if n.get("name"):
                    cookies.append(n)
        return FormatImporter._build_session(cookies, {}, "csv")

    @staticmethod
    def _extract_cookies_from_json(data) -> Tuple[List, Dict, str]:
        """Pull cookie list + optional localStorage from nested JSON shapes."""
        local_storage: Dict = {}
        source = "json"

        if isinstance(data, list):
            # Cookie-Editor / EditThisCookie array, or puppeteer cookies[]
            if data and isinstance(data[0], dict):
                if "expirationDate" in data[0] or "storeId" in data[0]:
                    source = "cookie-editor"
                elif "sameSite" in data[0] and "expires" in data[0]:
                    source = "json"
            return data, local_storage, source

        if not isinstance(data, dict):
            return [], local_storage, source

        # Playwright storageState
        if "origins" in data and "cookies" in data:
            cookies = data.get("cookies") or []
            for origin_data in data.get("origins") or []:
                origin = origin_data.get("origin", "")
                for ls_entry in origin_data.get("localStorage") or []:
                    key = ls_entry.get("name", "")
                    value = ls_entry.get("value", "")
                    domain = origin.replace("https://", "").replace("http://", "")
                    local_storage[f"{domain}:{key}"] = value
            return cookies, local_storage, "playwright"

        # HAR
        if "log" in data and isinstance(data.get("log"), dict):
            return [], local_storage, "har"

        # Puppeteer CDP: { cookies: [...] } or page.cookies()
        if "cookies" in data and isinstance(data["cookies"], list):
            cookies = data["cookies"]
            # Cypress: sometimes { cookies: { domain: [...] } }
            if data.get("origins") is None and any(
                k in data for k in ("localStorage", "sessionStorage")
            ):
                ls = data.get("localStorage") or {}
                if isinstance(ls, dict):
                    for k, v in ls.items():
                        local_storage[str(k)] = str(v)
                source = "cypress" if "cypress" in str(data.get("name", "")).lower() else "puppeteer"
            else:
                source = "puppeteer" if data.get("url") or data.get("sameSite") is None else "json"
            # Selenium JSON often has "secure" as string
            if cookies and isinstance(cookies[0], dict) and "expiry" in cookies[0]:
                source = "selenium"
            return cookies, local_storage, source

        # Cookie-Editor export: { url, cookies: [...] } already handled
        # Nested under "cookie" / "Cookie" / "items"
        for key in ("cookie", "Cookie", "items", "data", "result"):
            val = data.get(key)
            if isinstance(val, list):
                return val, local_storage, "json"
            if isinstance(val, dict) and "cookies" in val:
                return val.get("cookies") or [], local_storage, "json"

        # Single cookie object
        if "name" in data and "value" in data:
            return [data], local_storage, "json"

        # Name→value map (simple)
        if data and all(isinstance(v, (str, int, float, bool)) for v in data.values()):
            # Might be localStorage dump — not cookies
            if any(k in data for k in ("session", "token", "sid", "auth")):
                cookies = [
                    {"name": str(k), "value": str(v), "domain": "", "path": "/"}
                    for k, v in data.items()
                ]
                return cookies, local_storage, "json"

        return [], local_storage, source

    @staticmethod
    def _normalize_cookie(cookie: Dict) -> Dict:
        if not isinstance(cookie, dict):
            return {}
        # Selenium uses expiry; Cookie-Editor uses expirationDate; Chrome uses expires_utc
        expires = cookie.get("expires")
        if expires in (None, "", 0, -1):
            for alt in ("expirationDate", "expiry", "expiration", "expires_utc"):
                if cookie.get(alt) not in (None, ""):
                    expires = cookie.get(alt)
                    break
        try:
            expires_i = int(float(expires)) if expires not in (None, "") else None
        except (TypeError, ValueError):
            expires_i = None
        # Chrome WebKit epoch (microseconds since 1601) — rough detect
        if expires_i and expires_i > 10_000_000_000_000:
            # microseconds webkit → unix
            expires_i = int(expires_i / 1_000_000 - 11644473600)
        elif expires_i and expires_i > 10_000_000_000:
            # milliseconds
            expires_i = int(expires_i / 1000)

        def _bool(v, default=False):
            if isinstance(v, bool):
                return v
            if isinstance(v, (int, float)):
                return bool(v)
            if isinstance(v, str):
                return v.strip().lower() in ("1", "true", "yes", "on")
            return default

        domain = cookie.get("domain") or cookie.get("host") or cookie.get("host_key") or ""
        if isinstance(domain, str):
            domain = domain.strip()

        same = cookie.get("sameSite", cookie.get("same_site", cookie.get("samesite", "Lax")))
        if isinstance(same, int):
            same = {0: "None", 1: "Lax", 2: "Strict"}.get(same, "Lax")
        same = str(same or "Lax")
        # Playwright uses "None" | "Lax" | "Strict"; some use no_restriction
        sl = same.lower().replace("_", "").replace("-", "")
        if sl in ("none", "norestriction", "no_restriction"):
            same = "None"
        elif sl in ("lax",):
            same = "Lax"
        elif sl in ("strict",):
            same = "Strict"
        else:
            same = same[:1].upper() + same[1:] if same else "Lax"

        value = cookie.get("value", "")
        if value is None:
            value = ""
        # Some exports URL-encode values
        if isinstance(value, str) and "%" in value and cookie.get("decoded") is not True:
            try:
                # only decode if it looks fully encoded and round-trips poorly — keep raw
                pass
            except Exception:
                pass

        entry = {
            "name": str(cookie.get("name", cookie.get("key", "")) or ""),
            "value": str(value),
            "domain": domain,
            "path": cookie.get("path") or "/",
            "secure": _bool(cookie.get("secure", cookie.get("isSecure", cookie.get("is_secure"))), False),
            "httpOnly": _bool(
                cookie.get("httpOnly", cookie.get("http_only", cookie.get("isHttpOnly", cookie.get("is_httponly")))),
                False,
            ),
            "sameSite": same or "Lax",
        }
        if expires_i and expires_i > 0:
            entry["expires"] = expires_i
        return entry

    @staticmethod
    def detect_format(file_path: str) -> str:
        """Auto-detect cookie file format."""
        path = Path(file_path)
        if not path.exists():
            return "unknown"

        suffix = path.suffix.lower()
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return "unknown"

        stripped = content.lstrip()
        if stripped.startswith("\ufeff"):
            stripped = stripped.lstrip("\ufeff")

        # HAR
        if '"log"' in stripped[:500] and ("\"entries\"" in stripped[:2000] or '"version"' in stripped[:500]):
            try:
                data = json.loads(content)
                if isinstance(data, dict) and isinstance(data.get("log"), dict):
                    return "har"
            except json.JSONDecodeError:
                pass

        if stripped.startswith("{") or stripped.startswith("["):
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    if "origins" in data and "cookies" in data:
                        return "playwright"
                    if "log" in data and isinstance(data.get("log"), dict):
                        return "har"
                    if "cookies" in data and isinstance(data.get("cookies"), list):
                        cookies = data["cookies"]
                        if cookies and isinstance(cookies[0], dict) and "expiry" in cookies[0]:
                            return "selenium"
                        if data.get("url") or "puppeteer" in str(data.get("_meta", "")).lower():
                            return "puppeteer"
                        return "json"
                    if "name" in data and "value" in data:
                        return "json"
                if isinstance(data, list):
                    if data and isinstance(data[0], dict):
                        first = data[0]
                        if "expirationDate" in first or "storeId" in first:
                            return "cookie-editor"
                        if "expiry" in first and "httpOnly" in first:
                            return "selenium"
                    return "json"
            except json.JSONDecodeError:
                if stripped.startswith("["):
                    return "json"

        head = stripped[:120]
        if head.startswith("# Netscape HTTP Cookie File") or head.startswith("# HTTP Cookie File"):
            return "netscape"
        if head.startswith("# curl"):
            return "curl"

        lower_head = stripped[:200].lower()
        if lower_head.startswith("set-cookie:") or "\nset-cookie:" in lower_head:
            return "set-cookie"
        if lower_head.startswith("cookie:") or (
            "=" in stripped[:200] and ";" in stripped[:500] and "\t" not in stripped[:200]
            and not stripped.startswith("#")
            and suffix in (".txt", ".header", ".headers", "")
        ):
            # single-line cookie header dump
            if "\t" not in stripped.splitlines()[0] if stripped.splitlines() else True:
                line0 = stripped.splitlines()[0] if stripped.splitlines() else ""
                if line0.count("=") >= 1 and "\t" not in line0 and not line0.startswith("."):
                    return "header"

        lines = [line for line in content.splitlines() if line.strip() and not line.startswith("#")]
        if lines:
            first_line = lines[0]
            parts = first_line.split("\t")
            if len(parts) >= 7:
                return "netscape"

        if suffix == ".csv" or (lines and ("," in lines[0]) and re.search(r"name|domain|value", lines[0], re.I)):
            return "csv"

        if suffix == ".har":
            return "har"

        return "unknown"

    @staticmethod
    def _storage_from_flat(local_storage: Dict, cookies: List[Dict]) -> Dict:
        """Turn flat localStorage maps into v3 per-origin ``storage``."""
        storage: Dict = {"local": {}, "session": {}}
        if not local_storage:
            return storage

        # Already per-origin: {origin: {k: v}}
        sample = next(iter(local_storage.values()), None)
        if local_storage and all(isinstance(v, dict) for v in local_storage.values()):
            storage["local"] = {str(k): dict(v) for k, v in local_storage.items()}
            return storage

        # Flat "domain:key" → value (Playwright-style importer)
        by_origin: Dict[str, Dict[str, str]] = {}
        plain: Dict[str, str] = {}
        for key, value in local_storage.items():
            ks = str(key)
            if ":" in ks and not ks.startswith("http"):
                domain, rest = ks.split(":", 1)
                origin = domain if domain.startswith("http") else f"https://{domain.lstrip('.')}"
                by_origin.setdefault(origin, {})[rest] = "" if value is None else str(value)
            else:
                plain[ks] = "" if value is None else str(value)
        if by_origin:
            storage["local"].update(by_origin)
        if plain:
            from tokenade.core.importer.session_packager import SessionPackager

            origin = SessionPackager()._infer_origin(cookies)
            storage["local"].setdefault(origin, {}).update(plain)
        return storage

    @staticmethod
    def _product_url_for_site(site_name: str, cookies: List[Dict]) -> str:
        """Best-effort product URL for launch/proxy (same map as TUI sessions)."""
        try:
            from tokenade.tui.views.sessions import _SITE_URL_MAP

            if site_name and site_name in _SITE_URL_MAP:
                return _SITE_URL_MAP[site_name]
            mapped = _SITE_URL_MAP.get((site_name or "").lower())
            if mapped:
                return mapped
        except Exception:
            pass
        for c in cookies or []:
            domain = (c.get("domain") or "").lstrip(".")
            if domain:
                return f"https://{domain}"
        return ""

    @staticmethod
    def _build_session(cookies: List[Dict], local_storage: Dict, source_format: str) -> Dict:
        """Build a mature v3 .tokenade session via SessionPackager."""
        from datetime import datetime, timezone

        cookies = [FormatImporter._normalize_cookie(c) for c in (cookies or [])]
        cookies = [c for c in cookies if c.get("name")]
        ls = local_storage or {}
        storage = FormatImporter._storage_from_flat(ls, cookies)

        try:
            from tokenade.core.importer.session_packager import SessionPackager

            packager = SessionPackager()
            package = packager.package(
                cookies=cookies,
                browser="converted",
                profile=source_format,
                storage=storage if (storage.get("local") or storage.get("session")) else None,
                local_storage=None,
                metadata={
                    "extraction_method": f"import_{source_format}",
                    "source_format": source_format,
                    "converted": True,
                },
            )
            site = package.get("site_name") or "unknown"
            product_url = FormatImporter._product_url_for_site(site, cookies)
            if product_url:
                package.setdefault("metadata", {})["product_url"] = product_url
            # v3 uses storage only — drop legacy top-level local_storage if empty
            package.pop("local_storage", None)
            package = packager._normalize_legacy(package)
            # After normalize, keep storage canonical; strip empty legacy key
            if not package.get("local_storage"):
                package.pop("local_storage", None)
            return package
        except Exception:
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            site = "unknown"
            try:
                from tokenade.core.importer.session_packager import SessionPackager

                site = SessionPackager().detect_site(cookies) or "unknown"
            except Exception:
                pass
            product_url = FormatImporter._product_url_for_site(site, cookies)
            return {
                "version": "3.0",
                "created_at": now,
                "source_device": {
                    "browser": "converted",
                    "profile": source_format,
                    "platform": "unknown",
                    "hostname": "anonymous",
                },
                "site_name": site,
                "auth_status": "unknown",
                "cookies": cookies,
                "tokens": [],
                "storage": storage,
                "fingerprint": None,
                "tls_profile": None,
                "oauth_config": None,
                "metadata": {
                    "extraction_method": f"import_{source_format}",
                    "source_format": source_format,
                    "converted": True,
                    "cookie_count": len(cookies),
                    "critical_cookie_count": 0,
                    "local_storage_count": sum(len(v) for v in storage.get("local", {}).values()),
                    "session_storage_count": 0,
                    **({"product_url": product_url} if product_url else {}),
                },
            }

    @classmethod
    def convert_file(
        cls,
        input_path: str,
        output_path: str,
        *,
        format_hint: str = "auto",
        encrypt: Optional[bool] = False,
        domain: str = "",
    ) -> Dict:
        """Convert a cookie/storage file into a .tokenade session.

        Returns dict with success, output_path, cookie_count, site_name, format, error.
        """
        path = Path(input_path).expanduser()
        if not path.exists():
            return {
                "success": False,
                "error": f"File not found: {input_path}",
                "output_path": None,
            }

        fmt = (format_hint or "auto").lower().strip()
        if fmt in ("", "auto", "detect"):
            fmt = cls.detect_format(str(path))
        if fmt == "unknown":
            return {
                "success": False,
                "error": (
                    "Could not detect format. Choose one of: "
                    + ", ".join(SUPPORTED_FORMATS[1:])
                ),
                "output_path": None,
            }

        # Aliases
        aliases = {
            "editthiscookie": "cookie-editor",
            "cookie_editor": "cookie-editor",
            "cookieeditor": "cookie-editor",
            "storage_state": "playwright",
            "storagestate": "playwright",
            "cookie_header": "header",
            "cookie-header": "header",
            "setcookie": "set-cookie",
            "set_cookie": "set-cookie",
        }
        fmt = aliases.get(fmt, fmt)

        try:
            if fmt == "playwright":
                session = cls.from_playwright_storagestate(str(path))
            elif fmt in ("netscape", "curl"):
                session = cls.from_netscape(str(path))
                if fmt == "curl":
                    session.setdefault("metadata", {})["source_format"] = "curl"
            elif fmt in (
                "json",
                "puppeteer",
                "cookie-editor",
                "editthiscookie",
                "cypress",
                "selenium",
            ):
                session = cls.from_json(str(path))
                session.setdefault("metadata", {})["source_format"] = fmt
            elif fmt == "header":
                session = cls.from_header_file(str(path), domain=domain)
            elif fmt == "set-cookie":
                session = cls.from_set_cookie_file(str(path), domain=domain)
            elif fmt == "har":
                session = cls.from_har(str(path))
            elif fmt == "csv":
                session = cls.from_csv(str(path))
            else:
                return {
                    "success": False,
                    "error": f"Unsupported format: {fmt}",
                    "output_path": None,
                }
        except Exception as e:
            return {"success": False, "error": str(e), "output_path": None}

        cookies = session.get("cookies") or []
        if not cookies:
            return {
                "success": False,
                "error": "No cookies found in file",
                "output_path": None,
                "format": fmt,
            }

        # Optional domain fill for header imports
        if domain:
            for c in cookies:
                if not c.get("domain"):
                    c["domain"] = domain

        # Re-package so convert always yields mature v3
        try:
            ls = None
            if isinstance(session.get("storage"), dict):
                ls = session["storage"].get("local")
            if not ls:
                ls = session.get("local_storage") or {}
            session = cls._build_session(cookies, ls or {}, fmt)
            session.setdefault("metadata", {})["source_format"] = fmt
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to package session: {e}",
                "output_path": None,
                "format": fmt,
            }

        out = Path(output_path).expanduser()
        if not out.suffix:
            out = out.with_suffix(".tokenade")
        try:
            from tokenade.core.importer.session_packager import SessionPackager

            packager = SessionPackager()
            if not packager.validate_format(session):
                return {
                    "success": False,
                    "error": "Packaged session failed format validation",
                    "output_path": None,
                    "format": fmt,
                }
            saved = packager.save(session, str(out), encrypt=encrypt)
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to save session: {e}",
                "output_path": None,
                "format": fmt,
            }

        site = session.get("site_name") or "unknown"
        return {
            "success": True,
            "output_path": saved,
            "cookie_count": len(session.get("cookies") or cookies),
            "site_name": site,
            "format": fmt,
            "auth_status": session.get("auth_status"),
            "version": session.get("version"),
            "product_url": (session.get("metadata") or {}).get("product_url"),
        }
