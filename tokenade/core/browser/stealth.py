"""
Backward-compatible wrapper — imports from stealth/manager.py.

This file exists for backward compatibility. All new code should use:
    from tokenade.core.browser.stealth.manager import StealthManager
"""

from tokenade.core.browser.stealth.manager import (  # noqa: F401
    StealthConfig,
    StealthManager,
    build_stealth_script,
    generate_canvas_seed,
    get_canvas_consistency_script,
    get_session_aging_script,
)

__all__ = [
    "StealthConfig",
    "StealthManager",
    "build_stealth_script",
    "generate_canvas_seed",
    "get_canvas_consistency_script",
    "get_session_aging_script",
]
