"""
Advanced validation rules: custom JS, visual regression, API validation.
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List, Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation rule."""
    rule_name: str
    passed: bool
    message: str
    details: Optional[Dict] = None
    duration_ms: Optional[float] = None


@dataclass
class ValidationRule:
    """Definition of a validation rule."""
    name: str
    type: str  # "js", "screenshot", "api", "cookie", "url", "element"
    config: Dict = field(default_factory=dict)
    timeout: int = 30


class AdvancedValidator:
    """
    Advanced session validation with custom rules.
    
    Features:
    - Custom JavaScript validation scripts
    - Visual regression testing (screenshot comparison)
    - API endpoint validation
    - Cookie presence/value checks
    - URL redirect validation
    - DOM element presence checks
    """
    
    def __init__(self, proxy_port: int = 9222):
        self.proxy_port = proxy_port
        self._baseline_dir = Path("~/.tokenade/baselines").expanduser()
        self._baseline_dir.mkdir(parents=True, exist_ok=True)
    
    async def validate_rules(
        self,
        session: Dict,
        rules: List[ValidationRule],
        site_url: Optional[str] = None,
    ) -> List[ValidationResult]:
        """
        Validate session against a list of custom rules.
        
        Args:
            session: Session data
            rules: List of validation rules
            site_url: Target site URL
            
        Returns:
            List of validation results
        """
        results = []
        
        for rule in rules:
            try:
                start = time.time()
                result = await self._validate_rule(session, rule, site_url)
                result.duration_ms = (time.time() - start) * 1000
                results.append(result)
            except Exception as e:
                results.append(ValidationResult(
                    rule_name=rule.name,
                    passed=False,
                    message=f"Rule execution failed: {e}",
                ))
        
        return results
    
    async def _validate_rule(
        self,
        session: Dict,
        rule: ValidationRule,
        site_url: Optional[str],
    ) -> ValidationResult:
        """Validate a single rule."""
        if rule.type == "js":
            return await self._validate_js(session, rule, site_url)
        elif rule.type == "screenshot":
            return await self._validate_screenshot(session, rule, site_url)
        elif rule.type == "api":
            return await self._validate_api(session, rule, site_url)
        elif rule.type == "cookie":
            return self._validate_cookie(session, rule)
        elif rule.type == "url":
            return await self._validate_url(session, rule, site_url)
        elif rule.type == "element":
            return await self._validate_element(session, rule, site_url)
        else:
            return ValidationResult(
                rule_name=rule.name,
                passed=False,
                message=f"Unknown rule type: {rule.type}",
            )
    
    async def _validate_js(
        self,
        session: Dict,
        rule: ValidationRule,
        site_url: Optional[str],
    ) -> ValidationResult:
        """Validate using custom JavaScript."""
        try:
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                
                # Inject cookies
                cookies = session.get("cookies", [])
                if cookies:
                    pw_cookies = self._prepare_cookies(cookies)
                    await context.add_cookies(pw_cookies)
                
                page = await context.new_page()
                
                # Navigate to site
                url = site_url or self._get_site_url(session)
                await page.goto(url, wait_until="domcontentloaded", timeout=rule.timeout * 1000)
                
                # Execute JS validation
                js_code = rule.config.get("script", "return true")
                result = await page.evaluate(js_code)
                
                await browser.close()
                
                if result:
                    return ValidationResult(
                        rule_name=rule.name,
                        passed=True,
                        message="JavaScript validation passed",
                        details={"result": result},
                    )
                else:
                    return ValidationResult(
                        rule_name=rule.name,
                        passed=False,
                        message="JavaScript validation failed",
                        details={"result": result},
                    )
        
        except Exception as e:
            return ValidationResult(
                rule_name=rule.name,
                passed=False,
                message=f"JavaScript validation error: {e}",
            )
    
    async def _validate_screenshot(
        self,
        session: Dict,
        rule: ValidationRule,
        site_url: Optional[str],
    ) -> ValidationResult:
        """Validate using screenshot comparison."""
        try:
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                
                # Inject cookies
                cookies = session.get("cookies", [])
                if cookies:
                    pw_cookies = self._prepare_cookies(cookies)
                    await context.add_cookies(pw_cookies)
                
                page = await context.new_page()
                
                # Navigate to site
                url = site_url or self._get_site_url(session)
                await page.goto(url, wait_until="domcontentloaded", timeout=rule.timeout * 1000)
                
                # Take screenshot
                screenshot = await page.screenshot(type="png")
                current_hash = hashlib.sha256(screenshot).hexdigest()
                
                # Check baseline
                baseline_name = rule.config.get("baseline", "default")
                baseline_path = self._baseline_dir / f"{baseline_name}.png"
                
                if baseline_path.exists() and not rule.config.get("update_baseline"):
                    # Compare with baseline
                    baseline_bytes = baseline_path.read_bytes()
                    baseline_hash = hashlib.md5(baseline_bytes).hexdigest()
                    
                    if current_hash == baseline_hash:
                        await browser.close()
                        return ValidationResult(
                            rule_name=rule.name,
                            passed=True,
                            message="Screenshot matches baseline",
                            details={"hash": current_hash},
                        )
                    else:
                        await browser.close()
                        return ValidationResult(
                            rule_name=rule.name,
                            passed=False,
                            message="Screenshot differs from baseline",
                            details={
                                "current_hash": current_hash,
                                "baseline_hash": baseline_hash,
                            },
                        )
                else:
                    # Save as new baseline
                    baseline_path.parent.mkdir(parents=True, exist_ok=True)
                    baseline_path.write_bytes(screenshot)
                    
                    await browser.close()
                    return ValidationResult(
                        rule_name=rule.name,
                        passed=True,
                        message="Screenshot saved as new baseline",
                        details={"hash": current_hash},
                    )
        
        except Exception as e:
            return ValidationResult(
                rule_name=rule.name,
                passed=False,
                message=f"Screenshot validation error: {e}",
            )
    
    async def _validate_api(
        self,
        session: Dict,
        rule: ValidationRule,
        site_url: Optional[str],
    ) -> ValidationResult:
        """Validate API endpoint response."""
        import aiohttp
        
        api_url = rule.config.get("url")
        if not api_url:
            return ValidationResult(
                rule_name=rule.name,
                passed=False,
                message="No API URL specified",
            )
        
        expected_status = rule.config.get("status", 200)
        expected_body = rule.config.get("body")
        headers = rule.config.get("headers", {})
        
        # Add cookies to headers
        cookie_header = self._get_cookie_header(session, api_url)
        if cookie_header:
            headers["cookie"] = cookie_header
        
        try:
            async with aiohttp.ClientSession() as client:
                async with client.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=rule.timeout)) as resp:
                    status = resp.status
                    body = await resp.text()
                    
                    # Check status
                    if status != expected_status:
                        return ValidationResult(
                            rule_name=rule.name,
                            passed=False,
                            message=f"API returned status {status}, expected {expected_status}",
                            details={"status": status, "body": body[:500]},
                        )
                    
                    # Check body if specified
                    if expected_body:
                        if isinstance(expected_body, str):
                            if expected_body not in body:
                                return ValidationResult(
                                    rule_name=rule.name,
                                    passed=False,
                                    message=f"API response missing expected content",
                                    details={"expected": expected_body, "actual": body[:500]},
                                )
                        elif isinstance(expected_body, dict):
                            try:
                                json_body = json.loads(body)
                                for key, value in expected_body.items():
                                    if json_body.get(key) != value:
                                        return ValidationResult(
                                            rule_name=rule.name,
                                            passed=False,
                                            message=f"API response field mismatch: {key}",
                                            details={"expected": value, "actual": json_body.get(key)},
                                        )
                            except json.JSONDecodeError:
                                return ValidationResult(
                                    rule_name=rule.name,
                                    passed=False,
                                    message="API response is not valid JSON",
                                )
                    
                    return ValidationResult(
                        rule_name=rule.name,
                        passed=True,
                        message="API validation passed",
                        details={"status": status},
                    )
        
        except Exception as e:
            return ValidationResult(
                rule_name=rule.name,
                passed=False,
                message=f"API validation error: {e}",
            )
    
    def _validate_cookie(self, session: Dict, rule: ValidationRule) -> ValidationResult:
        """Validate cookie presence and value."""
        cookies = session.get("cookies", [])
        cookie_name = rule.config.get("name")
        cookie_domain = rule.config.get("domain")
        expected_value = rule.config.get("value")
        must_exist = rule.config.get("exists", True)
        
        if not cookie_name:
            return ValidationResult(
                rule_name=rule.name,
                passed=False,
                message="No cookie name specified",
            )
        
        # Find matching cookie
        found = None
        for cookie in cookies:
            if cookie.get("name") == cookie_name:
                if cookie_domain and cookie.get("domain") != cookie_domain:
                    continue
                found = cookie
                break
        
        if must_exist:
            if not found:
                return ValidationResult(
                    rule_name=rule.name,
                    passed=False,
                    message=f"Cookie '{cookie_name}' not found",
                )
            
            if expected_value and found.get("value") != expected_value:
                return ValidationResult(
                    rule_name=rule.name,
                    passed=False,
                    message=f"Cookie '{cookie_name}' has wrong value",
                    details={"expected": expected_value, "actual": found.get("value")},
                )
            
            return ValidationResult(
                rule_name=rule.name,
                passed=True,
                message=f"Cookie '{cookie_name}' found",
                details={"value": found.get("value", "")[:50]},
            )
        else:
            if found:
                return ValidationResult(
                    rule_name=rule.name,
                    passed=False,
                    message=f"Cookie '{cookie_name}' should not exist",
                )
            
            return ValidationResult(
                rule_name=rule.name,
                passed=True,
                message=f"Cookie '{cookie_name}' correctly absent",
            )
    
    async def _validate_url(
        self,
        session: Dict,
        rule: ValidationRule,
        site_url: Optional[str],
    ) -> ValidationResult:
        """Validate URL redirect behavior."""
        import aiohttp
        
        test_url = rule.config.get("url") or site_url
        expected_url = rule.config.get("redirect_to")
        should_redirect = rule.config.get("redirect", False)
        
        if not test_url:
            return ValidationResult(
                rule_name=rule.name,
                passed=False,
                message="No URL specified",
            )
        
        try:
            async with aiohttp.ClientSession() as client:
                async with client.get(
                    test_url,
                    allow_redirects=False,
                    timeout=aiohttp.ClientTimeout(total=rule.timeout),
                ) as resp:
                    if should_redirect:
                        if resp.status in (301, 302, 303, 307, 308):
                            location = resp.headers.get("location", "")
                            if expected_url and expected_url not in location:
                                return ValidationResult(
                                    rule_name=rule.name,
                                    passed=False,
                                    message=f"Redirect to wrong URL",
                                    details={"expected": expected_url, "actual": location},
                                )
                            return ValidationResult(
                                rule_name=rule.name,
                                passed=True,
                                message=f"Redirects to {location}",
                                details={"location": location},
                            )
                        else:
                            return ValidationResult(
                                rule_name=rule.name,
                                passed=False,
                                message=f"Expected redirect, got status {resp.status}",
                            )
                    else:
                        if resp.status in (301, 302, 303, 307, 308):
                            return ValidationResult(
                                rule_name=rule.name,
                                passed=False,
                                message=f"Unexpected redirect to {resp.headers.get('location')}",
                            )
                        return ValidationResult(
                            rule_name=rule.name,
                            passed=True,
                            message=f"No redirect (status {resp.status})",
                        )
        
        except Exception as e:
            return ValidationResult(
                rule_name=rule.name,
                passed=False,
                message=f"URL validation error: {e}",
            )
    
    async def _validate_element(
        self,
        session: Dict,
        rule: ValidationRule,
        site_url: Optional[str],
    ) -> ValidationResult:
        """Validate DOM element presence."""
        try:
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                
                # Inject cookies
                cookies = session.get("cookies", [])
                if cookies:
                    pw_cookies = self._prepare_cookies(cookies)
                    await context.add_cookies(pw_cookies)
                
                page = await context.new_page()
                
                # Navigate to site
                url = site_url or self._get_site_url(session)
                await page.goto(url, wait_until="domcontentloaded", timeout=rule.timeout * 1000)
                
                # Check element
                selector = rule.config.get("selector")
                should_exist = rule.config.get("exists", True)
                text_content = rule.config.get("text")
                
                if not selector:
                    await browser.close()
                    return ValidationResult(
                        rule_name=rule.name,
                        passed=False,
                        message="No selector specified",
                    )
                
                element = await page.query_selector(selector)
                
                if should_exist:
                    if not element:
                        await browser.close()
                        return ValidationResult(
                            rule_name=rule.name,
                            passed=False,
                            message=f"Element '{selector}' not found",
                        )
                    
                    if text_content:
                        actual_text = await element.text_content()
                        if text_content not in (actual_text or ""):
                            await browser.close()
                            return ValidationResult(
                                rule_name=rule.name,
                                passed=False,
                                message=f"Element text mismatch",
                                details={"expected": text_content, "actual": actual_text},
                            )
                    
                    await browser.close()
                    return ValidationResult(
                        rule_name=rule.name,
                        passed=True,
                        message=f"Element '{selector}' found",
                    )
                else:
                    if element:
                        await browser.close()
                        return ValidationResult(
                            rule_name=rule.name,
                            passed=False,
                            message=f"Element '{selector}' should not exist",
                        )
                    
                    await browser.close()
                    return ValidationResult(
                        rule_name=rule.name,
                        passed=True,
                        message=f"Element '{selector}' correctly absent",
                    )
        
        except Exception as e:
            return ValidationResult(
                rule_name=rule.name,
                passed=False,
                message=f"Element validation error: {e}",
            )
    
    def _prepare_cookies(self, cookies: List[Dict]) -> List[Dict]:
        """Convert cookies to Playwright format."""
        pw_cookies = []
        for cookie in cookies:
            pw_cookie = {
                "name": cookie.get("name", ""),
                "value": cookie.get("value", ""),
                "domain": cookie.get("domain", ""),
                "path": cookie.get("path", "/"),
            }
            
            same_site = cookie.get("sameSite", "").lower()
            if same_site in ("strict", "lax", "none"):
                pw_cookie["sameSite"] = same_site.capitalize()
            else:
                pw_cookie["sameSite"] = "Lax"
            
            if cookie.get("secure"):
                pw_cookie["secure"] = True
            if cookie.get("httpOnly"):
                pw_cookie["httpOnly"] = True
            
            expires = cookie.get("expires")
            if expires:
                if isinstance(expires, (int, float)) and expires > 1262304000000:
                    expires = expires / 1000
                pw_cookie["expires"] = expires
            
            pw_cookies.append(pw_cookie)
        
        return pw_cookies
    
    def _get_site_url(self, session: Dict) -> str:
        """Get site URL from session."""
        cookies = session.get("cookies", [])
        domains = set()
        for c in cookies:
            d = c.get("domain", "")
            if d:
                domains.add(d.lstrip("."))
        
        if domains:
            return f"https://{min(domains, key=len)}"
        
        site_name = session.get("site_name", "unknown")
        return f"https://www.{site_name}.com"
    
    def _get_cookie_header(self, session: Dict, url: str) -> str:
        """Get cookie header for a URL."""
        from urllib.parse import urlparse
        
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        
        cookies = session.get("cookies", [])
        parts = []
        
        for cookie in cookies:
            domain = cookie.get("domain", "").lstrip(".")
            if hostname == domain or hostname.endswith("." + domain):
                name = cookie.get("name", "")
                value = cookie.get("value", "")
                if name:
                    parts.append(f"{name}={value}")
        
        return "; ".join(parts)


def load_validation_rules(path: str) -> List[ValidationRule]:
    """Load validation rules from JSON file."""
    with open(path, "r") as f:
        data = json.load(f)
    
    rules = []
    for item in data:
        rules.append(ValidationRule(
            name=item.get("name", "unnamed"),
            type=item.get("type", "js"),
            config=item.get("config", {}),
            timeout=item.get("timeout", 30),
        ))
    
    return rules


def create_example_rules() -> List[ValidationRule]:
    """Create example validation rules."""
    return [
        ValidationRule(
            name="logged_in_check",
            type="js",
            config={
                "script": "return document.querySelector('[data-testid=\"user-menu\"]') !== null || document.querySelector('.user-avatar') !== null || document.title.includes('Dashboard')",
            },
        ),
        ValidationRule(
            name="no_login_redirect",
            type="url",
            config={
                "redirect": False,
            },
        ),
        ValidationRule(
            name="session_cookie_present",
            type="cookie",
            config={
                "name": "session",
                "exists": True,
            },
        ),
        ValidationRule(
            name="api_me_endpoint",
            type="api",
            config={
                "url": "https://api.example.com/me",
                "status": 200,
            },
        ),
    ]
