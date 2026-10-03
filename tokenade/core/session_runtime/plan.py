"""
Runtime plan - One builder for launch/load browser configuration.

Precedence (highest first): explicit CLI overrides > site-handler plugin
adjusters > jar embedded values > provider/oracle defaults.

The builder never opens browsers, sockets, or tunnels. It consumes:
  package:        the loaded .tokenade jar dict
  tunnel:         duck-typed tunnel state (or None):
                    {"local_proxy": {"server": "http://127.0.0.1:PORT"},
                     "oracle": {"mode": "live"|"snapshot"|"off", ...},
                     "egress_echo": {"country","asn","ip_hash"}}
  cli_overrides:  {"fingerprint": dict, "proxy": dict, "stealth_level": str,
                   "tunnel": "auto"|"off"|provider-name,
                   "tunnel_allow_unpaired": bool, "geolocation": {lat,lng},
                   "extra_args": [str]}
  plugin_adjusters: ordered list of callables(plan) -> None (site handlers).
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from tokenade.core.session_runtime.oracle_snapshot import verify_snapshot
from tokenade.core.session_runtime.policy import (
    EgressCheckError,
    enforce_egress,
    resolve_policy,
)
from tokenade.core.session_runtime.webrtc import webrtc_lockdown_args

logger = logging.getLogger(__name__)

TUNNEL_AUTO = "auto"
TUNNEL_OFF = "off"

# Fingerprint-oracle query allowlist, deny-by-default. Scalar/metadata probes
# only — render-readback methods (toDataURL, getImageData, readPixels,
# OfflineAudioContext sums) are NEVER forwarded; they use local deterministic
# perturbation instead (see plan doc §3.2).
ORACLE_ALLOWLIST = [
    "navigator.userAgent",
    "navigator.platform",
    "navigator.language",
    "navigator.languages",
    "navigator.hardwareConcurrency",
    "navigator.deviceMemory",
    "navigator.maxTouchPoints",
    "navigator.webdriver",
    "navigator.plugins",
    "navigator.mimeTypes",
    "screen.width",
    "screen.height",
    "screen.colorDepth",
    "screen.availWidth",
    "screen.availHeight",
    "window.devicePixelRatio",
    "window.innerWidth",
    "window.innerHeight",
    "Intl.timeZone",
    "Intl.locale",
    "webgl.vendor",
    "webgl.renderer",
    "fonts.list",
]


def build_oracle_bootstrap_script(allowlist: List[str]) -> str:
    """Build the init script that exposes the oracle query stub.

    The stub queues calls in window.__tokenade_fpq_queue until the tunnel
    consumer replaces window.__tokenade_fpq with the live transport (a
    second init script appended after this one). Unknown methods throw
    immediately — deny-by-default is enforced in-page as well as server-side.
    """
    import json

    allowed = json.dumps(sorted(set(allowlist)))
    return (
        "(function() {\n"
        "  if (window.__tokenade_fpq) return;\n"
        f"  const ALLOWED = new Set({allowed});\n"
        "  const queue = [];\n"
        "  window.__tokenade_fpq_queue = queue;\n"
        "  window.__tokenade_fpq = function(method, args) {\n"
        "    if (!ALLOWED.has(String(method))) {\n"
        "      throw new Error('[tokenade-oracle] denied: ' + method);\n"
        "    }\n"
        "    return new Promise((resolve, reject) => {\n"
        "      queue.push({method, args: args || null, resolve, reject});\n"
        "    });\n"
        "  };\n"
        "})();"
    )


@dataclass
class RuntimePlan:
    """Concrete browser runtime derived from jar + tunnel + flags."""

    context_kwargs: Dict[str, Any] = field(default_factory=dict)
    init_scripts: List[str] = field(default_factory=list)
    cdp_overrides: Dict[str, Any] = field(default_factory=dict)
    proxy: Optional[Dict[str, str]] = None
    launch_args: List[str] = field(default_factory=list)
    oracle: Dict[str, Any] = field(default_factory=dict)
    policy: Dict[str, Any] = field(default_factory=dict)
    split: Dict[str, Any] = field(default_factory=dict)
    fingerprint_source: str = "none"  # cli | jar | none
    report: Dict[str, Any] = field(default_factory=dict)


class RuntimePlanBuilder:
    """Builds RuntimePlans. Pure function of (jar, tunnel, flags, adjusters)."""

    @staticmethod
    def _fingerprint_dict(package: Dict[str, Any], cli_overrides: Dict[str, Any]):
        if isinstance(cli_overrides.get("fingerprint"), dict):
            return cli_overrides["fingerprint"], "cli"
        jar_fp = package.get("fingerprint")
        if isinstance(jar_fp, dict) and jar_fp:
            return jar_fp, "jar"
        return None, "none"

    def build(
        self,
        package: Dict[str, Any],
        *,
        tunnel: Optional[Dict[str, Any]] = None,
        cli_overrides: Optional[Dict[str, Any]] = None,
        plugin_adjusters: Optional[List[Callable[[RuntimePlan], None]]] = None,
    ) -> RuntimePlan:
        cli = dict(cli_overrides or {})
        tunnel_mode = str(cli.get("tunnel", TUNNEL_OFF)).lower()
        tunnel_wanted = tunnel_mode != TUNNEL_OFF
        plan = RuntimePlan()

        # --- Policy first: fail closed before touching anything else.
        plan.policy = resolve_policy(package)
        if tunnel_wanted and not isinstance(package.get("egress"), dict):
            if not cli.get("tunnel_allow_unpaired"):
                raise EgressCheckError(
                    "Tunnel requested but jar has no egress block. "
                    "Export with --with-egress (or pair the jar) so the "
                    "circuit can be verified; refusing to proceed."
                )
            plan.policy = {"required": False, "fallback": "warn"}

        # --- Fingerprint → native tier (Playwright context options, CDP-level).
        fp_dict, plan.fingerprint_source = self._fingerprint_dict(package, cli)
        if fp_dict:
            try:
                from tokenade.core.fingerprint.manager import BrowserFingerprint

                fields = set(BrowserFingerprint.__dataclass_fields__)
                clean = {k: v for k, v in fp_dict.items() if k in fields}
                fp = BrowserFingerprint.from_dict(clean)
                plan.context_kwargs.update(fp.to_playwright_context())
                if fp.timezone:
                    plan.cdp_overrides["timezone_id"] = fp.timezone
            except Exception as exc:
                logger.warning("Fingerprint unusable, continuing without it: %s", exc)
                plan.fingerprint_source = "none (unusable)"
                plan.report["fingerprint_error"] = str(exc)

        stealth = cli.get("stealth_level") or "maximum"
        plan.context_kwargs.setdefault("color_scheme", "light")

        # --- Proxy: CLI > tunnel listener > none. Plain HTTP on loopback by
        # design (Chromium cannot do SOCKS5+auth; loopback needs no auth).
        if isinstance(cli.get("proxy"), dict):
            plan.proxy = cli["proxy"]
        elif tunnel and isinstance(tunnel.get("local_proxy"), dict):
            plan.proxy = tunnel["local_proxy"]
        if plan.proxy:
            plan.context_kwargs["proxy"] = {
                "server": plan.proxy["server"],
                **({"username": plan.proxy["username"]} if plan.proxy.get("username") else {}),
                **({"password": plan.proxy["password"]} if plan.proxy.get("password") else {}),
            }

        # --- WebRTC lockdown whenever traffic leaves via proxy/tunnel.
        extra_args = list(cli.get("extra_args") or [])
        if plan.proxy or tunnel:
            extra_args = webrtc_lockdown_args(extra_args)
        plan.launch_args = extra_args

        # --- Geolocation override (explicit only; never guessed).
        geo = cli.get("geolocation")
        if isinstance(geo, dict) and "latitude" in geo and "longitude" in geo:
            plan.cdp_overrides["geolocation"] = {
                "latitude": geo["latitude"],
                "longitude": geo["longitude"],
            }

        # --- Oracle: tunnel live > jar snapshot > off.
        oracle_cfg: Dict[str, Any] = {"mode": "off", "allowlist": list(ORACLE_ALLOWLIST)}
        if tunnel and isinstance(tunnel.get("oracle"), dict):
            oracle_cfg.update(tunnel["oracle"])
        elif isinstance(package.get("oracle_snapshot"), dict):
            ok, reason, age_s = verify_snapshot(package["oracle_snapshot"])
            oracle_cfg = {
                "mode": "snapshot",
                "allowlist": list(ORACLE_ALLOWLIST),
                "snapshot": package["oracle_snapshot"],
                "snapshot_status": reason,
                "snapshot_age_s": age_s,
            }
            if not ok and reason != "valid-stale":
                oracle_cfg["mode"] = "off"
                plan.report["oracle_warning"] = f"snapshot rejected: {reason}"
        if oracle_cfg["mode"] in ("live", "snapshot"):
            plan.init_scripts.append(
                build_oracle_bootstrap_script(oracle_cfg["allowlist"])
            )
        plan.oracle = oracle_cfg

        # --- Split routing: explicit opt-in only; empty list refuses.
        from tokenade.core.session_runtime.split import resolve_split

        plan.split = resolve_split(package, cli.get("tunnel_split"))
        if plan.split["enabled"] and not plan.split["domains"]:
            raise EgressCheckError(
                "Split routing enabled but no domains resolved — refusing, "
                "because an empty list would send EVERYTHING direct."
            )

        # --- Egress self-check when a circuit echo is available.
        if tunnel and isinstance(tunnel.get("egress_echo"), dict):
            hint = package.get("egress", {}).get("origin_hint", {})
            action, message = enforce_egress(tunnel["egress_echo"], hint, plan.policy)
            plan.report["egress_check"] = {"action": action, "message": message}
            if action == "deny":
                raise EgressCheckError(message)
            if action == "warn":
                logger.warning(message)
        elif tunnel_wanted and tunnel is None:
            # Tunnel requested but no circuit was established upstream.
            # The caller (launch/load) opens the circuit; the builder records
            # the expectation so verification cannot be skipped silently.
            plan.report["egress_check"] = {
                "action": "pending",
                "message": "tunnel requested; circuit must be verified before launch",
            }

        # --- Site-handler adjustments last (narrow hook, never transport).
        for adjust in plugin_adjusters or []:
            try:
                adjust(plan)
            except Exception as exc:
                logger.warning("Plugin adjuster failed, ignoring: %s", exc)

        plan.report.update(
            {
                "fingerprint_source": plan.fingerprint_source,
                "stealth_level": stealth,
                "proxy": plan.proxy.get("server") if plan.proxy else None,
                "oracle_mode": plan.oracle.get("mode"),
                "webrtc_lockdown": any(
                    "webrtc" in a.lower() for a in plan.launch_args
                ),
                "split": plan.split,
            }
        )
        return plan
