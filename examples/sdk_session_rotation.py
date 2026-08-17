"""
SDK Session Rotation Example

Demonstrates automated health-weighted session rotation using the Tokenade SDK.
Manages a pool of sessions and transparently cycles through active credentials
while monitoring session health and security metrics.

Usage:
    python examples/sdk_session_rotation.py
"""

import json
import tempfile
import time
from pathlib import Path
from typing import List, Optional

from tokenade.sdk import TokenadeClient, SessionProxy


class SessionRotator:
    """Manages an active pool of .tokenade sessions and selects healthy candidates."""

    def __init__(self, session_paths: List[Path], client: Optional[TokenadeClient] = None):
        self.session_paths = session_paths
        self.client = client or TokenadeClient()
        self._index = 0

    def get_healthy_session(self) -> Optional[Path]:
        """Iterate through session pool and pick the next candidate with passing health."""
        if not self.session_paths:
            return None

        total = len(self.session_paths)
        for _ in range(total):
            path = self.session_paths[self._index]
            self._index = (self._index + 1) % total

            try:
                health = self.client.health_check(str(path))
                # health_score is a 0.0–1.0 ratio (valid_cookies / total)
                if health.get("healthy") or health.get("health_score", 0) >= 0.5:
                    return path
            except Exception:
                continue

        # Fallback to first available if all report issues
        return self.session_paths[0]


def create_mock_session(site: str, user: str) -> dict:
    """Build a mock v3 session dict for demonstration."""
    now = int(time.time())
    return {
        "version": "3.0",
        "format": "tokenade",
        "site_name": site,
        "auth_status": "logged_in",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "cookies": [
            {
                "name": "session_id",
                "value": f"{user}_secret_token_{now}",
                "domain": f".{site}.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "sameSite": "Lax",
                "expires": now + 86400,
            }
        ],
        "storage": {
            "local": {
                f"https://{site}.com": {
                    "username": user,
                    "account_type": "pro",
                }
            },
            "session": {},
        },
    }


def main():
    print("=== Tokenade SDK: Automated Session Rotation Recipe ===\n")
    client = TokenadeClient()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        session_files = []

        # Create sample pool of sessions
        for i in range(1, 4):
            session_data = create_mock_session("github", f"worker_bot_{i}")
            file_path = tmp_path / f"github_worker_{i}.tokenade"
            file_path.write_text(json.dumps(session_data, indent=2))
            session_files.append(file_path)
            print(f"Created pool session: {file_path.name}")

        rotator = SessionRotator(session_files, client=client)

        print("\nSimulating 3 rotation cycles:")
        for cycle in range(1, 4):
            selected = rotator.get_healthy_session()
            print(f"Cycle {cycle}: Selected healthy session -> {selected.name}")
            data = client.load(str(selected))
            user = data.get("storage", {}).get("local", {}).get("https://github.com", {}).get("username")
            print(f"         Authenticated as: {user}")

    print("\nSession rotation workflow completed successfully.")


if __name__ == "__main__":
    main()
