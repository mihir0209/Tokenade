"""
Session Runtime - Centralized launch/load runtime planning.

Single choke point that turns a .tokenade jar (+ tunnel state + CLI flags +
plugin adjustments) into a concrete browser runtime: Playwright context options,
init scripts, CDP overrides, proxy config, and oracle wiring.

Both `tokenade launch` and `tokenade load` must build their browser config
through RuntimePlanBuilder so the two paths cannot drift apart.
"""

from tokenade.core.session_runtime.plan import (
    ORACLE_ALLOWLIST,
    RuntimePlan,
    RuntimePlanBuilder,
    build_oracle_bootstrap_script,
)
from tokenade.core.session_runtime.policy import (
    EgressCheckError,
    enforce_egress,
    resolve_policy,
)
from tokenade.core.session_runtime.split import (
    derive_tunnel_domains,
    host_in_domains,
    normalize_domain,
    resolve_split,
)
from tokenade.core.session_runtime.webrtc import (
    WEBRTC_LOCKDOWN_ARGS,
    webrtc_lockdown_args,
)
from tokenade.core.session_runtime.oracle_snapshot import (
    generate_origin_keypair,
    load_origin_private_key,
    load_origin_public_key,
    origin_key_paths,
    sign_snapshot,
    verify_snapshot,
)

__all__ = [
    "ORACLE_ALLOWLIST",
    "EgressCheckError",
    "RuntimePlan",
    "RuntimePlanBuilder",
    "WEBRTC_LOCKDOWN_ARGS",
    "build_oracle_bootstrap_script",
    "derive_tunnel_domains",
    "enforce_egress",
    "host_in_domains",
    "generate_origin_keypair",
    "load_origin_private_key",
    "load_origin_public_key",
    "normalize_domain",
    "origin_key_paths",
    "resolve_policy",
    "resolve_split",
    "sign_snapshot",
    "verify_snapshot",
    "webrtc_lockdown_args",
]
