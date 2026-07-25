"""
Tokenade Python SDK.

Programmatic interface for session management, extraction, and proxy.

Usage:
    from tokenade.sdk import TokenadeClient, SessionProxy

    client = TokenadeClient()
    session = client.extract(browser="chrome", domains=["github.com"])

    # Background CDP proxy (no second CLI process)
    with client.start_proxy(session.session_file, port=9222) as proxy:
        print(proxy.base_url)
        ...
"""
import json
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, List, Union
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Result of a session extraction."""
    success: bool
    session_file: Optional[str] = None
    session_data: Optional[Dict] = None
    cookie_count: int = 0
    error: Optional[str] = None


class SessionProxy:
    """In-process session reverse proxy (CDP by default).

    Starts the same stack as ``tokenade proxy -s …`` without spawning a CLI
    subprocess. Prefer as a context manager so shutdown is reliable::

        with SessionProxy.from_file("gmail.tokenade", port=9222) as p:
            requests.get(p.base_url)
    """

    def __init__(
        self,
        session: Union[str, Path, Dict],
        *,
        port: int = 9222,
        host: str = "127.0.0.1",
        mode: str = "cdp",
        fingerprint: bool = False,
        headless: bool = True,
        timeout: int = 30,
        impersonate: Optional[str] = None,
        background: bool = True,
    ):
        self.session = session
        self.port = port
        self.host = host
        self.mode = mode
        self.fingerprint = fingerprint
        self.headless = headless
        self.timeout = timeout
        self.impersonate = impersonate
        self.background = background
        self._proxy = None
        self._thread: Optional[threading.Thread] = None
        self._error: Optional[BaseException] = None
        self._started = threading.Event()
        self._stop = threading.Event()

    @classmethod
    def from_file(cls, path: Union[str, Path], **kwargs) -> "SessionProxy":
        return cls(str(path), **kwargs)

    @property
    def base_url(self) -> str:
        bind = "127.0.0.1" if self.host in ("0.0.0.0", "::") else self.host
        return f"http://{bind}:{self.port}"

    @property
    def running(self) -> bool:
        return self._started.is_set() and not self._stop.is_set()

    def start(self, *, wait: float = 15.0) -> "SessionProxy":
        """Start the proxy. Blocks briefly until the server is accepting, then
        returns (background thread) or runs until stop (foreground)."""
        if self._started.is_set():
            return self

        if self.mode == "forward":
            self._start_forward(wait=wait)
        elif self.mode in ("cdp", "gui"):
            self._start_cdp(wait=wait)
        else:
            raise ValueError(f"Unsupported proxy mode: {self.mode!r} (use cdp|forward)")

        return self

    def _load_session(self) -> Dict:
        if isinstance(self.session, dict):
            return self.session
        from tokenade.core.importer.session_packager import SessionPackager

        return SessionPackager().load(str(self.session))

    def _start_cdp(self, *, wait: float) -> None:
        from tokenade.core.proxy.cdp_proxy import CDPProxy, CDPProxyConfig

        if self.fingerprint:
            from tokenade.core.runtime.tls_matcher import require_curl_cffi

            require_curl_cffi()

        config = CDPProxyConfig(
            port=self.port,
            host=self.host,
            headless=self.headless,
            timeout=self.timeout,
            use_fingerprint=self.fingerprint,
        )
        self._proxy = CDPProxy(self._load_session(), config)
        if self.impersonate:
            self._proxy._auto_refresh_config["impersonate"] = self.impersonate

        def _run():
            try:
                self._proxy.run()
            except BaseException as exc:
                self._error = exc
                logger.error("SessionProxy CDP failed: %s", exc, exc_info=True)
            finally:
                self._stop.set()

        if self.background:
            self._thread = threading.Thread(target=_run, name="tokenade-session-proxy", daemon=True)
            self._thread.start()
            if not self._wait_port(wait):
                raise RuntimeError(
                    f"SessionProxy did not become ready on {self.base_url}"
                    + (f": {self._error}" if self._error else "")
                )
            self._started.set()
        else:
            self._started.set()
            _run()

    def _start_forward(self, *, wait: float) -> None:
        import asyncio
        from tokenade.core.proxy.forward_proxy import ForwardProxy

        proxy = ForwardProxy(self._load_session(), port=self.port, host=self.host)
        self._proxy = proxy

        def _run():
            try:
                asyncio.run(proxy.start())
            except BaseException as exc:
                self._error = exc
                logger.error("SessionProxy forward failed: %s", exc, exc_info=True)
            finally:
                self._stop.set()

        if self.background:
            self._thread = threading.Thread(target=_run, name="tokenade-forward-proxy", daemon=True)
            self._thread.start()
            if not self._wait_port(wait):
                raise RuntimeError(
                    f"SessionProxy did not become ready on {self.base_url}"
                    + (f": {self._error}" if self._error else "")
                )
            self._started.set()
        else:
            self._started.set()
            _run()

    def _wait_port(self, timeout: float) -> bool:
        import socket
        import time

        deadline = time.time() + max(timeout, 0.1)
        host = "127.0.0.1" if self.host in ("0.0.0.0", "::") else self.host
        while time.time() < deadline:
            if self._error is not None:
                return False
            try:
                with socket.create_connection((host, self.port), timeout=0.25):
                    return True
            except OSError:
                time.sleep(0.1)
        return False

    def stop(self, *, join_timeout: float = 5.0) -> None:
        """Best-effort shutdown of the background proxy thread."""
        self._stop.set()
        proxy = self._proxy
        if proxy is None:
            return
        try:
            if hasattr(proxy, "stop"):
                import asyncio

                maybe = proxy.stop()
                if asyncio.iscoroutine(maybe):
                    try:
                        loop = asyncio.new_event_loop()
                        try:
                            loop.run_until_complete(maybe)
                        finally:
                            loop.close()
                    except Exception:
                        logger.debug("SessionProxy async stop failed", exc_info=True)
        except Exception:
            logger.debug("SessionProxy stop failed", exc_info=True)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=join_timeout)
        self._started.clear()

    def __enter__(self) -> "SessionProxy":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def __del__(self):
        try:
            self.stop(join_timeout=0.5)
        except Exception:
            pass


class TokenadeClient:
    """Main SDK client for Tokenade operations."""

    def __init__(self, sessions_dir: Optional[str] = None):
        self.sessions_dir = Path(sessions_dir or "~/.tokenade/sessions").expanduser()
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._proxies: List[SessionProxy] = []

    def extract(self, browser: str = "chrome", domains: Optional[List[str]] = None,
                profile: Optional[str] = None, output: Optional[str] = None) -> ExtractionResult:
        """Extract cookies from a browser.

        Args:
            browser: Browser name (chrome, firefox, edge, brave)
            domains: Optional domain filter (e.g., ["github.com"])
            profile: Optional profile name
            output: Optional output file path

        Returns:
            ExtractionResult
        """
        from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery
        from tokenade.core.importer.cookie_extractor import CookieExtractor, SiteFilter
        from tokenade.core.importer.session_packager import SessionPackager
        from tokenade.core.importer.cookie_extractor import SITE_DETECTION

        try:
            discovery = BrowserProfileDiscovery()
            profiles = discovery.discover_all()

            browser_profiles = profiles.get(browser, [])
            if not browser_profiles:
                return ExtractionResult(
                    success=False,
                    error=f"No profiles found for {browser}"
                )

            target_profile = browser_profiles[0]
            if profile:
                for p in browser_profiles:
                    if p.name == profile:
                        target_profile = p
                        break

            site_filter = None
            if domains:
                site_names = []
                for domain in domains:
                    for site_name, rules in SITE_DETECTION.items():
                        for pattern in rules["domains"]:
                            clean = pattern.lstrip(".")
                            if domain == clean or domain.endswith("." + clean):
                                site_names.append(site_name)
                                break
                if site_names:
                    site_filter = SiteFilter(list(set(site_names)))

            extractor = CookieExtractor(str(target_profile.path), browser=browser)
            cookies = extractor.extract(site_filter=site_filter)

            if not cookies:
                return ExtractionResult(
                    success=False,
                    error="No cookies extracted"
                )

            packager = SessionPackager()
            session = packager.package(
                cookies=cookies,
                browser=browser,
                profile=target_profile.name,
            )

            if output:
                output_path = output
            else:
                site_name = session.get("site_name", "session")
                output_path = str(self.sessions_dir / f"{site_name}.tokenade")

            packager.save(session, output_path)

            return ExtractionResult(
                success=True,
                session_file=output_path,
                session_data=session,
                cookie_count=len(cookies),
            )

        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return ExtractionResult(
                success=False,
                error=str(e)
            )

    def load(self, session_file: str) -> Optional[Dict]:
        """Load a session file.

        Args:
            session_file: Path to .tokenade file

        Returns:
            Session dictionary or None
        """
        from tokenade.core.importer.session_packager import SessionPackager

        try:
            packager = SessionPackager()
            return packager.load(session_file)
        except Exception as e:
            logger.error(f"Failed to load session: {e}")
            return None

    def health_check(self, session_file: str) -> Dict:
        """Check session health.

        Args:
            session_file: Path to .tokenade file

        Returns:
            Health check result
        """
        from tokenade.core.refresh.health_checker import SessionHealthChecker
        from tokenade.core.refresh.health_scorer import SessionHealthScorer

        try:
            checker = SessionHealthChecker()
            health = checker.check_session(session_file)

            scorer = SessionHealthScorer()
            with open(session_file) as f:
                session = json.load(f)
            score = scorer.score(session)

            return {
                "healthy": health.healthy,
                "health_score": health.health_score,
                "owasp_score": score.total_score,
                "issues": health.issues,
                "recommendations": health.recommendations,
            }

        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
            }

    def share(self, session_file: str, password: Optional[str] = None,
              expiry_hours: int = 24) -> Optional[str]:
        """Create a shareable link.

        Args:
            session_file: Path to .tokenade file
            password: Optional password protection
            expiry_hours: Link expiry in hours

        Returns:
            Share URL or None
        """
        from tokenade.core.importer.session_sharer import SessionSharer, ShareConfig

        try:
            with open(session_file) as f:
                session = json.load(f)

            config = ShareConfig(
                expiry_hours=expiry_hours,
                password_protected=password is not None,
                password=password,
            )

            sharer = SessionSharer()
            share_url, _ = sharer.create_share_link(session, config)
            return share_url
        except Exception as e:
            logger.error(f"Share failed: {e}")
            return None

    def list_sessions(self) -> List[Dict]:
        """List all sessions in the sessions directory.

        Returns:
            List of session metadata
        """
        from tokenade.core.importer.session_manager import SessionManager

        manager = SessionManager(str(self.sessions_dir))
        sessions = manager.list_sessions()

        return [
            {
                "path": s.path,
                "site_name": s.site_name,
                "cookie_count": s.cookie_count,
                "created_at": s.created_at,
                "source_browser": s.source_browser,
            }
            for s in sessions
        ]

    def export_playwright(self, session_file: str, output: str) -> bool:
        """Export session to Playwright storageState format.

        Args:
            session_file: Path to .tokenade file
            output: Output file path

        Returns:
            Success boolean
        """
        from tokenade.core.importer.format_exporter import FormatExporter

        try:
            with open(session_file) as f:
                session = json.load(f)

            exporter = FormatExporter(session)
            storage_state = exporter.to_playwright_storagestate()

            with open(output, "w") as f:
                f.write(storage_state)

            return True
        except Exception as e:
            logger.error(f"Export failed: {e}")
            return False

    def start_proxy(
        self,
        session: Union[str, Path, Dict, ExtractionResult],
        *,
        port: int = 9222,
        host: str = "127.0.0.1",
        mode: str = "cdp",
        fingerprint: bool = False,
        headless: bool = True,
        timeout: int = 30,
        impersonate: Optional[str] = None,
        background: bool = True,
    ) -> SessionProxy:
        """Start a session reverse proxy in-process (no CLI subprocess).

        Equivalent intent to ``tokenade proxy -s session.tokenade`` for
        automation wrappers. Returns a :class:`SessionProxy` that is already
        started when ``background=True`` (default).

        Example::

            client = TokenadeClient()
            with client.start_proxy("gmail.tokenade", port=9222) as proxy:
                # point scrapers / browsers at proxy.base_url
                ...
        """
        if isinstance(session, ExtractionResult):
            if not session.success or not (session.session_file or session.session_data):
                raise ValueError(session.error or "ExtractionResult has no session")
            target: Union[str, Path, Dict] = session.session_file or session.session_data  # type: ignore[assignment]
        else:
            target = session

        proxy = SessionProxy(
            target,
            port=port,
            host=host,
            mode=mode,
            fingerprint=fingerprint,
            headless=headless,
            timeout=timeout,
            impersonate=impersonate,
            background=background,
        )
        proxy.start()
        self._proxies.append(proxy)
        return proxy

    def stop_proxies(self) -> None:
        """Stop all proxies started via :meth:`start_proxy`."""
        while self._proxies:
            proxy = self._proxies.pop()
            try:
                proxy.stop()
            except Exception:
                logger.debug("stop_proxies failed", exc_info=True)
