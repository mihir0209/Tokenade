"""
Portability Testing Framework - Test if cookies work across devices.

Simulates a target device with specific fingerprint and validates
whether transferred cookies maintain a valid session.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TestResult(Enum):
    """Test result status."""
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"


@dataclass
class PortabilityTest:
    """Result of a single portability test."""
    name: str
    result: TestResult
    source_fingerprint: str = ""
    target_fingerprint: str = ""
    cookies_injected: int = 0
    cookies_accepted: int = 0
    auth_status: str = "unknown"
    api_test_passed: bool = False
    duration_ms: int = 0
    error_message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "result": self.result.value,
            "source_fingerprint": self.source_fingerprint,
            "target_fingerprint": self.target_fingerprint,
            "cookies_injected": self.cookies_injected,
            "cookies_accepted": self.cookies_accepted,
            "auth_status": self.auth_status,
            "api_test_passed": self.api_test_passed,
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
            "details": self.details,
        }


class PortabilityTester:
    """
    Tests if cookies from one device/browser work on another.

    Workflow:
    1. Load source session data
    2. Apply target fingerprint
    3. Inject cookies into fresh browser
    4. Verify session is valid
    5. Test API calls if applicable
    """

    def __init__(self, browser_factory, fingerprint_manager):
        self.browser_factory = browser_factory
        self.fp_manager = fingerprint_manager
        self.results: List[PortabilityTest] = []

    def test_session_transfer(
        self,
        session_data: Dict,
        source_fp_name: str,
        target_fp_name: str,
        handler_class,
        test_api: bool = True,
    ) -> PortabilityTest:
        """
        Test transferring a session from source to target fingerprint.

        Args:
            session_data: Session data with cookies and tokens
            source_fp_name: Name of source fingerprint
            target_fp_name: Name of target fingerprint
            handler_class: Site handler class to use
            test_api: Whether to test API calls

        Returns:
            PortabilityTest result
        """
        import time as time_module
        start_time = time_module.time()

        test = PortabilityTest(
            name=f"{source_fp_name}_to_{target_fp_name}",
            result=TestResult.SKIP,
            source_fingerprint=source_fp_name,
            target_fingerprint=target_fp_name,
        )

        browser = None

        try:
            # Load fingerprints
            self.fp_manager.load(source_fp_name)
            target_fp = self.fp_manager.load(target_fp_name)

            if not target_fp:
                test.result = TestResult.ERROR
                test.error_message = f"Target fingerprint not found: {target_fp_name}"
                return test

            # Launch browser with target fingerprint
            config = target_fp.to_playwright_context()
            config["headless"] = True

            browser = self.browser_factory.create(**config)
            browser.launch()

            # Create handler
            handler = handler_class(browser)

            # Inject cookies
            from tokenade.handlers.base import SessionData, AuthStatus

            session = SessionData(
                site_name=session_data.get("site_name", "unknown"),
                auth_status=AuthStatus(session_data.get("auth_status", "unknown")),
                tokens=[],
                cookies=session_data.get("cookies", []),
                fingerprint=target_fp.to_dict() if hasattr(target_fp, "to_dict") else None,
            )

            test.cookies_injected = len(session.cookies)

            # Attempt injection
            injection_success = handler.inject_session(session)

            if not injection_success:
                test.result = TestResult.FAIL
                test.error_message = "Cookie injection failed"
                test.auth_status = handler.check_auth_status().value
                return test

            # Check auth status after injection
            auth_status = handler.check_auth_status()
            test.auth_status = auth_status.value

            # Count accepted cookies
            accepted_cookies = browser.get_cookies()
            test.cookies_accepted = len(accepted_cookies)

            # Validate session
            is_valid = handler.validate_session(accepted_cookies)

            if auth_status == AuthStatus.LOGGED_IN and is_valid:
                test.result = TestResult.PASS

                # Test API if requested
                if test_api:
                    token = session_data.get("tokens", [{}])[0].get("value")
                    if token and hasattr(handler, "test_api"):
                        api_result = handler.test_api(token)
                        test.api_test_passed = api_result is not None
                        test.details["api_response"] = api_result
            else:
                test.result = TestResult.FAIL
                test.error_message = f"Auth status: {auth_status.value}, Valid: {is_valid}"

            return test

        except Exception as e:
            test.result = TestResult.ERROR
            test.error_message = str(e)
            logger.exception("Portability test failed")
            return test

        finally:
            if browser:
                browser.close()

            test.duration_ms = int((time_module.time() - start_time) * 1000)
            self.results.append(test)

    def test_fingerprint_variations(
        self,
        session_data: Dict,
        base_fp_name: str,
        handler_class,
        variations: Optional[List[Dict]] = None,
    ) -> List[PortabilityTest]:
        """
        Test session against multiple fingerprint variations.

        Tests how robust the session is against fingerprint changes.
        """
        if variations is None:
            variations = [
                {"name": "same_fp", "changes": {}},
                {"name": "different_ua", "changes": {"user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}},
                {"name": "different_viewport", "changes": {"viewport_width": 1366, "viewport_height": 768}},
                {"name": "different_timezone", "changes": {"timezone": "America/New_York"}},
            ]

        results = []
        base_fp = self.fp_manager.load(base_fp_name)

        if not base_fp:
            logger.error(f"Base fingerprint not found: {base_fp_name}")
            return results

        for variation in variations:
            var_name = variation["name"]
            changes = variation["changes"]

            # Create modified fingerprint
            var_fp = self._modify_fingerprint(base_fp, changes)
            var_fp_name = f"{base_fp_name}_{var_name}"

            # Save temporarily
            self.fp_manager.save(var_fp_name, var_fp)

            # Test
            result = self.test_session_transfer(
                session_data=session_data,
                source_fp_name=base_fp_name,
                target_fp_name=var_fp_name,
                handler_class=handler_class,
                test_api=False,  # Skip API test for variations
            )

            result.name = f"{base_fp_name}_to_{var_name}"
            results.append(result)

            # Cleanup
            self.fp_manager.delete(var_fp_name)

        return results

    def _modify_fingerprint(self, fp, changes: Dict) -> Any:
        """Create a modified copy of a fingerprint."""
        from copy import deepcopy
        new_fp = deepcopy(fp)

        for key, value in changes.items():
            if hasattr(new_fp, key):
                setattr(new_fp, key, value)

        return new_fp

    def generate_report(self, output_path: Optional[str] = None) -> str:
        """Generate a test report."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.result == TestResult.PASS)
        failed = sum(1 for r in self.results if r.result == TestResult.FAIL)
        errors = sum(1 for r in self.results if r.result == TestResult.ERROR)
        skipped = sum(1 for r in self.results if r.result == TestResult.SKIP)

        report = []
        report.append("=" * 80)
        report.append("PORTABILITY TEST REPORT")
        report.append("=" * 80)
        report.append(f"\nTotal Tests: {total}")
        report.append(f"  ✅ Passed:   {passed}")
        report.append(f"  ❌ Failed:   {failed}")
        report.append(f"  ⚠️  Errors:   {errors}")
        report.append(f"  ⏭️  Skipped:  {skipped}")
        report.append(f"\nSuccess Rate: {passed / total * 100:.1f}%" if total > 0 else "")

        report.append("\n" + "=" * 80)
        report.append("DETAILED RESULTS")
        report.append("=" * 80)

        for result in self.results:
            status_icon = {
                TestResult.PASS: "✅",
                TestResult.FAIL: "❌",
                TestResult.ERROR: "⚠️",
                TestResult.SKIP: "⏭️",
            }.get(result.result, "❓")

            report.append(f"\n{status_icon} {result.name}")
            report.append(f"   Result: {result.result.value}")
            report.append(f"   Duration: {result.duration_ms}ms")
            report.append(f"   Cookies: {result.cookies_accepted}/{result.cookies_injected} accepted")
            report.append(f"   Auth: {result.auth_status}")
            report.append(f"   API Test: {'✅' if result.api_test_passed else '❌'}")

            if result.error_message:
                report.append(f"   Error: {result.error_message}")

        report_text = "\n".join(report)

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                f.write(report_text)

            # Also save JSON
            json_path = str(Path(output_path).with_suffix(".json"))
            with open(json_path, "w") as f:
                json.dump([r.to_dict() for r in self.results], f, indent=2)

        return report_text
