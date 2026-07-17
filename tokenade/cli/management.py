"""Session management CLI commands.

P1: thin facade — implementations live in tokenade.cli.handlers.*.
External imports of tokenade.cli.management.cmd_* remain valid.

Modules re-exported below so existing tests can patch
``tokenade.cli.management.time`` / helpers without breaking.
"""
import json  # noqa: F401
import logging
import os  # noqa: F401
import sys  # noqa: F401
import time  # noqa: F401 — patched by tests as management.time
from typing import Optional

logger = logging.getLogger("tokenade")

# Infrastructure / CI / misc (already split)
from tokenade.cli.handlers.infrastructure import (  # noqa: F401
    cmd_fleet,
    cmd_container,
    cmd_k8s,
)
from tokenade.cli.handlers.ci import (  # noqa: F401
    cmd_cicd, cmd_ci, cmd_autopsy, cmd_cloak, cmd_tui,
)
from tokenade.cli.handlers.misc import (  # noqa: F401
    cmd_monitor, cmd_analytics, cmd_daemon, _health_bar,
)

# Session + browser ops (P1 split)
from tokenade.cli.handlers.session_ops import (  # noqa: F401
    cmd_sessions,
    cmd_health,
    cmd_health_report,
    cmd_refresh,
    cmd_share,
    cmd_unshare,
    cmd_import,
    cmd_sync,
    cmd_validate_session,
    cmd_encrypted_refresh,
    cmd_refresh_oauth,
    cmd_oauth_config,
    cmd_batch_refresh,
    cmd_versions,
    cmd_rollback,
    cmd_session_diff,
    cmd_logs,
    cmd_mobile_import,
    cmd_clone_profile,
    _resolve_upstream_proxy,
    _run_post_refresh_plugins,
)
from tokenade.cli.handlers.browser_ops import (  # noqa: F401
    cmd_launch,
    cmd_refresh_browser,
    cmd_accounts,
    _refresh_session_cookies,
    _detect_url_from_cookies,
    _accounts_list,
    _accounts_status,
    _accounts_refresh,
)

__all__ = [
    "cmd_sessions", "cmd_health", "cmd_health_report", "cmd_refresh",
    "cmd_share", "cmd_unshare", "cmd_import", "cmd_sync",
    "cmd_monitor", "cmd_analytics", "cmd_daemon",
    "cmd_validate_session", "cmd_encrypted_refresh",
    "cmd_refresh_oauth", "cmd_oauth_config", "cmd_batch_refresh",
    "cmd_launch", "cmd_refresh_browser", "cmd_accounts",
    "cmd_versions", "cmd_rollback", "cmd_session_diff", "cmd_logs",
    "cmd_mobile_import", "cmd_clone_profile",
    "cmd_container", "cmd_k8s", "cmd_fleet",
    "cmd_cicd", "cmd_ci", "cmd_autopsy", "cmd_cloak", "cmd_tui",
    "_resolve_upstream_proxy", "_health_bar",
    "_refresh_session_cookies", "_detect_url_from_cookies",
    "_accounts_list", "_accounts_status", "_accounts_refresh",
    "_run_post_refresh_plugins",
]
