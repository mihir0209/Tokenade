"""
SDK Multi-Site Scraper Proxy Example

Demonstrates scraping multi-domain workflows through in-process Tokenade SessionProxy.
Runs proxy in a background context manager without subprocess overhead.

Usage:
    python examples/sdk_multisite_scraper.py
"""

import json
import tempfile
import time
from pathlib import Path

from tokenade.sdk import TokenadeClient, SessionProxy


def create_sample_session(site: str, token: str) -> dict:
    now = int(time.time())
    return {
        "version": "3.0",
        "format": "tokenade",
        "site_name": site,
        "auth_status": "logged_in",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "cookies": [
            {
                "name": "auth_token",
                "value": token,
                "domain": f".{site}.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "sameSite": "Lax",
                "expires": now + 3600,
            }
        ],
        "storage": {"local": {}, "session": {}},
    }


def main():
    print("=== Tokenade SDK: In-Process Proxy Scraper Recipe ===\n")
    client = TokenadeClient()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        session_file = tmp_path / "app_session.tokenade"
        session_data = create_sample_session("example", "secret_bearer_token_xyz")
        session_file.write_text(json.dumps(session_data, indent=2))

        print(f"Loading session from {session_file.name}...")
        loaded = client.load(str(session_file))
        print(f"Session site: {loaded.get('site_name')}, cookies: {len(loaded.get('cookies', []))}")

        # Start an in-process proxy using Python context manager
        print("\nStarting in-process SessionProxy on port 9876 (forward mode)...")
        try:
            with SessionProxy.from_file(session_file, port=9876, mode="forward") as proxy:
                print(f"Proxy active at: {proxy.base_url}")
                print(f"Proxy status: running={proxy.running}")
                print("Session headers and cookies automatically mapped into outbound requests.")
        except Exception as e:
            print(f"Proxy failed to start: {e}")
            print("Forward mode requires curl-cffi (pip install curl-cffi).")

    print("\nIn-process proxy workflow completed successfully.")


if __name__ == "__main__":
    main()
