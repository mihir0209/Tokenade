"""
Tokenade Browser - System browser management and CDP connection.
"""

from tokenade.core.browser.undetectable import (
    SystemBrowserLauncher,
    BrowserProcess,
    BrowserLaunchConfig,
)

from tokenade.core.browser.cdp_connection import (
    CDPConnection,
    get_undetectable_stealth_script,
)

from tokenade.core.browser.patcher import (
    ChromePatcher,
    PatchResult,
)

from tokenade.core.browser.stealth import (
    StealthConfig,
    StealthManager,
    build_stealth_script,
)

from tokenade.core.browser.tls_fingerprint import (
    TLSFingerprint,
    TLSFingerprintConfig,
    get_tls_fingerprint,
)

from tokenade.core.browser.dependencies import (
    DependencyChecker,
    check_system_deps,
    install_system_deps,
)

from tokenade.core.browser.cloudflare import (
    CloudflareBypass,
    AkamaiBypass,
    detect_challenge,
    extract_clearance,
    has_clearance,
)

from tokenade.core.browser.captcha import (
    CaptchaType,
    CaptchaChallenge,
    CaptchaSolution,
    CaptchaSolver,
    CaptchaDetector,
    CaptchaManager,
)

__all__ = [
    "SystemBrowserLauncher",
    "BrowserProcess",
    "BrowserLaunchConfig",
    "CDPConnection",
    "get_undetectable_stealth_script",
    "ChromePatcher",
    "PatchResult",
    "StealthConfig",
    "StealthManager",
    "build_stealth_script",
    "TLSFingerprint",
    "TLSFingerprintConfig",
    "get_tls_fingerprint",
    "DependencyChecker",
    "check_system_deps",
    "install_system_deps",
    "CloudflareBypass",
    "AkamaiBypass",
    "detect_challenge",
    "extract_clearance",
    "has_clearance",
    "CaptchaType",
    "CaptchaChallenge",
    "CaptchaSolution",
    "CaptchaSolver",
    "CaptchaDetector",
    "CaptchaManager",
]
