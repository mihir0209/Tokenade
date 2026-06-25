"""
TLS Fingerprint Matching — impersonate Chrome/Firefox TLS stacks.

Uses curl-cffi to match the TLS fingerprint (JA3/JA4) of real browsers.
This is critical for bypassing Cloudflare and Akamai detection.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

CHROME_FINGERPRINTS = {
    "chrome131": {
        "ciphers": [
            4865, 4866, 4867, 49195, 49199, 49196, 49200, 52393,
            52392, 49171, 49172, 156, 157, 47, 53, 10, 255
        ],
        "extensions": [
            0, 23, 65281, 10, 11, 35, 16, 5, 13, 18, 51, 45, 27, 21, 43, 43690
        ],
        "sig_algorithms": [
            1025, 1281, 1537, 2049, 2053, 2055, 2057, 2059, 2061, 2063,
            2065, 2067, 2069, 2071, 2073, 2075, 2077, 2079, 2081, 2083,
            2085, 2087, 2089, 2091, 2093, 2095, 2097, 2099, 2101
        ],
        "alpn_protocols": ["h2", "http/1.1"],
    },
    "chrome124": {
        "ciphers": [
            4865, 4866, 4867, 49195, 49199, 49196, 49200, 52393,
            52392, 49171, 49172, 156, 157, 47, 53, 10, 255
        ],
        "extensions": [0, 23, 65281, 10, 11, 35, 16, 5, 13, 18, 51, 45, 27, 21],
        "alpn_protocols": ["h2", "http/1.1"],
    },
}

FIREFOX_FINGERPRINTS = {
    "firefox128": {
        "ciphers": [
            4865, 4867, 4866, 49195, 49199, 49196, 49200, 52393,
            52392, 49171, 49172, 156, 157, 47, 53
        ],
        "extensions": [0, 23, 65281, 10, 11, 35, 16, 5, 13, 51, 45, 27, 21],
        "alpn_protocols": ["h2", "http/1.1"],
    },
}


@dataclass
class TLSFingerprintConfig:
    """Configuration for TLS fingerprint impersonation."""
    impersonate: str = "chrome131"
    verify: bool = False
    timeout: int = 30
    proxy: Optional[str] = None
    proxy_auth: Optional[str] = None


class TLSFingerprint:
    """TLS fingerprint matching using curl-cffi."""

    def __init__(self, config: Optional[TLSFingerprintConfig] = None):
        self.config = config or TLSFingerprintConfig()
        self._available = self._check_available()

    def _check_available(self) -> bool:
        """Check if curl-cffi is available."""
        try:
            import curl_cffi  # noqa: F401
            return True
        except ImportError:
            logger.warning("curl-cffi not installed. TLS fingerprint matching unavailable.")
            return False

    @property
    def is_available(self) -> bool:
        return self._available

    def get_available_impersonate_targets(self) -> List[str]:
        """List available impersonation targets."""
        if not self._available:
            return []
        try:
            from curl_cffi.requests import Session
            s = Session()
            return list(s.impersonate_map.keys()) if hasattr(s, 'impersonate_map') else [
                "chrome131", "chrome124", "chrome120", "chrome119",
                "firefox128", "firefox120", "firefox109",
                "safari17_0", "safari15_3", "safari15_5",
            ]
        except Exception:
            return list(CHROME_FINGERPRINTS.keys()) + list(FIREFOX_FINGERPRINTS.keys())

    def fetch(self, url: str, **kwargs) -> Optional[Dict]:
        """Fetch a URL with impersonated TLS fingerprint."""
        if not self._available:
            logger.error("curl-cffi not available for TLS fingerprint matching")
            return None

        try:
            from curl_cffi.requests import Session

            session = Session(
                impersonate=self.config.impersonate,
                verify=self.config.verify,
                timeout=self.config.timeout,
            )

            if self.config.proxy:
                session.proxies = {
                    "http": self.config.proxy,
                    "https": self.config.proxy,
                }

            response = session.get(url, **kwargs)

            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "text": response.text,
                "cookies": dict(response.cookies),
                "impersonate": self.config.impersonate,
            }
        except Exception as e:
            logger.error(f"TLS fingerprint fetch failed: {e}")
            return None

    def test_fingerprint(self, url: str = "https://www.google.com") -> Dict:
        """Test the current TLS fingerprint against a test endpoint."""
        result = self.fetch(url)
        if result is None:
            return {"available": False, "error": "curl-cffi not installed"}

        return {
            "available": True,
            "impersonate": self.config.impersonate,
            "status_code": result["status_code"],
            "success": result["status_code"] == 200,
            "headers": {
                "server": result["headers"].get("server", ""),
                "alt-svc": result["headers"].get("alt-svc", ""),
            },
        }

    def get_ja3_info(self) -> Dict:
        """Get information about the JA3 fingerprint for the current impersonation target."""
        return {
            "impersonate": self.config.impersonate,
            "available": self._available,
            "chrome_fingerprints": list(CHROME_FINGERPRINTS.keys()),
            "firefox_fingerprints": list(FIREFOX_FINGERPRINTS.keys()),
        }

    def auto_select_target(self, session_data: Optional[Dict] = None) -> str:
        """Auto-select the best impersonation target based on session data."""
        if session_data:
            user_agent = session_data.get("user_agent", "")
            if "Firefox" in user_agent:
                return "firefox128"
            if "Edg/" in user_agent:
                return "chrome131"
            if "Chrome/" in user_agent:
                return "chrome131"
        return self.config.impersonate

    def apply_to_session(self, session_data: Dict) -> Dict:
        """Apply TLS fingerprint config to a session data dict."""
        target = self.auto_select_target(session_data)
        session_data["tls_impersonate"] = target
        session_data["tls_available"] = self._available
        return session_data


def get_tls_fingerprint(config: Optional[TLSFingerprintConfig] = None) -> TLSFingerprint:
    """Get a TLS fingerprint instance."""
    return TLSFingerprint(config)
