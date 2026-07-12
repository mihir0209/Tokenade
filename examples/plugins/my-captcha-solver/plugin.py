"""Example: CAPTCHA Solver Plugin

Integrates with a CAPTCHA solving service (e.g., 2Captcha, Anti-Captcha).

Install:
    cp -r my-captcha-solver ~/.tokenade/plugins/my-captcha-solver
    tokenade plugin configure my-captcha-solver --set api_key=YOUR_KEY
"""

from tokenade.plugin.base import CaptchaPlugin


class MyCaptchaSolverPlugin(CaptchaPlugin):
    """Example CAPTCHA solver — delegates to external service."""

    name = "my-captcha-solver"
    version = "1.0.0"
    description = "Example CAPTCHA solver plugin"

    def solve_image_captcha(self, image_data: bytes) -> str:
        """Solve an image-based CAPTCHA. Returns the solution text."""
        # In production: upload to 2Captcha/Anti-Captcha API
        # This example returns a placeholder.
        return "SOLVED_TEXT"

    def solve_recaptcha(self, site_key: str, page_url: str) -> str:
        """Solve a reCAPTCHA v2/v3. Returns the token."""
        # In production: use 2Captcha's reCAPTCHA solving
        return "RECAPTCHA_TOKEN"

    def solve_hcaptcha(self, site_key: str, page_url: str) -> str:
        """Solve hCaptcha. Returns the token."""
        return "HCAPTCHA_TOKEN"
