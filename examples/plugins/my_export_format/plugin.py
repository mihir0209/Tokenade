"""
Example: Custom Export Format Plugin

This plugin demonstrates how to create an export format plugin
that exports sessions in a custom format.

Use cases:
- Export sessions as Python requests code
- Export sessions as curl commands
- Export sessions as Postman collections
- Export sessions as HAR files

To use this plugin:
1. Copy the my_export_format/ directory to ~/.tokenade/plugins/
2. Run: tokenade plugin list
3. Run: tokenade export -s session.tokenade --format python-requests -o output.py
"""

import logging
from typing import Dict, List

from tokenade.plugin import ExportFormatPlugin

logger = logging.getLogger(__name__)


class MyExportFormatPlugin(ExportFormatPlugin):
    """Export sessions as Python requests code.

    This example shows:
    - How to define a custom export format
    - How to convert cookies to code
    - How to generate executable output
    """

    name = "my-export-format"
    version = "1.0.0"
    description = "Example: Export sessions as Python requests code"
    author = "Tokenade Examples"

    def get_format_name(self) -> str:
        """Return the format name used in CLI --format flag."""
        return "python-requests"

    def export(self, session: dict, output_path: str) -> str:
        """Export session as Python requests code.

        Args:
            session: Session data with cookies
            output_path: Where to write the .py file

        Returns:
            Path to the exported file
        """
        cookies = session.get("cookies", [])
        site_name = session.get("site_name", "unknown")

        # Generate Python requests code
        code = self._generate_requests_code(cookies, site_name)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(code)

        logger.info(f"Exported session to Python requests code: {output_path}")
        return output_path

    def _generate_requests_code(self, cookies: List[Dict], site_name: str) -> str:
        """Generate Python requests code from cookies."""
        lines = [
            '"""',
            f"Session for {site_name}",
            f"Exported by Tokenade plugin: my-export-format",
            '"""',
            "",
            "import requests",
            "",
            "",
            "def make_request():",
            '    """Make a request with the exported session."""',
            "    session = requests.Session()",
            "",
            "    # Cookies",
            "    session.cookies.update({",
        ]

        for cookie in cookies:
            name = cookie.get("name", "")
            value = cookie.get("value", "")
            lines.append(f'        "{name}": "{value}",')

        lines.extend([
            "    })",
            "",
            "    # Headers",
            "    session.headers.update({",
            '        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",',
            '        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",',
            "    })",
            "",
            "    # Make request",
            '    response = session.get("https://example.com")',
            "    print(f'Status: {response.status_code}')",
            "    return response",
            "",
            "",
            'if __name__ == "__main__":',
            "    make_request()",
            "",
        ])

        return "\n".join(lines)
