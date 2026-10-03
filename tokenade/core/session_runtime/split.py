"""
Split routing - Tunnel only the target domains, direct for the rest.

Default tunnel behavior is fail-closed: EVERYTHING rides the circuit. Split
routing is an explicit, per-run opt-in (`--tunnel-split`) for the latency
case: sensitive site traffic egresses from the origin while bulk/utility
traffic (CDNs, fonts, analytics) goes direct.

Matching: case-insensitive suffix match against the domain list
(`example.com` covers `a.example.com`, never `notexample.com`).

Mode "auto" derives the domain list from the jar (cookie domains +
site_name). Mode "manual" uses the CLI list verbatim.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def normalize_domain(host: str) -> str:
    """Lowercase host without port or trailing dot."""
    host = (host or "").strip().lower()
    if host.endswith("."):
        host = host[:-1]
    if ":" in host and not host.startswith("["):
        host = host.rsplit(":", 1)[0]
    return host


def host_in_domains(host: str, domains: List[str]) -> bool:
    """Suffix-match host against domains (exact or subdomain only)."""
    host = normalize_domain(host)
    if not host:
        return False
    for domain in domains:
        domain = normalize_domain(domain)
        if not domain:
            continue
        if host == domain or host.endswith("." + domain):
            return True
    return False


def derive_tunnel_domains(package: Dict[str, Any]) -> List[str]:
    """Derive tunnel domains from a jar (cookie domains + site_name)."""
    domains: List[str] = []
    seen = set()
    for cookie in package.get("cookies", []) or []:
        domain = normalize_domain(str(cookie.get("domain", "") or "").lstrip("."))
        if domain and domain not in seen:
            seen.add(domain)
            domains.append(domain)
    site = normalize_domain(str(package.get("site_name", "") or ""))
    if site and site not in seen and "." in site:
        domains.append(site)
    return domains


def resolve_split(
    package: Dict[str, Any],
    tunnel_split: Optional[str],
) -> Dict[str, Any]:
    """Resolve split config from the --tunnel-split flag value.

    tunnel_split: None/""/"off" → disabled; "auto" → derive from jar;
    otherwise comma-separated domains. Returns
    {"enabled": bool, "domains": [...], "mode": "off"|"auto"|"manual"}.
    """
    flag = (tunnel_split or "").strip().lower()
    if not flag or flag == "off":
        return {"enabled": False, "domains": [], "mode": "off"}
    if flag == "auto":
        domains = derive_tunnel_domains(package)
        return {"enabled": True, "domains": domains, "mode": "auto"}
    domains = [d for d in (normalize_domain(p) for p in flag.split(",")) if d]
    return {"enabled": True, "domains": domains, "mode": "manual"}
