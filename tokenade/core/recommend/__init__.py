"""Internal recommendation engine for Tokenade.

Answers three connected questions for any session/URL/cookie list:

  1. Which **site** is this?        -> ``recommend_site``
  2. Which **plugin** handles it?   -> ``recommend_plugin``
  3. Which **browser binary** runs? -> ``recommend_browser``

The all-in-one entrypoint is ``recommend`` which returns a ``Recommendation``
dataclass carrying ``site`` / ``plugin`` / ``browser`` / ``confidence`` /
``reasons``.

This module is **core internals** — it never installs, downloads, or executes
plugins. It only consults existing catalogs:

  - ``tokenade.core.importer.cookie_extractor.SITE_DETECTION``
  - ``tokenade.core.importer.site_configs`` (runtime catalog incl. ``preferred_plugin``)
  - ``tokenade.handlers.resolve._ALIASES`` (alias normalization)
  - ``tokenade.core.integration.plugin_loader.PluginLoader.list_handlers``
  - ``tokenade.core.config.DEFAULTS['automation_browser']``
  - Each plugin's ``plugin.json`` manifest ``browser.default`` field

It is NOT a marketplace plugin — recommending plugins would be self-referential.
Callers (CLI, SDK, daemon) use it; it does not call them.

See ``docs/adr/0003-internal-recommend-module.md`` for the full design.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- models


@dataclass
class Recommendation:
    """The full site/plugin/browser recommendation for one query."""

    site: Optional[str] = None
    plugin: Optional[str] = None
    browser: Optional[str] = None
    confidence: float = 0.0
    reasons: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "site": self.site,
            "plugin": self.plugin,
            "browser": self.browser,
            "confidence": round(self.confidence, 3),
            "reasons": list(self.reasons),
        }


@dataclass
class RecommendationConfig:
    """Optional knobs for the recommend functions. Defaults read from ~/.tokenade."""

    plugins_dir: Optional[str] = None
    automation_browser_override: Optional[str] = None


# ---------------------------------------------------------------- site


def recommend_site(
    *,
    cookies: Optional[Sequence[Dict[str, Any]]] = None,
    url: Optional[str] = None,
    domains: Optional[Sequence[str]] = None,
    session: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Return a site_name for the given input, or None.

    Resolution order:
      1. ``session.metadata.site_name`` (already specified upstream)
      2. ``SiteFilter.detect_site(cookies)`` (domain match, then critical cookies)
      3. URL host against ``SITE_DETECTION`` domains
      4. Longest unique cookie-domain suffix cross-checked against installed
         site_configs (catches sites not in ``SITE_DETECTION`` but known to
         installed plugins, e.g. chatgpt)
      5. None
    """
    # 1. Session metadata
    if session is not None:
        meta = session.get("metadata") or {}
        existing = meta.get("site_name") or session.get("site_name")
        if existing:
            return _normalize_site_name(existing)

    # 2. Cookie-based detection via existing catalog
    if cookies:
        try:
            from tokenade.core.importer.cookie_extractor import SiteFilter

            detected = SiteFilter().detect_site(list(cookies))
            if detected:
                logger.debug("recommend_site: detect_site=%s", detected)
                return _normalize_site_name(detected)
        except Exception as e:
            logger.debug("recommend_site: detect_site failed: %s", e)

    # 3. URL host against SITE_DETECTION
    if url:
        host = urlparse(url).hostname or url
        site = _match_host_to_site(host)
        if site:
            return site

    # 4. Domains cross-checked against installed site_configs
    domain_list = list(domains or [])
    if not domain_list and cookies:
        domain_list = [c.get("domain", "") for c in cookies if c.get("domain")]
    if domain_list:
        site = _match_domains_to_installed_sites(domain_list)
        if site:
            return site

    return None


def _normalize_site_name(name: str) -> str:
    """Apply known aliases (gh -> github etc.)."""
    return _resolve_alias(name)


def _resolve_alias(name: str) -> str:
    try:
        from tokenade.handlers.resolve import _ALIASES

        return _ALIASES.get(name.lower().strip(), name.lower().strip())
    except Exception:
        return name.lower().strip()


def _match_host_to_site(host: str) -> Optional[str]:
    """Match a single hostname against SITE_DETECTION domain patterns."""
    if not host:
        return None
    try:
        from tokenade.core.importer.cookie_extractor import SITE_DETECTION
    except Exception as e:
        logger.debug("recommend_site: SITE_DETECTION unavailable: %s", e)
        return None

    host = host.lower().lstrip(".")
    for site, rules in SITE_DETECTION.items():
        for pattern in rules.get("domains", []):
            if pattern.startswith("."):
                if host.endswith(pattern):
                    return _normalize_site_name(site)
            elif host == pattern or host.endswith("." + pattern):
                return _normalize_site_name(site)
    return None


def _match_domains_to_installed_sites(domains: Sequence[str]) -> Optional[str]:
    """Look up installed site_configs and SITE_DETECTION; match by domain suffix.

    Catches sites missing from one catalog but present in the other
    (e.g. labs.google defined as a plugin site_config, google.com defined
    in the static ``SITE_DETECTION``).
    """
    if not domains:
        return None

    domain_blob = " ".join(str(d).lower().lstrip(".") for d in domains if d)
    if not domain_blob:
        return None

    best_match = None
    best_score = 0

    def _consider(site_key: str, doms: Sequence[str]) -> None:
        nonlocal best_match, best_score
        for d in doms or []:
            d_clean = str(d).lower().lstrip(".")
            if not d_clean:
                continue
            for inp in domains:
                inp_clean = str(inp).lower().lstrip(".")
                if (
                    inp_clean == d_clean
                    or inp_clean.endswith("." + d_clean)
                    or d_clean.endswith("." + inp_clean)
                ):
                    if best_score < len(d_clean):
                        best_score = len(d_clean)
                        best_match = site_key
                        break

    # installed site_configs (runtime catalog)
    try:
        from tokenade.core.importer.site_configs import list_site_configs

        configs = list_site_configs() or {}
        for site_key, cfg in configs.items():
            _consider(site_key, cfg.get("domains") or [])
    except Exception as e:
        logger.debug("recommend_site: list_site_configs failed: %s", e)

    # static SITE_DETECTION catalog
    try:
        from tokenade.core.importer.cookie_extractor import SITE_DETECTION

        for site_key, rules in SITE_DETECTION.items():
            _consider(site_key, rules.get("domains") or [])
    except Exception as e:
        logger.debug("recommend_site: SITE_DETECTION lookup failed: %s", e)

    if best_match:
        return _normalize_site_name(best_match)
    return None


# ---------------------------------------------------------------- plugin


def recommend_plugin(
    *,
    site: Optional[str] = None,
    url: Optional[str] = None,
    session: Optional[Dict[str, Any]] = None,
    cookies: Optional[Sequence[Dict[str, Any]]] = None,
    domains: Optional[Sequence[str]] = None,
    config: Optional[RecommendationConfig] = None,
) -> Optional[str]:
    """Return a plugin name for the given input, or None.

    Resolution order:
      1. ``site_config.preferred_plugin`` for the resolved site
      2. Multi-site plugin catalog (``sites/<site>.json`` inside a plugin dir)
      3. ``PluginExporter.find_handler(domains)`` filtered to actual site
         handlers (excludes utility plugins masquerading as SiteHandlerPlugin)
      4. ``generic-handler`` catch-all (low confidence)
      5. None
    """
    if site is None:
        site = recommend_site(
            cookies=cookies, url=url, domains=domains, session=session
        )

    # 1. site_config.preferred_plugin
    if site:
        plugin = _lookup_preferred_plugin(site)
        if plugin:
            logger.debug("recommend_plugin: preferred_plugin=%s for site=%s", plugin, site)
            return plugin

    # 2. Multi-site catalog: sites/<site>.json inside any installed plugin dir
    if site:
        plugin = _lookup_multisite_catalog(site, config)
        if plugin:
            logger.debug("recommend_plugin: multisite catalog=%s for site=%s", plugin, site)
            return plugin

    # 3. domains -> handler via existing PluginExporter (filtered)
    domain_list = list(domains or [])
    if not domain_list and cookies:
        domain_list = [c.get("domain", "") for c in cookies if c.get("domain")]
    if url:
        host = urlparse(url).hostname or url
        if host and host not in domain_list:
            domain_list.append(host)

    if domain_list:
        handler = _find_handler_via_exporter(domain_list)
        if handler is not None and _is_real_site_handler(handler):
            name = (
                getattr(handler, "name", None)
                or getattr(handler, "__name__", None)
                or "unknown"
            )
            logger.debug("recommend_plugin: find_handler=%s for domains=%s", name, domain_list)
            return name

    # 4. generic-handler catch-all (if installed and we have a site)
    if site and _is_plugin_installed("generic-handler", config):
        logger.debug("recommend_plugin: generic-handler catch-all for site=%s", site)
        return "generic-handler"

    return None


# "SiteHandlerPlugin" subclasses used as historical-reasons utility helpers
# (their ``can_handle`` returns True for everything; recommend must skip them
# so they don't shadow real site handlers).
_UTILITY_HANDLER_PLUGINS = frozenset({
    "session-backup",
    "session-merge",
})


def _is_real_site_handler(handler: Any) -> bool:
    """Return False for utility-typed SiteHandlerPlugin subclasses."""
    name = (getattr(handler, "name", "") or "").lower()
    if name in _UTILITY_HANDLER_PLUGINS:
        return False
    return True


def _lookup_multisite_catalog(
    site: str, config: Optional[RecommendationConfig]
) -> Optional[str]:
    """Find a plugin that declares ``sites/<site>.json`` in its dir.

    The de-facto multi-site plugin is ``generic-handler`` but the lookup is
    generic so future multi-handler plugins work without code changes.
    """
    try:
        from pathlib import Path
        from tokenade.core.integration.plugin_loader import PluginLoader

        loader = (
            PluginLoader(plugins_dir=config.plugins_dir)
            if config and config.plugins_dir
            else PluginLoader()
        )
        # Check every installed plugin for sites/<site>.json
        plugins_dir = loader.plugins_dir
        target_file = f"{site.lower()}.json"
        for plugin_dir in plugins_dir.iterdir():
            if not plugin_dir.is_dir() or plugin_dir.name.startswith("."):
                continue
            sites_dir = plugin_dir / "sites"
            if not sites_dir.is_dir():
                continue
            if (sites_dir / target_file).is_file():
                # Confirm the plugin.json lists this as type=handler
                manifest = loader.get_manifest(plugin_dir.name)
                if manifest is None:
                    continue
                ptype = (manifest.get("type") or "").lower()
                if ptype in ("handler", "site_handler", ""):
                    return manifest.get("name") or plugin_dir.name
        return None
    except Exception as e:
        logger.debug("recommend_plugin: multisite catalog lookup failed: %s", e)
        return None


def _lookup_preferred_plugin(site: str) -> Optional[str]:
    """Return preferred_plugin from the site's installed site_config, if any."""
    try:
        from tokenade.core.importer.site_configs import get_site_config
    except Exception as e:
        logger.debug("recommend_plugin: site_configs unavailable: %s", e)
        return None

    try:
        cfg = get_site_config(site) or {}
    except Exception as e:
        logger.debug("recommend_plugin: get_site_config(%s) failed: %s", site, e)
        return None

    preferred = cfg.get("preferred_plugin")
    if preferred and _is_plugin_installed(preferred, None):
        return preferred
    return None


def _find_handler_via_exporter(domains: Sequence[str]):
    """Wrap PluginExporter.find_handler so recommend does not import it at module top."""
    try:
        from tokenade.core.importer.plugin_export import PluginExporter

        exporter = PluginExporter()
        return exporter.find_handler(list(domains))
    except Exception as e:
        logger.debug("recommend_plugin: find_handler failed: %s", e)
        return None


def _is_plugin_installed(name: str, config: Optional[RecommendationConfig]) -> bool:
    try:
        from tokenade.core.integration.plugin_loader import PluginLoader

        loader = PluginLoader(
            plugins_dir=config.plugins_dir if config else None
        ) if config and config.plugins_dir else PluginLoader()
        manifest = loader.get_manifest(name)
        return manifest is not None
    except Exception as e:
        logger.debug("recommend_plugin: installed-check failed for %s: %s", name, e)
        return False


# ---------------------------------------------------------------- browser


# Hardcoded per-site overrides. Sites here are known-detectable by
# CloakBrowser-using plugins (Google/Discord flag Chrome via bot-detection).
_SITE_BROWSER_OVERRIDES: Dict[str, str] = {
    "google": "cloak",
    "discord": "cloak",
    "chatgpt": "cloak",
}


def recommend_browser(
    *,
    site: Optional[str] = None,
    plugin: Optional[str] = None,
    session: Optional[Dict[str, Any]] = None,
    config: Optional[RecommendationConfig] = None,
) -> str:
    """Return a browser binary name (cloak / firefox / brave / chrome / ...).

    Resolution order:
      1. ``session.metadata.automation_browser`` (user override at session level)
      2. Plugin manifest ``browser.default`` (per-plugin preference)
      3. Hardcoded per-site override (Google / Discord / ChatGPT -> cloak)
      4. ``config.DEFAULTS['automation_browser']`` (cloak)
    """
    # 1. Session override
    if session is not None:
        meta = session.get("metadata") or {}
        override = meta.get("automation_browser")
        if override:
            return str(override).lower().strip()

    # 2. Plugin manifest browser.default
    if plugin:
        browser = _lookup_plugin_default_browser(plugin, config)
        if browser:
            return browser

    # 3. Per-site override
    if site:
        site_key = site.lower().strip()
        if site_key in _SITE_BROWSER_OVERRIDES:
            return _SITE_BROWSER_OVERRIDES[site_key]

    # 4. Config / CLI override
    if config and config.automation_browser_override:
        return config.automation_browser_override

    # 5. Core config default
    try:
        from tokenade.core.config import DEFAULTS

        return DEFAULTS.get("automation_browser") or "cloak"
    except Exception:
        return "cloak"


def _lookup_plugin_default_browser(
    plugin: str, config: Optional[RecommendationConfig]
) -> Optional[str]:
    try:
        from tokenade.core.integration.plugin_loader import PluginLoader

        loader = (
            PluginLoader(plugins_dir=config.plugins_dir)
            if config and config.plugins_dir
            else PluginLoader()
        )
        manifest = loader.get_manifest(plugin) or {}
        browser_block = manifest.get("browser") or {}
        if isinstance(browser_block, dict):
            default = browser_block.get("default")
            if default:
                return str(default).lower().strip()
    except Exception as e:
        logger.debug("recommend_browser: plugin manifest lookup failed: %s", e)
    return None


# ---------------------------------------------------------------- composite


def recommend(
    *,
    session: Optional[Dict[str, Any]] = None,
    url: Optional[str] = None,
    domains: Optional[Sequence[str]] = None,
    cookies: Optional[Sequence[Dict[str, Any]]] = None,
    config: Optional[RecommendationConfig] = None,
) -> Recommendation:
    """Return a full Recommendation (site + plugin + browser + reasons).

    Pure / no side-effects. Always returns a Recommendation — fields may be
    None when nothing could be resolved.
    """
    reasons: List[str] = []
    confidence = 0.0

    cookies = cookies or (session.get("cookies") if session else None)

    # ── site ──────────────────────────────────────────────────────────
    site = recommend_site(
        cookies=cookies, url=url, domains=domains, session=session
    )
    if session is not None:
        meta = session.get("metadata") or {}
        existing = meta.get("site_name") or session.get("site_name")
        if existing and site == _normalize_site_name(existing):
            source = "metadata.site_name" if meta.get("site_name") else "site_name"
            reasons.append(f"session {source} = {existing!r}")
            confidence += 0.25
        elif site:
            reasons.append(f"site resolved from cookies/domains/url as {site!r}")
            confidence += 0.5
        else:
            reasons.append("site: no resolution (session/cookies/url all matched nothing)")
    elif site:
        if url and not cookies and not domains:
            reasons.append(f"site matched from URL host: {url!r}")
            confidence += 0.4
        elif domains:
            reasons.append(f"site matched from domains: {list(domains)!r}")
            confidence += 0.45
        elif cookies:
            reasons.append(f"site matched from cookies ({len(cookies)} cookies)")
            confidence += 0.55
    else:
        reasons.append("site: no input matched a known site")

    # ── plugin ───────────────────────────────────────────────────────
    plugin = recommend_plugin(
        site=site,
        url=url,
        session=session,
        cookies=cookies,
        domains=domains,
        config=config,
    )
    if plugin:
        preferred = _lookup_preferred_plugin(site) if site else None
        multisite = _lookup_multisite_catalog(site, config) if site else None
        if preferred == plugin:
            reasons.append(f"plugin = {plugin!r} (site_config.preferred_plugin)")
            confidence += 0.25
        elif multisite == plugin:
            reasons.append(
                f"plugin = {plugin!r} (multi-site catalog sites/{site}.json)"
            )
            confidence += 0.2
        elif plugin == "generic-handler":
            reasons.append("plugin = generic-handler (catch-all fallback)")
            confidence += 0.1
        else:
            reasons.append(f"plugin = {plugin!r} (can_handle resolved)")
            confidence += 0.2
    else:
        reasons.append("plugin: no installed handler applies")

    # ── browser ───────────────────────────────────────────────────────
    browser = recommend_browser(site=site, plugin=plugin, session=session, config=config)
    reasons.append(f"browser = {browser!r}")
    if site and _SITE_BROWSER_OVERRIDES.get(site.lower()) == browser:
        reasons.append(f"per-site override ({site} -> {browser})")
        confidence += 0.15
    elif plugin and _lookup_plugin_default_browser(plugin, config) == browser:
        reasons.append(f"plugin manifest browser.default = {browser!r}")
        confidence += 0.15
    else:
        confidence += 0.05  # fell back to config default

    # Cap confidence
    confidence = min(confidence, 1.0)

    return Recommendation(
        site=site,
        plugin=plugin,
        browser=browser,
        confidence=confidence,
        reasons=reasons,
    )


__all__ = [
    "Recommendation",
    "RecommendationConfig",
    "recommend_site",
    "recommend_plugin",
    "recommend_browser",
    "recommend",
]
