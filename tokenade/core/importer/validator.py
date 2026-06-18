"""
Session Validator - Multiple strategies for validating session state.

Each strategy is independent and composable. The validator runs all
configured strategies and combines results.
"""

import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result from a single validation strategy."""
    strategy: str
    valid: bool
    confidence: float  # 0.0 to 1.0
    reason: str
    details: Dict = field(default_factory=dict)


class ValidationStrategy(ABC):
    """Base class for validation strategies."""

    @abstractmethod
    def validate(self, browser_manager, context: Dict) -> ValidationResult:
        """Run validation and return result."""

    @abstractmethod
    def name(self) -> str:
        pass


class CSSIndicatorStrategy(ValidationStrategy):
    """
    Check if a CSS selector matches on the page.
    If the selector matches → element found → likely logged out.
    If no match → element not found → likely logged in.
    """

    def name(self) -> str:
        return "css_indicator"

    def validate(self, browser_manager, context: Dict) -> ValidationResult:
        login_css = context.get("login_indicator_css")
        if not login_css:
            return ValidationResult(
                strategy=self.name(), valid=True, confidence=0.0,
                reason="no login_indicator_css configured"
            )

        try:
            element = browser_manager.query_selector(login_css, timeout=5000)
            found = element is not None
        except Exception:
            found = False

        return ValidationResult(
            strategy=self.name(),
            valid=not found,
            confidence=0.9 if not found else 0.95,
            reason="login indicator not found" if not found else "login indicator found",
            details={"selector": login_css, "element_found": found}
        )


class URLRedirectStrategy(ValidationStrategy):
    """
    Navigate to an auth-gated URL and check the final URL.
    If redirected to a login page → session invalid.
    If stayed on target URL → session valid.

    Config:
        auth_gated_url: URL that requires authentication
        login_page_patterns: list of URL patterns that indicate login page
    """

    def name(self) -> str:
        return "url_redirect"

    def validate(self, browser_manager, context: Dict) -> ValidationResult:
        auth_url = context.get("auth_gated_url")
        login_patterns = context.get("login_page_patterns", [
            "/auth/login", "/signin", "/login", "/sign-in",
            "/accounts/signin", "/auth/authorize",
            "auth0.com/authorize", "login.yahoo.com",
        ])

        if not auth_url:
            return ValidationResult(
                strategy=self.name(), valid=True, confidence=0.0,
                reason="no auth_gated_url configured"
            )

        try:
            browser_manager.navigate(auth_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            current_url = browser_manager.evaluate("window.location.href")
            redirected_to_login = any(p in current_url for p in login_patterns)

            return ValidationResult(
                strategy=self.name(),
                valid=not redirected_to_login,
                confidence=0.85,
                reason=f"redirected to login: {current_url}" if redirected_to_login
                       else f"stayed on target: {current_url}",
                details={"target_url": auth_url, "final_url": current_url,
                         "redirected": redirected_to_login}
            )
        except Exception as e:
            return ValidationResult(
                strategy=self.name(), valid=False, confidence=0.5,
                reason=f"navigation failed: {e}"
            )


class APIProbeStrategy(ValidationStrategy):
    """
    Make a fetch request to an API endpoint and check the response.
    200/304 → valid, 401/403 → invalid.

    Config:
        api_probe_url: API endpoint to test
        api_probe_headers: optional headers to send
        api_probe_method: HTTP method (default GET)
    """

    def name(self) -> str:
        return "api_probe"

    def validate(self, browser_manager, context: Dict) -> ValidationResult:
        probe_url = context.get("api_probe_url")
        if not probe_url:
            return ValidationResult(
                strategy=self.name(), valid=True, confidence=0.0,
                reason="no api_probe_url configured"
            )

        try:
            js_code = """
                async (config) => {
                    const resp = await fetch(config.url, {
                        method: config.method || 'GET',
                        headers: config.headers || {},
                        credentials: 'include'
                    });
                    return {
                        status: resp.status,
                        ok: resp.ok,
                        url: resp.url,
                        redirected: resp.redirected
                    };
                }
            """
            result = browser_manager.evaluate_with_arg(js_code, {
                "url": probe_url,
                "method": context.get("api_probe_method", "GET"),
                "headers": context.get("api_probe_headers", {}),
            })

            status = result.get("status", 0)
            ok = result.get("ok", False)

            return ValidationResult(
                strategy=self.name(),
                valid=ok and status not in (401, 403),
                confidence=0.8,
                reason=f"API returned {status}",
                details={"url": probe_url, "status": status, "ok": ok,
                         "redirected": result.get("redirected")}
            )
        except Exception as e:
            return ValidationResult(
                strategy=self.name(), valid=False, confidence=0.3,
                reason=f"API probe failed: {e}"
            )


class PageContentStrategy(ValidationStrategy):
    """
    Check if page contains user-specific content.
    If content found → logged in. If not → logged out.

    Config:
        user_content_selectors: CSS selectors that exist when logged in
        user_content_text: text strings that appear when logged in
    """

    def name(self) -> str:
        return "page_content"

    def validate(self, browser_manager, context: Dict) -> ValidationResult:
        selectors = context.get("user_content_selectors", [])
        text_patterns = context.get("user_content_text", [])

        if not selectors and not text_patterns:
            return ValidationResult(
                strategy=self.name(), valid=True, confidence=0.0,
                reason="no user_content_selectors or user_content_text configured"
            )

        found_items = []

        # Check CSS selectors
        for sel in selectors:
            try:
                el = browser_manager.query_selector(sel, timeout=3000)
                if el:
                    found_items.append(f"selector:{sel}")
            except Exception:
                pass

        # Check text patterns via page content
        if text_patterns:
            try:
                page_text = browser_manager.evaluate("document.body.innerText")
                for pattern in text_patterns:
                    if pattern.lower() in (page_text or "").lower():
                        found_items.append(f"text:{pattern}")
            except Exception:
                pass

        has_user_content = len(found_items) > 0

        return ValidationResult(
            strategy=self.name(),
            valid=has_user_content,
            confidence=0.7,
            reason=f"user content found: {found_items}" if has_user_content
                   else "no user content found",
            details={"found": found_items}
        )


class CookieExpiryStrategy(ValidationStrategy):
    """
    Check if critical cookies exist and haven't expired.

    Config:
        critical_cookies: list of cookie names that must be present
    """

    def name(self) -> str:
        return "cookie_expiry"

    def validate(self, browser_manager, context: Dict) -> ValidationResult:
        critical = context.get("critical_cookies", [])

        try:
            cookies = browser_manager.get_cookies()

            # No critical cookies defined - check if any cookies present
            if not critical:
                valid = len(cookies) > 0
                return ValidationResult(
                    strategy=self.name(),
                    valid=valid,
                    confidence=0.3,
                    reason=f"{len(cookies)} cookies present" if valid else "no cookies present",
                    details={"total_cookies": len(cookies)}
                )
            cookie_map = {c.get("name", ""): c for c in cookies}

            missing = [name for name in critical if name not in cookie_map]
            expired = []
            for name in critical:
                if name in cookie_map:
                    c = cookie_map[name]
                    exp = c.get("expires", -1)
                    if exp > 0 and exp < time.time():
                        expired.append(name)

            all_present = len(missing) == 0
            none_expired = len(expired) == 0
            valid = all_present and none_expired

            # Distinguish between logged_out (all missing) and session_expired (some missing)
            if not all_present and len(missing) < len(critical):
                status = "session_expired"
            elif not all_present:
                status = "logged_out"
            elif not none_expired:
                status = "session_expired"
            else:
                status = "logged_in"

            return ValidationResult(
                strategy=self.name(),
                valid=valid,
                confidence=0.6,
                reason=f"all {len(critical)} critical cookies present and valid" if valid
                       else f"missing: {missing}, expired: {expired}",
                details={"missing": missing, "expired": expired,
                         "total_cookies": len(cookies), "status": status}
            )
        except Exception as e:
            return ValidationResult(
                strategy=self.name(), valid=False, confidence=0.3,
                reason=f"cookie check failed: {e}",
                details={"error": str(e)}
            )


class LocalStorageStrategy(ValidationStrategy):
    """
    Check if auth tokens exist in localStorage.

    Config:
        localStorage_keys: list of keys that should exist when logged in
    """

    def name(self) -> str:
        return "local_storage"

    def validate(self, browser_manager, context: Dict) -> ValidationResult:
        keys = context.get("localStorage_keys", [])
        if not keys:
            return ValidationResult(
                strategy=self.name(), valid=True, confidence=0.0,
                reason="no localStorage_keys configured"
            )

        try:
            found = []
            for key in keys:
                try:
                    val = browser_manager.evaluate(
                        f"(() => {{ try {{ return localStorage.getItem('{key}'); }} catch(e) {{ return null; }} }})()"
                    )
                    if val:
                        found.append(key)
                except Exception:
                    pass

            valid = len(found) > 0
            return ValidationResult(
                strategy=self.name(),
                valid=valid,
                confidence=0.5,
                reason=f"found keys: {found}" if valid else "no auth tokens in localStorage",
                details={"expected": keys, "found": found}
            )
        except Exception as e:
            return ValidationResult(
                strategy=self.name(), valid=False, confidence=0.2,
                reason=f"localStorage check failed: {e}"
            )


class SessionValidator:
    """
    Composable session validator that runs multiple strategies.

    Strategies are weighted by confidence. A strategy with confidence=0
    is skipped (not configured). Final result is determined by weighted
    majority of configured strategies.
    """

    STRATEGY_MAP = {
        "css_indicator": CSSIndicatorStrategy,
        "url_redirect": URLRedirectStrategy,
        "api_probe": APIProbeStrategy,
        "page_content": PageContentStrategy,
        "cookie_expiry": CookieExpiryStrategy,
        "local_storage": LocalStorageStrategy,
    }

    def __init__(self, strategies: Optional[List[str]] = None):
        """
        Initialize validator.

        Args:
            strategies: List of strategy names to use. If None, uses all
                       strategies that have config values in site_config.
        """
        self.strategies = strategies

    def validate(self, browser_manager, site_config: Dict) -> Dict:
        """
        Run all configured validation strategies.

        Args:
            browser_manager: Active browser manager
            site_config: Site configuration with strategy-specific keys

        Returns:
            Combined validation result dict
        """
        # Determine which strategies to run
        if self.strategies:
            strategy_names = self.strategies
        else:
            # Auto-detect: use all strategies that have config
            strategy_names = []
            if site_config.get("login_indicator_css"):
                strategy_names.append("css_indicator")
            if site_config.get("auth_gated_url"):
                strategy_names.append("url_redirect")
            if site_config.get("api_probe_url"):
                strategy_names.append("api_probe")
            if site_config.get("user_content_selectors") or site_config.get("user_content_text"):
                strategy_names.append("page_content")
            if site_config.get("critical_cookies"):
                strategy_names.append("cookie_expiry")
            if site_config.get("localStorage_keys"):
                strategy_names.append("local_storage")

            # Always include cookie_expiry as baseline
            if "cookie_expiry" not in strategy_names:
                strategy_names.append("cookie_expiry")

        if not strategy_names:
            return {
                "valid": False,
                "auth_status": "unknown",
                "strategies_run": [],
                "reason": "no validation strategies configured",
            }

        # Run strategies
        results = []
        for name in strategy_names:
            cls = self.STRATEGY_MAP.get(name)
            if not cls:
                logger.warning(f"Unknown validation strategy: {name}")
                continue

            strategy = cls()
            try:
                result = strategy.validate(browser_manager, site_config)
                results.append(result)
                logger.info(f"  [{name}] {'PASS' if result.valid else 'FAIL'} "
                            f"(confidence={result.confidence}): {result.reason}")
            except Exception as e:
                logger.error(f"  [{name}] ERROR: {e}")
                results.append(ValidationResult(
                    strategy=name, valid=False, confidence=0.0,
                    reason=f"strategy error: {e}",
                    details={"error": str(e)}
                ))

        # Combine results using weighted voting
        total_weight = sum(r.confidence for r in results if r.confidence > 0)
        if total_weight == 0:
            return {
                "valid": False,
                "auth_status": "unknown",
                "strategies_run": [r.strategy for r in results],
                "reason": "all strategies skipped (no config)",
            }

        weighted_score = sum(
            r.confidence if r.valid else 0
            for r in results if r.confidence > 0
        )
        valid_ratio = weighted_score / total_weight

        # Determine final result
        final_valid = valid_ratio > 0.5
        final_status = "logged_in" if final_valid else "logged_out"

        # Check if any strategy reports session_expired (partial cookie presence)
        for r in results:
            if r.strategy == "cookie_expiry" and not r.valid:
                detail_status = r.details.get("status", "")
                if detail_status == "session_expired":
                    final_status = "session_expired"
                    break

        # Build detailed response
        strategy_details = {}
        errors = {}
        for r in results:
            strategy_details[r.strategy] = {
                "valid": r.valid,
                "confidence": r.confidence,
                "reason": r.reason,
                "details": r.details,
            }
            if "error" in r.details:
                errors[r.strategy] = r.details["error"]

        return {
            "valid": final_valid,
            "auth_status": final_status,
            "confidence": valid_ratio,
            "strategies_run": [r.strategy for r in results],
            "strategy_results": strategy_details,
            "cookies_present": results[0].details.get("total_cookies", 0) if results else 0,
            **({"error": errors} if errors else {}),
        }
