"""
SolvedSessionCapturer — persist the artifacts of a successful challenge solve
into a portable .tokenade session file.

After auto-solving an anti-bot challenge (e.g. Cloudflare Managed Challenge),
the origin's cookies (cf_clearance, __cf_bm, ...) and any issued token
(cf-turnstile-response) are packed into a session file. The win becomes
portable: solve once, carry the clearance to another machine.

Capture is deliberately best-effort: it never raises into the browser flow.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def default_session_dir() -> Path:
    """Default directory for captured solved sessions."""
    return Path.home() / ".tokenade" / "sessions"


class SolvedSessionCapturer:
    """Packs a solved page's cookies + tokens into a .tokenade file."""

    def __init__(self, output_dir: Optional[str] = None,
                 encrypt: Optional[bool] = None,
                 packager: Optional[Any] = None):
        """
        Args:
            output_dir: where to write .tokenade files (default ~/.tokenade/sessions).
            encrypt: force encryption on/off; None = config default.
            packager: SessionPackager instance (injected for tests).
        """
        self.output_dir = Path(output_dir).expanduser() if output_dir else default_session_dir()
        self.encrypt = encrypt
        self.packager = packager

    def capture(self, page: Any, url: str, solver_result: Any) -> Optional[Path]:
        """Package the current context's cookies for `url`'s origin into a .tokenade file.

        Args:
            page: Playwright page on the solved site.
            url: the navigated URL (origin determines filename and cookie scope).
            solver_result: PluginResult from the solver (data carries token/method/elapsed).

        Returns:
            Path of the saved session file, or None on failure (never raises).
        """
        try:
            packager = self._get_packager()
            cookies = page.context.cookies(url)
            origin = self._origin_of(url)
            tokens = self._tokens_from(solver_result, origin)
            fingerprint = self._probe_fingerprint(page)
            metadata = self._metadata_from(solver_result)

            package = packager.package(
                cookies,
                browser="cloakbrowser",
                profile="challenge-solve",
                fingerprint=fingerprint,
                tokens=tokens,
                metadata=metadata,
            )
            # Generic clearance cookies can resemble known sites (for example,
            # cf_clearance is also an OpenAI critical cookie). The navigated
            # origin is authoritative for challenge-derived sessions.
            package["site_name"] = origin
            package["metadata"]["target_origin"] = origin
            path = packager.save(
                package,
                str(self.output_dir / f"{origin}.tokenade"),
                encrypt=self.encrypt,
            )
            logger.info("Captured solved session for %s -> %s", origin, path)
            return Path(path)
        except Exception as e:
            logger.warning("Failed to capture solved session for %s: %s", url, e)
            return None

    def _get_packager(self) -> Any:
        if self.packager is None:
            from tokenade.core.importer.session_packager import SessionPackager
            self.packager = SessionPackager()
        return self.packager

    @staticmethod
    def _origin_of(url: str) -> str:
        from urllib.parse import urlparse
        return urlparse(url).netloc

    @staticmethod
    def _tokens_from(solver_result: Any, origin: str) -> List[Dict[str, str]]:
        data = getattr(solver_result, "data", {}) or {}
        token = data.get("token", "")
        if not token:
            return []
        return [{
            "name": "cf-turnstile-response",
            "value": token,
            "origin": origin,
        }]

    @staticmethod
    def _probe_fingerprint(page: Any) -> Optional[Dict[str, Any]]:
        """Best-effort fingerprint from the live page (never raises)."""
        try:
            values = page.evaluate(
                "() => ({"
                "  user_agent: navigator.userAgent,"
                "  platform: navigator.platform,"
                "  languages: navigator.languages,"
                "  hardware_concurrency: navigator.hardwareConcurrency || 0,"
                "})"
            ) or {}
            return {
                "user_agent": values.get("user_agent", ""),
                "platform": values.get("platform", ""),
                "languages": values.get("languages", []),
                "hardware_concurrency": values.get("hardware_concurrency", 0),
            }
        except Exception:
            return None

    @staticmethod
    def _metadata_from(solver_result: Any) -> Dict[str, Any]:
        data = getattr(solver_result, "data", {}) or {}
        return {
            "extraction_method": "challenge_solve",
            "challenge_provider": data.get("provider", ""),
            "challenge_method": data.get("method", "stealth"),
            "solve_elapsed_s": round(float(data.get("elapsed_s", 0)), 2),
        }
