"""
Session Loader - Load .tokenade files and inject into target browsers.

Handles:
- Read .tokenade session packages
- Apply target fingerprint with stealth spoofing
- Inject cookies into browser context
- Validate session after injection
- Optional: Load into RuntimeEngine
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

from tokenade.core.browser.manager import BrowserFactory, BrowserConfig
from tokenade.core.fingerprint.manager import FingerprintManager, BrowserFingerprint
from tokenade.core.fingerprint.injector import inject_stealth_script
from tokenade.core.importer.validator import SessionValidator
from tokenade.handlers.base import AuthStatus, SessionData

logger = logging.getLogger(__name__)


def storage_shortfall_message(result):
    """Warning when storage existed but injection fell short, else None.

    Anti-automation pages (discord.com deletes window.localStorage after
    boot) silently drop programmatic storage writes while cookies land
    fine — a cookies-only "success" then misleads. Works for both the
    Playwright ``load()`` result shape (totals vs injected counts) and
    the CDP ``inject_into_cdp_tab`` shape (totals + failed flags).
    """
    gaps = []
    lt = result.get("local_storage_total", 0) or 0
    if lt:
        if result.get("storage_failed_local", False):
            gaps.append("localStorage write failed (%s entries)" % lt)
        elif "local_storage_injected" in result and result["local_storage_injected"] < lt:
            gaps.append(
                "localStorage %s/%s"
                % (result["local_storage_injected"], lt)
            )
    st = result.get("session_storage_total", 0) or 0
    if st:
        if result.get("storage_failed_session", False):
            gaps.append("sessionStorage write failed (%s entries)" % st)
        elif "session_storage_injected" in result and result["session_storage_injected"] < st:
            gaps.append(
                "sessionStorage %s/%s"
                % (result["session_storage_injected"], st)
            )
    if not gaps:
        return None
    return (
        "Storage fell short (%s) — the page may block automation storage "
        "writes (observed on discord.com). Cookies transferred; use the "
        "browser extension Inject for storage-backed auth." % ", ".join(gaps)
    )


class SessionLoader:
    """Loads .tokenade session packages and injects into browsers."""

    def __init__(self, fp_manager: Optional[FingerprintManager] = None):
        """
        Initialize session loader.

        Args:
            fp_manager: Optional fingerprint manager for loading target fingerprints
        """
        self.fp_manager = fp_manager or FingerprintManager()
        self._browser = None
        self._last_result: Optional[Dict] = None

    def load_file(self, file_path: str) -> Dict:
        """
        Load a .tokenade file.

        Args:
            file_path: Path to .tokenade file

        Returns:
            Package dictionary
        """
        from tokenade.core.importer.session_packager import SessionPackager

        path = Path(file_path)
        package = SessionPackager().load(str(path))

        logger.info(
            f"Loaded session package: {path} ({len(package.get('cookies', []))} cookies)"
        )
        return package

    def apply_fingerprint(
        self,
        browser_manager,
        fingerprint: Optional[Dict] = None,
        stealth_level: str = "maximum",
    ) -> bool:
        """
        Apply fingerprint with stealth spoofing to browser.

        Args:
            browser_manager: Active browser manager
            fingerprint: Fingerprint dict to apply
            stealth_level: Stealth level (basic, advanced, maximum)

        Returns:
            True if injection succeeded
        """
        if not fingerprint:
            logger.info("No fingerprint to apply")
            return True

        try:
            fp = BrowserFingerprint.from_dict(fingerprint)
            inject_stealth_script(browser_manager, fp, stealth_level)
            logger.info(f"Stealth script injected at level: {stealth_level}")
            return True
        except Exception as e:
            logger.warning(f"Failed to inject stealth script: {e}")
            return False

    def inject_cookies(self, browser_manager, cookies: List[Dict]) -> int:
        """
        Inject cookies into browser context.

        Args:
            browser_manager: Active browser manager
            cookies: List of cookies to inject

        Returns:
            Number of cookies successfully injected
        """
        if not cookies:
            logger.warning("No cookies to inject")
            return 0

        injected = 0
        for cookie in cookies:
            try:
                # Ensure required fields
                if "name" not in cookie or "value" not in cookie:
                    logger.debug(f"Skipping invalid cookie: {cookie}")
                    continue

                # Normalize cookie format for Playwright
                normalized = self._normalize_cookie(cookie)
                browser_manager.add_cookies([normalized])
                injected += 1
            except Exception as e:
                logger.debug(f"Failed to inject cookie {cookie.get('name')}: {e}")

        logger.info(f"Injected {injected}/{len(cookies)} cookies")
        return injected

    def inject_local_storage(
        self,
        browser_manager,
        local_storage: Dict[str, str],
        origin: Optional[str] = None,
    ) -> int:
        """
        Inject localStorage into browser context.

        Uses page.evaluate() to call localStorage.setItem() for each key-value pair.
        Must be called after navigating to the target origin.

        Args:
            browser_manager: Active browser manager
            local_storage: Dictionary of {key: value} to inject
            origin: Optional origin URL to navigate to before injection

        Returns:
            Number of localStorage entries successfully injected
        """
        if not local_storage:
            logger.info("No localStorage to inject")
            return 0

        # Navigate to origin if specified
        if origin:
            try:
                browser_manager.navigate(
                    origin, wait_until="domcontentloaded", timeout=15000
                )
                logger.info(f"Navigated to origin for localStorage injection: {origin}")
            except Exception as e:
                logger.warning(f"Failed to navigate to origin {origin}: {e}")

        injected = 0
        try:
            # Batch inject all localStorage entries
            # Use page.evaluate with a data parameter to avoid serialization issues
            result = browser_manager.evaluate_with_arg(
                """
                (data) => {
                    let count = 0;
                    for (const [key, value] of Object.entries(data)) {
                        try {
                            localStorage.setItem(key, value);
                            count++;
                        } catch (e) {
                            console.error('localStorage setItem failed for key:', key, e);
                        }
                    }
                    return count;
                }
            """,
                local_storage,
            )

            if isinstance(result, int):
                injected = result
            else:
                # Fallback: inject one by one
                for key, value in local_storage.items():
                    try:
                        browser_manager.evaluate_with_arg(
                            """
                            (entry) => {
                                localStorage.setItem(entry[0], entry[1]);
                            }
                        """,
                            [key, value],
                        )
                        injected += 1
                    except Exception as e:
                        logger.debug(f"Failed to inject localStorage key {key}: {e}")

        except Exception as e:
            logger.error(f"Failed to inject localStorage: {e}")

        logger.info(f"Injected {injected}/{len(local_storage)} localStorage entries")
        return injected

    def inject_session_storage(
        self,
        browser_manager,
        session_storage: Dict[str, str],
        origin: Optional[str] = None,
    ) -> int:
        """Inject sessionStorage into browser context."""
        if not session_storage:
            logger.info("No sessionStorage to inject")
            return 0

        if origin:
            try:
                browser_manager.navigate(
                    origin, wait_until="domcontentloaded", timeout=15000
                )
                logger.info(f"Navigated to origin for sessionStorage injection: {origin}")
            except Exception as e:
                logger.warning(f"Failed to navigate to origin {origin}: {e}")

        injected = 0
        try:
            result = browser_manager.evaluate_with_arg(
                """
                (data) => {
                    let count = 0;
                    for (const [key, value] of Object.entries(data)) {
                        try {
                            sessionStorage.setItem(key, value);
                            count++;
                        } catch (e) {
                            console.error('sessionStorage setItem failed for key:', key, e);
                        }
                    }
                    return count;
                }
            """,
                session_storage,
            )

            if isinstance(result, int):
                injected = result
            else:
                for key, value in session_storage.items():
                    try:
                        browser_manager.evaluate_with_arg(
                            """
                            (entry) => {
                                sessionStorage.setItem(entry[0], entry[1]);
                            }
                        """,
                            [key, value],
                        )
                        injected += 1
                    except Exception as e:
                        logger.debug(f"Failed to inject sessionStorage key {key}: {e}")
        except Exception as e:
            logger.error(f"Failed to inject sessionStorage: {e}")

        logger.info(f"Injected {injected}/{len(session_storage)} sessionStorage entries")
        return injected

    def inject_indexeddb(self, browser_manager, idb_data: Dict[str, Any]) -> int:
        """Inject IndexedDB object stores and key-value records via browser evaluation."""
        if not idb_data or browser_manager is None:
            return 0

        script = """
        async (databases) => {
            let totalRecords = 0;
            for (const [dbName, dbSpec] of Object.entries(databases)) {
                try {
                    const version = dbSpec.version || 1;
                    const stores = dbSpec.stores || {};
                    await new Promise((resolve, reject) => {
                        const req = indexedDB.open(dbName, version);
                        req.onupgradeneeded = (e) => {
                            const db = e.target.result;
                            for (const storeName of Object.keys(stores)) {
                                if (!db.objectStoreNames.contains(storeName)) {
                                    db.createObjectStore(storeName);
                                }
                            }
                        };
                        req.onsuccess = (e) => {
                            const db = e.target.result;
                            const tx = db.transaction(Object.keys(stores), "readwrite");
                            for (const [storeName, records] of Object.entries(stores)) {
                                const store = tx.objectStore(storeName);
                                for (const [k, v] of Object.entries(records)) {
                                    store.put(v, k);
                                    totalRecords++;
                                }
                            }
                            tx.oncomplete = () => { db.close(); resolve(); };
                            tx.onerror = () => { db.close(); reject(tx.error); };
                        };
                        req.onerror = () => reject(req.error);
                    });
                } catch (e) {
                    console.warn("IndexedDB injection error:", e);
                }
            }
            return totalRecords;
        }
        """
        try:
            res = browser_manager.evaluate_with_arg(script, idb_data)
            return res if isinstance(res, int) else 0
        except Exception as e:
            logger.error(f"Failed to inject IndexedDB: {e}")
            return 0

    def _normalize_cookie(self, cookie: Dict) -> Dict:
        """Normalize cookie dict to Playwright format.

        Handles differences between browser cookie formats:
        - Firefox stores expires in milliseconds, Playwright expects seconds
        - Session cookies (expires=0 or missing) should omit the expires field
        - sameSite='None' requires secure=True per Playwright spec
        - Boolean fields may be stored as strings "False"/"True" after round-trip
        """
        normalized = {
            "name": cookie["name"],
            "value": cookie["value"],
            "domain": cookie.get("domain", ""),
            "path": cookie.get("path", "/"),
        }

        secure = _parse_bool(cookie.get("secure"))
        http_only = _parse_bool(cookie.get("httpOnly"))
        same_site = cookie.get("sameSite", "")

        # Fix expires: Firefox uses milliseconds, Playwright expects seconds
        expires = cookie.get("expires")
        if expires and int(expires) > 0:
            expires_int = int(expires)
            # If value looks like milliseconds (> year 2010 in ms = 1262304000000)
            if expires_int > 1262304000000:
                expires_int = expires_int // 1000
            # Only include if it's a valid future-ish timestamp
            if expires_int > 0:
                normalized["expires"] = expires_int

        # Playwright requires secure=True when sameSite='None'
        if same_site == "None":
            secure = True

        if secure:
            normalized["secure"] = True
        if http_only:
            normalized["httpOnly"] = True
        if same_site:
            normalized["sameSite"] = same_site

        return normalized

    async def inject_into_cdp_tab(
        self,
        tab_ws_url: str,
        cookies: List[Dict],
        local_data: Optional[Dict[str, str]] = None,
        session_data: Optional[Dict[str, str]] = None,
        url: Optional[str] = None,
        stealth_script: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Inject stealth script, normalized cookies, and web storage into a CDP tab."""
        import asyncio
        import json
        import time
        import websockets

        msg_id_counter = [0]

        async def cdp_cmd(ws, method, params=None):
            msg_id_counter[0] += 1
            current_id = msg_id_counter[0]
            msg = {"id": current_id, "method": method}
            if params:
                msg["params"] = params
            await ws.send(json.dumps(msg))
            deadline = time.time() + 30
            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(
                        ws.recv(),
                        timeout=min(5, deadline - time.time()),
                    )
                except asyncio.TimeoutError:
                    continue
                data = json.loads(raw)
                if "id" in data and data["id"] == current_id:
                    if "error" in data:
                        raise RuntimeError(data["error"].get("message", "CDP error"))
                    return data.get("result", {})
            raise RuntimeError(f"CDP timeout: {method}")

        tab_ws = await websockets.connect(
            tab_ws_url,
            max_size=10 * 1024 * 1024,
            ping_interval=30,
            ping_timeout=10,
        )
        try:
            if stealth_script:
                try:
                    await cdp_cmd(tab_ws, "Page.enable")
                    await cdp_cmd(
                        tab_ws,
                        "Page.addScriptToEvaluateOnNewDocument",
                        {"source": stealth_script},
                    )
                except Exception as _stealth_err:
                    logger.debug(f"Stealth inject skipped in tab: {_stealth_err}")

            cdp_cookies = []
            for cookie in cookies:
                name = cookie.get("name") or ""
                if not name:
                    continue
                domain = cookie.get("domain") or ""
                if not domain and not cookie.get("url"):
                    continue
                cdp_cookie = {
                    "name": name,
                    "value": str(cookie.get("value", "")),
                    "path": cookie.get("path") or "/",
                }
                if domain:
                    cdp_cookie["domain"] = domain
                elif cookie.get("url"):
                    cdp_cookie["url"] = cookie["url"]
                if cookie.get("secure"):
                    cdp_cookie["secure"] = True
                if cookie.get("httpOnly"):
                    cdp_cookie["httpOnly"] = True
                if cookie.get("sameSite"):
                    same_site = str(cookie["sameSite"])
                    ss_map = {
                        "strict": "Strict",
                        "lax": "Lax",
                        "none": "None",
                        "no_restriction": "None",
                        "unspecified": "Lax",
                    }
                    same_site = ss_map.get(same_site.lower(), same_site)
                    if same_site in ("Strict", "Lax", "None"):
                        cdp_cookie["sameSite"] = same_site
                expires = cookie.get("expires", 0) or 0
                try:
                    exp = int(float(expires))
                except (TypeError, ValueError):
                    exp = 0
                if exp > 0:
                    if exp > 1262304000000:
                        exp = exp // 1000
                    if exp > time.time():
                        cdp_cookie["expires"] = exp
                if cdp_cookie.get("sameSite") == "None" and not cdp_cookie.get("secure"):
                    cdp_cookie["secure"] = True
                if name.startswith("__Host-"):
                    cdp_cookie["secure"] = True
                    cdp_cookie["path"] = "/"
                    cdp_cookie.pop("domain", None)
                    if not cdp_cookie.get("url"):
                        host = (domain or "").lstrip(".")
                        if host:
                            cdp_cookie["url"] = f"https://{host}/"
                elif name.startswith("__Secure-"):
                    cdp_cookie["secure"] = True
                cdp_cookies.append(cdp_cookie)

            await cdp_cmd(tab_ws, "Network.enable")
            injected = 0
            failed = 0
            try:
                await cdp_cmd(tab_ws, "Network.setCookies", {"cookies": cdp_cookies})
                injected = len(cdp_cookies)
            except Exception:
                for cdp_cookie in cdp_cookies:
                    try:
                        await cdp_cmd(tab_ws, "Network.setCookie", cdp_cookie)
                        injected += 1
                    except Exception:
                        failed += 1

            if injected == 0 and cdp_cookies:
                raise RuntimeError(f"Failed to inject any of {len(cdp_cookies)} cookies")

            local_data = local_data or {}
            session_data = session_data or {}
            current_origin = None
            if url:
                try:
                    from urllib.parse import urlparse

                    parsed = urlparse(url)
                    if parsed.scheme and parsed.netloc:
                        current_origin = f"{parsed.scheme}://{parsed.netloc}"
                except Exception:
                    pass

            # Anti-automation pages (discord.com) delete window.localStorage
            # after boot: post-load writes fail while document-start scripts
            # still land. Track write failures so callers can warn instead
            # of reporting a cookies-only load as fully successful.
            storage_failed_local = False
            storage_failed_session = False

            def _storage_write_failed(cdp_result):
                # cdp_cmd already raises on protocol errors, so anything
                # reaching here is a result payload: a page-level exception
                # (anti-automation storage deletion) shows up as
                # exceptionDetails or an error-typed inner result.
                if not isinstance(cdp_result, dict):
                    return True
                if cdp_result.get("exceptionDetails"):
                    return True
                inner = cdp_result.get("result") or {}
                return inner.get("subtype") == "error"

            if local_data or session_data:
                init_storage = json.dumps({
                    "origin": current_origin,
                    "local": local_data,
                    "session": session_data,
                })
                await cdp_cmd(tab_ws, "Page.addScriptToEvaluateOnNewDocument", {
                    "source": (
                        f"(function(){{const d={init_storage};"
                        "if(d.origin&&location.origin!==d.origin)return;"
                        "try{Object.entries(d.local).forEach(([k,v])=>localStorage.setItem(k,v));}catch(e){}"
                        "try{Object.entries(d.session).forEach(([k,v])=>sessionStorage.setItem(k,v));}catch(e){}"
                        "}})();"
                    ),
                })

            page_title = ""
            final_url = ""
            if url:
                await cdp_cmd(tab_ws, "Page.navigate", {"url": url})
                await asyncio.sleep(2)

                if local_data:
                    ls_json = json.dumps(local_data)
                    try:
                        ls_res = await cdp_cmd(tab_ws, "Runtime.evaluate", {
                            "expression": f"(function(d){{Object.entries(d).forEach(function(e){{localStorage.setItem(e[0],e[1])}})}})({ls_json})",
                            "returnByValue": True,
                        })
                        if _storage_write_failed(ls_res):
                            storage_failed_local = True
                    except Exception:
                        storage_failed_local = True

                if session_data:
                    ss_json = json.dumps(session_data)
                    try:
                        ss_res = await cdp_cmd(tab_ws, "Runtime.evaluate", {
                            "expression": f"(function(d){{Object.entries(d).forEach(function(e){{sessionStorage.setItem(e[0],e[1])}})}})({ss_json})",
                            "returnByValue": True,
                        })
                        if _storage_write_failed(ss_res):
                            storage_failed_session = True
                    except Exception:
                        storage_failed_session = True

                if local_data or session_data:
                    await cdp_cmd(tab_ws, "Page.navigate", {"url": url})
                    await asyncio.sleep(2)

                title_result = await cdp_cmd(
                    tab_ws, "Runtime.evaluate",
                    {"expression": "document.title", "returnByValue": True},
                )
                page_title = title_result.get("result", {}).get("value", "")

                url_result = await cdp_cmd(
                    tab_ws, "Runtime.evaluate",
                    {"expression": "window.location.href", "returnByValue": True},
                )
                final_url = url_result.get("result", {}).get("value", "")

            return {
                "injected_cookies": injected,
                "failed_cookies": failed,
                "total_cookies": len(cdp_cookies),
                "title": page_title,
                "url": final_url,
                "local_storage_total": len(local_data),
                "session_storage_total": len(session_data),
                "storage_failed_local": storage_failed_local,
                "storage_failed_session": storage_failed_session,
            }
        finally:
            await tab_ws.close()

    def validate_session(self, browser_manager, site_config: Dict) -> Dict:
        """
        Validate session using composable validation strategies.

        Strategies are auto-detected from site_config keys:
        - login_indicator_css → CSSIndicatorStrategy
        - auth_gated_url → URLRedirectStrategy
        - api_probe_url → APIProbeStrategy
        - user_content_selectors/text → PageContentStrategy
        - critical_cookies → CookieExpiryStrategy
        - localStorage_keys → LocalStorageStrategy

        Args:
            browser_manager: Active browser manager
            site_config: Site configuration dict

        Returns:
            Combined validation result dict
        """
        validate_url = site_config.get("validate_url")
        wait_seconds = site_config.get("wait_seconds", 10)

        # Navigate to the page first if URL provided
        if validate_url:
            try:
                logger.info(
                    f"Navigating to {validate_url} for validation (wait {wait_seconds}s)"
                )
                browser_manager.navigate(
                    validate_url, wait_until="domcontentloaded", timeout=30000
                )
                time.sleep(wait_seconds)
            except Exception as e:
                logger.warning(f"Navigation failed: {e}")

        # Run composable validator
        validator = SessionValidator()
        return validator.validate(browser_manager, site_config)

    def load(
        self,
        file_path: str,
        target_fp_name: Optional[str] = None,
        stealth_level: str = "maximum",
        validate: bool = True,
        visible: bool = False,
        profile_dir: Optional[str] = None,
        inject_local_storage: bool = True,
        site_config: Optional[Dict] = None,
        acknowledge_exclusive_move: bool = False,
        allow_single_use: bool = False,
        browser_type: str = "cloakbrowser",
        proxy: Optional[Dict[str, str]] = None,
        target_url: Optional[str] = None,
        auto_solve_challenges: Optional[bool] = None,
        capture_solved_sessions: Optional[bool] = None,
        session_output_dir: Optional[str] = None,
        extra_args: Optional[List[str]] = None,
        init_scripts: Optional[List[str]] = None,
    ) -> Dict:
        """
        Complete load workflow: read file, launch browser, inject cookies, validate.

        Args:
            file_path: Path to .tokenade file
            target_fp_name: Optional target fingerprint name
            stealth_level: Stealth level for spoofing
            validate: Whether to validate session after injection
            visible: Show browser window
            profile_dir: Browser profile directory
            inject_local_storage: Whether to inject localStorage if present in package
            site_config: Site configuration dict with validate_url, login_indicator_css, etc.
            browser_type: Browser backend requested from BrowserFactory
            proxy: Optional Playwright proxy configuration
            target_url: Final product URL and storage-origin scope
            extra_args: Optional extra Chromium launch args (e.g. WebRTC lockdown)
            init_scripts: Optional document-start init scripts (e.g. oracle stub)

        Returns:
            Load result dict
        """
        result = {
            "success": False,
            "file": file_path,
            "cookies_injected": 0,
            "cookies_total": 0,
            "local_storage_injected": 0,
            "local_storage_total": 0,
            "session_storage_injected": 0,
            "session_storage_total": 0,
            "validation": {},
            "error": None,
        }

        try:
            # Step 1: Load package
            package = self.load_file(file_path)
            from tokenade.core.artifacts import ProfileArtifactManager

            ProfileArtifactManager.preflight(
                package,
                purpose="load",
                acknowledge_exclusive_move=acknowledge_exclusive_move,
                allow_single_use=allow_single_use,
            )
            result["cookies_total"] = len(package.get("cookies", []))
            result["site_name"] = package.get("site_name", "unknown")
            site_handler_metadata = self._site_handler_metadata(package)
            if site_handler_metadata:
                result["site_handler"] = site_handler_metadata

            # Step 2: Prepare browser config
            config_kwargs = {
                "browser_type": browser_type,
                "headless": not visible,
                "stealth_level": stealth_level,
                "force_playwright": browser_type in ("firefox", "webkit"),
            }
            if proxy:
                config_kwargs["proxy"] = proxy
            if extra_args:
                merged_args = list(config_kwargs.get("args", []) or [])
                for arg in extra_args:
                    if arg.split("=", 1)[0] not in {a.split("=", 1)[0] for a in merged_args}:
                        merged_args.append(arg)
                config_kwargs["args"] = merged_args
            if package.get("profile_artifacts") and not profile_dir:
                import tempfile

                profile_dir = tempfile.mkdtemp(prefix="tokenade-load-artifacts-")
            if profile_dir:
                config_kwargs["user_data_dir"] = profile_dir
            if package.get("profile_artifacts"):
                ProfileArtifactManager.restore(
                    package,
                    profile_dir,
                    browser_type,
                    allow_single_use=allow_single_use,
                )

            # Step 3: Apply target fingerprint if specified
            if target_fp_name:
                fp = self.fp_manager.load(target_fp_name)
                if fp:
                    config_kwargs["fingerprint"] = fp.to_dict()
                    logger.info(f"Using target fingerprint: {target_fp_name}")
                else:
                    logger.warning(f"Fingerprint not found: {target_fp_name}")

            if capture_solved_sessions is not None:
                config_kwargs["capture_solved_sessions"] = capture_solved_sessions
            if auto_solve_challenges is not None:
                config_kwargs["auto_solve_challenges"] = auto_solve_challenges
            if session_output_dir is not None:
                config_kwargs["session_output_dir"] = session_output_dir

            # Step 4: Launch browser
            config = BrowserConfig(**config_kwargs)
            self._browser = BrowserFactory.create(**config.__dict__)
            self._browser.launch()

            # Step 4b: Seed carried Web Storage at document-start so it
            # lands before anti-automation storage deletion. Best-effort:
            # backends without init-script support keep the post-load
            # evaluate path below.
            if inject_local_storage:
                try:
                    seed = self.build_storage_seed_script(package, site_config)
                    add_init = getattr(self._browser, "add_init_script", None)
                    if seed and callable(add_init):
                        add_init(seed)
                        logger.info("Registered document-start storage seed")
                except Exception as e:
                    logger.debug(f"Storage seed skipped: {e}")

            # Step 4c: Register caller-supplied document-start init scripts
            # (e.g. fingerprint-oracle bootstrap). Best-effort per backend.
            for script in init_scripts or []:
                try:
                    add_init = getattr(self._browser, "add_init_script", None)
                    if callable(add_init):
                        add_init(script)
                        logger.info("Registered runtime init script")
                    else:
                        logger.debug("Backend has no init-script support; skipping")
                        break
                except Exception as e:
                    logger.debug(f"Runtime init script skipped: {e}")

            # Step 5: Apply source fingerprint from package (if no target specified)
            if not target_fp_name and package.get("fingerprint"):
                self.apply_fingerprint(
                    self._browser, package["fingerprint"], stealth_level
                )

            # Step 5b: Worker-parity check (best-effort, never fails the load).
            # Makes the add_init_script-vs-Worker gap visible per session:
            # detectors re-read identity in workers, where JS spoofs don't run.
            try:
                from tokenade.core.fingerprint.injector import validate_worker_parity

                result["worker_parity"] = validate_worker_parity(self._browser)
            except Exception as e:
                result["worker_parity"] = {"status": "unknown", "reason": str(e)}

            # Step 6: Inject cookies
            cookies = package.get("cookies", [])
            result["cookies_injected"] = self.inject_cookies(self._browser, cookies)

            # Step 7: Inject localStorage and sessionStorage if present and enabled
            local_storage_by_origin = (
                []
                if ProfileArtifactManager.web_storage_is_superseded(package)
                else self._local_storage_by_origin(package, site_config)
            )
            session_storage_by_origin = (
                []
                if ProfileArtifactManager.web_storage_is_superseded(package)
                else self._session_storage_by_origin(package, site_config)
            )
            if target_url:
                from urllib.parse import urlparse

                target = urlparse(target_url)
                target_origin = (
                    f"{target.scheme}://{target.netloc}"
                    if target.scheme and target.netloc
                    else ""
                )
                local_storage_by_origin = [
                    (origin, entries)
                    for origin, entries in local_storage_by_origin
                    if not origin or origin.rstrip("/") == target_origin.rstrip("/")
                ]
                session_storage_by_origin = [
                    (origin, entries)
                    for origin, entries in session_storage_by_origin
                    if not origin or origin.rstrip("/") == target_origin.rstrip("/")
                ]
            result["local_storage_total"] = sum(
                len(entries) for _, entries in local_storage_by_origin
            )
            result["session_storage_total"] = sum(
                len(entries) for _, entries in session_storage_by_origin
            )
            if inject_local_storage:
                for origin, local_storage in local_storage_by_origin:
                    if not local_storage:
                        continue
                    result["local_storage_injected"] += self.inject_local_storage(
                        self._browser, local_storage, origin=origin
                    )
                for origin, session_storage in session_storage_by_origin:
                    if not session_storage:
                        continue
                    result["session_storage_injected"] += self.inject_session_storage(
                        self._browser, session_storage, origin=origin
                    )

            if inject_local_storage and not local_storage_by_origin:
                local_storage = package.get("local_storage", {})
                origin = self._infer_origin(package, site_config)
                result["local_storage_injected"] = self.inject_local_storage(
                    self._browser, local_storage, origin=origin
                )
            if inject_local_storage and not session_storage_by_origin:
                session_storage = package.get("session_storage", {})
                origin = self._infer_origin(package, site_config)
                result["session_storage_injected"] = self.inject_session_storage(
                    self._browser, session_storage, origin=origin
                )

            if target_url:
                self._browser.navigate(
                    target_url, wait_until="domcontentloaded", timeout=30000
                )

            # Step 8: Validate if requested
            if validate:
                time.sleep(1)
                # Build site_config for validation
                if not site_config:
                    site_config = self._build_default_site_config(package)
                result["validation"] = self.validate_session(self._browser, site_config)
                result["cookies_injected"] > 0
                has_storage = (
                    result["local_storage_injected"] > 0
                    or result["session_storage_injected"] > 0
                )
                result["success"] = (
                    result["validation"].get("valid", False) or has_storage
                )
            else:
                result["success"] = (
                    result["cookies_injected"] > 0
                    or result["local_storage_injected"] > 0
                    or result["session_storage_injected"] > 0
                )

            logger.info(f"Session load complete: {result['success']}")

        except Exception as e:
            error_msg = str(e).lower()
            hint = ""
            if "no such file" in error_msg or "file not found" in error_msg:
                hint = f" Session file not found: {file_path}"
            elif "json" in error_msg or "decode" in error_msg:
                hint = f" Invalid .tokenade file format: {file_path}"
            elif "browser" in error_msg and (
                "launch" in error_msg or "start" in error_msg
            ):
                hint = f" Install browser: playwright install {browser_type}"
            elif "permission denied" in error_msg:
                hint = f" Check file permissions for: {file_path}"

            logger.error(f"Session load failed: {e}{hint}")
            result["error"] = str(e)

        finally:
            self._last_result = result
            # Keep browser open for interactive --visible loads; headless/batch closes.
            if self._browser and not visible:
                try:
                    self._browser.close()
                    self._browser = None
                except Exception:
                    pass

        return result

    def build_storage_seed_script(
        self,
        package: Dict,
        site_config: Optional[Dict] = None,
    ) -> Optional[str]:
        """Build a document-start init script seeding carried Web Storage.

        Returns None when the package carries no storage. The script applies
        entries only on matching origins and tolerates missing storage APIs,
        so it is safe to register unconditionally. This is the only hook
        that precedes anti-automation storage deletion (discord.com).
        """
        pairs = self._local_storage_by_origin(package, site_config)
        spairs = self._session_storage_by_origin(package, site_config)
        if not pairs and not spairs:
            return None
        payload = json.dumps({
            "local": {o or "": e for o, e in pairs},
            "session": {o or "": e for o, e in spairs},
        })
        return (
            "(function(){try{var d=" + payload + ";"
            "var origins=Object.keys(d.local).concat(Object.keys(d.session));"
            "var ok=origins.some(function(o){return o&&location.origin===o;});"
            "if(!ok)return;"
            "var L=d.local[location.origin]||{},S=d.session[location.origin]||{};"
            "if(typeof localStorage!=='undefined'){"
            "Object.entries(L).forEach(function(e){"
            "try{localStorage.setItem(e[0],typeof e[1]==='string'?e[1]:JSON.stringify(e[1]))}catch(_){}});}"
            "if(typeof sessionStorage!=='undefined'){"
            "Object.entries(S).forEach(function(e){"
            "try{sessionStorage.setItem(e[0],typeof e[1]==='string'?e[1]:JSON.stringify(e[1]))}catch(_){}});}"
            "}catch(_){}})();"
        )

    def _local_storage_by_origin(
        self,
        package: Dict,
        site_config: Optional[Dict] = None,
    ) -> list[tuple[Optional[str], Dict[str, str]]]:
        """Return localStorage entries grouped by exact v3 origin, falling back to legacy flat storage."""
        grouped: list[tuple[Optional[str], Dict[str, str]]] = []
        storage = (
            package.get("storage") if isinstance(package.get("storage"), dict) else {}
        )
        local_by_origin = (
            storage.get("local") if isinstance(storage.get("local"), dict) else {}
        )
        from urllib.parse import urlparse

        cookie_domains = {
            str(cookie.get("domain") or "").lstrip(".").lower()
            for cookie in package.get("cookies", [])
            if cookie.get("domain")
        }
        site_name = str(package.get("site_name") or "").lower()
        if site_name and "." in site_name:
            cookie_domains.add(site_name.lstrip("."))

        for origin, entries in local_by_origin.items():
            if not isinstance(origin, str) or not isinstance(entries, dict) or not entries:
                continue
            if "^partitionKey=" in origin:
                continue
            parsed = urlparse(origin)
            host = (parsed.hostname or "").lower()
            if not parsed.scheme or not host:
                continue
            if cookie_domains and not any(
                host == domain
                or host.endswith(f".{domain}")
                or domain.endswith(f".{host}")
                for domain in cookie_domains
            ):
                continue
            grouped.append((origin, entries))

        if grouped:
            return grouped

        legacy = package.get("local_storage")
        if isinstance(legacy, dict) and legacy:
            grouped.append((self._infer_origin(package, site_config), legacy))
        return grouped

    def _session_storage_by_origin(
        self,
        package: Dict,
        site_config: Optional[Dict] = None,
    ) -> list[tuple[Optional[str], Dict[str, str]]]:
        """Return sessionStorage entries grouped by exact v3 origin, falling back to legacy flat storage."""
        grouped: list[tuple[Optional[str], Dict[str, str]]] = []
        storage = (
            package.get("storage") if isinstance(package.get("storage"), dict) else {}
        )
        session_by_origin = (
            storage.get("session") if isinstance(storage.get("session"), dict) else {}
        )
        from urllib.parse import urlparse

        cookie_domains = {
            str(cookie.get("domain") or "").lstrip(".").lower()
            for cookie in package.get("cookies", [])
            if cookie.get("domain")
        }
        site_name = str(package.get("site_name") or "").lower()
        if site_name and "." in site_name:
            cookie_domains.add(site_name.lstrip("."))

        for origin, entries in session_by_origin.items():
            if not isinstance(origin, str) or not isinstance(entries, dict) or not entries:
                continue
            if "^partitionKey=" in origin:
                continue
            parsed = urlparse(origin)
            host = (parsed.hostname or "").lower()
            if not parsed.scheme or not host:
                continue
            if cookie_domains and not any(
                host == domain
                or host.endswith(f".{domain}")
                or domain.endswith(f".{host}")
                for domain in cookie_domains
            ):
                continue
            grouped.append((origin, entries))

        if grouped:
            return grouped

        legacy = package.get("session_storage")
        if isinstance(legacy, dict) and legacy:
            grouped.append((self._infer_origin(package, site_config), legacy))
        return grouped

    def _infer_origin(
        self, package: Dict, site_config: Optional[Dict] = None
    ) -> Optional[str]:
        """Infer the origin URL from package data or site config for localStorage injection."""
        site_handler = self._site_handler_metadata(package)
        if site_handler:
            origins = site_handler.get("storage_origins") or []
            if origins:
                return origins[0]

        # Try site_config domains first
        if site_config and site_config.get("domains"):
            domains = site_config["domains"]
            for d in domains:
                if not d.startswith("."):
                    return f"https://{d}"

        # Fallback to cookie domains
        cookies = package.get("cookies", [])
        if cookies:
            domain = cookies[0].get("domain", "")
            if domain:
                if not domain.startswith("http"):
                    domain = f"https://{domain.lstrip('.')}"
                return domain

        # Fallback: try to construct from site_name
        site_name = package.get("site_name", "")
        if site_name and site_name != "unknown":
            return f"https://{site_name}.com"

        return None

    def _build_default_site_config(self, package: Dict) -> Dict:
        """Build a minimal site config from package when none provided."""
        site_name = package.get("site_name", "unknown")
        site_handler = self._site_handler_metadata(package)

        # Try to get from site_configs first
        from tokenade.core.importer.site_configs import get_site_config

        preset = get_site_config(site_name)
        if preset:
            return preset

        cookies = package.get("cookies", [])
        domains = []
        if site_handler:
            domains = list(site_handler.get("export_domains") or [])
        if not domains:
            domains = list(
                {c.get("domain", "").lstrip(".") for c in cookies if c.get("domain")}
            )

        auth_cookie_names = []
        for c in cookies:
            name = c.get("name", "")
            if any(
                kw in name.lower() for kw in ("session", "token", "auth", "sid", "csrf")
            ):
                auth_cookie_names.append(name)

        return {
            "name": site_name,
            "domains": domains,
            "critical_cookies": auth_cookie_names[:5] if auth_cookie_names else [],
            "validate_url": None,
            "login_indicator_css": None,
            "wait_seconds": 10,
        }

    def _site_handler_metadata(self, package: Dict) -> Optional[Dict]:
        """Return embedded Site Handler export metadata, if present."""
        metadata = package.get("metadata") or {}
        site_handler = metadata.get("site_handler")
        return site_handler if isinstance(site_handler, dict) else None

    def load_into_runtime(self, file_path: str, runtime_engine=None) -> Dict:
        """
        Load session into RuntimeEngine for API use.

        Args:
            file_path: Path to .tokenade file
            runtime_engine: Optional RuntimeEngine instance

        Returns:
            Load result dict
        """
        result = self.load(file_path, validate=True)

        if not result["success"]:
            logger.error("Cannot load into runtime - session load failed")
            return result

        if runtime_engine:
            try:
                # Load session data into runtime
                package = self.load_file(file_path)
                SessionData(
                    site_name=package.get("site_name", "unknown"),
                    auth_status=AuthStatus(package.get("auth_status", "unknown")),
                    tokens=package.get("tokens", []),
                    cookies=package.get("cookies", []),
                    fingerprint=package.get("fingerprint"),
                )
                # RuntimeEngine would have a method to accept session data
                logger.info("Session loaded into RuntimeEngine")
                result["runtime_loaded"] = True
            except Exception as e:
                logger.error(f"Failed to load into runtime: {e}")
                result["runtime_loaded"] = False
                result["runtime_error"] = str(e)
        else:
            result["runtime_loaded"] = False
            result["runtime_error"] = "No RuntimeEngine provided"

        return result

    def close(self):
        """Close browser if active."""
        if self._browser:
            try:
                self._browser.close()
                self._browser = None
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")

    def get_last_result(self) -> Optional[Dict]:
        """Get result from last load operation."""
        return self._last_result


def _parse_bool(value: Any) -> bool:
    """Parse a value that might be a bool or string "True"/"False" into bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)
