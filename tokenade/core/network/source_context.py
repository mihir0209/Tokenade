"""Privacy-conscious source network stamping."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.request import urlopen


class SourceNetworkError(RuntimeError):
    """Raised when an explicit source-network lookup fails."""


@dataclass(frozen=True)
class SourceNetworkContext:
    captured_at: str
    provider: str
    approx_country: Optional[str] = None
    approx_region: Optional[str] = None
    approx_city: Optional[str] = None
    timezone: Optional[str] = None
    asn: Optional[str] = None
    asn_type: Optional[str] = None
    raw_ip_stored: bool = False
    ip: Optional[str] = None

    def to_dict(self, include_source_ip: bool = False) -> Dict[str, Any]:
        data = {
            "captured_at": self.captured_at,
            "provider": self.provider,
            "approx_country": self.approx_country,
            "approx_region": self.approx_region,
            "approx_city": self.approx_city,
            "timezone": self.timezone,
            "asn": self.asn,
            "asn_type": self.asn_type,
            "raw_ip_stored": bool(include_source_ip and self.ip),
        }
        if include_source_ip and self.ip:
            data["ip"] = self.ip
        return {key: value for key, value in data.items() if value is not None}


def capture_source_network(*, include_source_ip: bool = False, lookup_url: str = "https://ipapi.co/json/") -> Dict[str, Any]:
    """Perform an explicit source-network lookup and return safe metadata."""
    try:
        with urlopen(lookup_url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise SourceNetworkError(f"source network lookup failed: {exc}") from exc

    context = SourceNetworkContext(
        captured_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        provider="tokenade-default-ip-lookup",
        approx_country=_first(payload, "country_code", "country"),
        approx_region=_first(payload, "region", "region_code"),
        approx_city=_first(payload, "city"),
        timezone=_first(payload, "timezone"),
        asn=_first(payload, "asn", "org"),
        asn_type=_first(payload, "asn_type", "type"),
        ip=_first(payload, "ip"),
    )
    return context.to_dict(include_source_ip=include_source_ip)


def _first(payload: Dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None
