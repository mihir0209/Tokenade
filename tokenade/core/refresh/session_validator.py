"""
Session Validation Endpoint for CI/CD Health Gates.

Provides programmatic validation of .tokenade session files for use in
CI/CD pipelines as health gates. Returns exit codes and JSON reports.

Usage:
    # CLI
    tokenade validate-session --session gmail.tokenade --min-health 0.8
    tokenade validate-session --sessions-dir sessions/ --require-oauth

    # Python
    from tokenade.core.refresh.session_validator import SessionValidator
    validator = SessionValidator()
    result = validator.validate("gmail.tokenade")
    if not result.valid:
        sys.exit(1)
"""

import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ValidationRule:
    """A single validation rule."""
    name: str
    check: str  # "min_health", "max_expired", "require_oauth", "require_cookies", "max_age_hours"
    value: any = None
    description: str = ""


@dataclass
class ValidationResult:
    """Result of session validation."""
    valid: bool
    session_file: str
    rules_passed: int
    rules_total: int
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict = field(default_factory=dict)
    exit_code: int = 0  # 0 = pass, 1 = fail, 2 = warning

    def to_dict(self) -> Dict:
        return {
            "valid": self.valid,
            "session_file": self.session_file,
            "rules_passed": self.rules_passed,
            "rules_total": self.rules_total,
            "errors": self.errors,
            "warnings": self.warnings,
            "details": self.details,
            "exit_code": self.exit_code,
        }


class SessionValidator:
    """
    Validates .tokenade session files against configurable rules.

    Usage:
        validator = SessionValidator()

        # Validate single session
        result = validator.validate("gmail.tokenade", rules=[
            ValidationRule("min_health", "min_health", 0.8),
            ValidationRule("require_oauth", "require_oauth"),
        ])

        # Validate directory
        results = validator.validate_directory("sessions/", rules=[...])
    """

    DEFAULT_RULES = [
        ValidationRule("has_cookies", "require_cookies", description="Session must have cookies"),
        ValidationRule("min_health", "min_health", 0.5, description="Minimum health score"),
        ValidationRule("no_expired", "max_expired", 0, description="No expired cookies"),
    ]

    def validate(
        self,
        session_file: str,
        rules: Optional[List[ValidationRule]] = None,
    ) -> ValidationResult:
        """
        Validate a single session file.

        Args:
            session_file: Path to .tokenade file
            rules: Validation rules (uses defaults if None)

        Returns:
            ValidationResult
        """
        rules = rules or self.DEFAULT_RULES
        errors = []
        warnings = []
        details = {}
        rules_passed = 0

        try:
            with open(session_file) as f:
                session = json.load(f)
        except FileNotFoundError:
            return ValidationResult(
                valid=False,
                session_file=session_file,
                rules_passed=0,
                rules_total=len(rules),
                errors=[f"File not found: {session_file}"],
                exit_code=1,
            )
        except json.JSONDecodeError:
            # Check if encrypted
            try:
                with open(session_file, "rb") as f:
                    data = f.read(100)
                if b"-----BEGIN" in data or len(data) < 10:
                    return ValidationResult(
                        valid=False,
                        session_file=session_file,
                        rules_passed=0,
                        rules_total=len(rules),
                        errors=["Session is encrypted. Decrypt first or provide password."],
                        exit_code=1,
                    )
            except Exception:
                pass
            return ValidationResult(
                valid=False,
                session_file=session_file,
                rules_passed=0,
                rules_total=len(rules),
                errors=["Invalid JSON in session file"],
                exit_code=1,
            )

        # Basic structure validation
        if "cookies" not in session:
            errors.append("Missing 'cookies' field")
            return ValidationResult(
                valid=False,
                session_file=session_file,
                rules_passed=0,
                rules_total=len(rules),
                errors=errors,
                exit_code=1,
            )

        cookies = session.get("cookies", [])
        tokens = session.get("tokens", [])

        # Apply rules
        for rule in rules:
            try:
                passed = self._check_rule(rule, session, cookies, tokens)
                if passed:
                    rules_passed += 1
                elif rule.check in ("min_health",):
                    warnings.append(f"Rule '{rule.name}' failed: {rule.description}")
                else:
                    errors.append(f"Rule '{rule.name}' failed: {rule.description}")
            except Exception as e:
                errors.append(f"Rule '{rule.name}' error: {e}")

        # Collect details
        from tokenade.core.refresh.health_checker import SessionHealthChecker
        checker = SessionHealthChecker()
        health = checker.check_session(session_file)
        details["health_score"] = health.health_score
        details["cookie_count"] = len(cookies)
        details["token_count"] = len(tokens)
        details["auth_status"] = session.get("auth_status", "unknown")
        details["site_name"] = session.get("site_name", "unknown")
        details["has_oauth_config"] = session.get("oauth_config") is not None
        details["version"] = session.get("version", "unknown")

        valid = len(errors) == 0
        exit_code = 0 if valid else 1

        return ValidationResult(
            valid=valid,
            session_file=session_file,
            rules_passed=rules_passed,
            rules_total=len(rules),
            errors=errors,
            warnings=warnings,
            details=details,
            exit_code=exit_code,
        )

    def _check_rule(
        self,
        rule: ValidationRule,
        session: Dict,
        cookies: List[Dict],
        tokens: List[Dict],
    ) -> bool:
        """Check a single validation rule."""
        if rule.check == "require_cookies":
            return len(cookies) > 0

        elif rule.check == "min_health":
            from tokenade.core.refresh.health_checker import SessionHealthChecker
            checker = SessionHealthChecker()
            health = checker.check_session(rule.value if isinstance(rule.value, str) else "")
            # Re-check with session data
            min_score = float(rule.value) if rule.value is not None else 0.5
            # Calculate inline
            now = time.time()
            valid_cookies = 0
            for c in cookies:
                expires = c.get("expires", 0)
                if not expires or int(expires) <= 0:
                    valid_cookies += 1
                elif int(expires) > now:
                    valid_cookies += 1
            score = valid_cookies / len(cookies) if cookies else 0.0
            return score >= min_score

        elif rule.check == "max_expired":
            max_expired = int(rule.value) if rule.value is not None else 0
            now = time.time()
            expired = 0
            for c in cookies:
                expires = c.get("expires", 0)
                if expires and int(expires) > 0:
                    exp = int(expires)
                    if exp > 1262304000000:
                        exp = exp // 1000
                    if exp < now:
                        expired += 1
            return expired <= max_expired

        elif rule.check == "require_oauth":
            return session.get("oauth_config") is not None

        elif rule.check == "require_tokens":
            return len(tokens) > 0

        elif rule.check == "max_age_hours":
            max_hours = float(rule.value) if rule.value is not None else 24
            created_at = session.get("created_at")
            if not created_at:
                return False
            try:
                from datetime import datetime, timezone
                created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
                return age_hours <= max_hours
            except Exception:
                return False

        elif rule.check == "require_auth":
            return session.get("auth_status") == "logged_in"

        elif rule.check == "site_name":
            return session.get("site_name") == rule.value

        else:
            logger.warning(f"Unknown rule check: {rule.check}")
            return True

    def validate_directory(
        self,
        sessions_dir: str,
        rules: Optional[List[ValidationRule]] = None,
    ) -> List[ValidationResult]:
        """
        Validate all session files in a directory.

        Args:
            sessions_dir: Directory containing .tokenade files
            rules: Validation rules

        Returns:
            List of ValidationResult
        """
        results = []
        sessions_path = Path(sessions_dir)

        if not sessions_path.exists():
            logger.error(f"Directory not found: {sessions_dir}")
            return results

        for session_file in sorted(sessions_path.glob("*.tokenade")):
            result = self.validate(str(session_file), rules)
            results.append(result)

        return results

    def ci_report(self, results: List[ValidationResult]) -> str:
        """
        Generate a CI/CD-friendly report.

        Args:
            results: List of validation results

        Returns:
            Formatted report string
        """
        lines = []
        total = len(results)
        passed = sum(1 for r in results if r.valid)
        failed = total - passed

        lines.append(f"Session Validation Report: {passed}/{total} passed")

        for result in results:
            status = "PASS" if result.valid else "FAIL"
            lines.append(f"  [{status}] {Path(result.session_file).name}")
            for error in result.errors:
                lines.append(f"         ERROR: {error}")
            for warning in result.warnings:
                lines.append(f"         WARN: {warning}")

        if failed > 0:
            lines.append(f"\n{failed} session(s) failed validation")
        else:
            lines.append("\nAll sessions passed validation")

        return "\n".join(lines)


def create_ci_validation_rules(
    min_health: float = 0.5,
    max_expired: int = 0,
    require_oauth: bool = False,
    max_age_hours: Optional[float] = None,
) -> List[ValidationRule]:
    """
    Create validation rules for CI/CD.

    Args:
        min_health: Minimum health score (0.0-1.0)
        max_expired: Maximum allowed expired cookies
        require_oauth: Require OAuth config
        max_age_hours: Maximum session age in hours

    Returns:
        List of ValidationRule
    """
    rules = [
        ValidationRule("has_cookies", "require_cookies", description="Session must have cookies"),
        ValidationRule("min_health", "min_health", min_health, description=f"Health score >= {min_health}"),
        ValidationRule("no_expired", "max_expired", max_expired, description=f"Max {max_expired} expired cookies"),
    ]

    if require_oauth:
        rules.append(
            ValidationRule("require_oauth", "require_oauth", description="OAuth config required")
        )

    if max_age_hours is not None:
        rules.append(
            ValidationRule("max_age", "max_age_hours", max_age_hours, description=f"Max age: {max_age_hours}h")
        )

    return rules
