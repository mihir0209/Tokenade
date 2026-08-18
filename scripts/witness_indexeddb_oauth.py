#!/usr/bin/env python3
"""
Witness: Live Playwright browser validation for:
1. IndexedDB state injection and extraction round-trip
2. OAuth donor session cookie injection & flow simulation
"""

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tokenade.core.importer.session_loader import SessionLoader
from tokenade.core.importer.session_packager import SessionPackager
from tokenade.core.integration.oauth_handlers import GoogleOAuthAutomation


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP: playwright not available")
        return 0

    print("=== Advanced Browser Witness: IndexedDB & OAuth Automation ===")
    results = []

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:
            print(f"SKIP: could not launch chromium: {e}")
            return 0

        # 1. IndexedDB Injection Witness
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://example.com", wait_until="domcontentloaded")

        idb_sample = {
            "tokenade_witness_db": {
                "version": 1,
                "stores": {
                    "sessions": {
                        "user_auth": {"uid": "usr_99", "tier": "pro"},
                        "jwt_token": "bearer_sample_eyJhbGciOi"
                    }
                }
            }
        }

        # Mock adapter wrapping page.evaluate for SessionLoader
        class BrowserManagerAdapter:
            def evaluate_with_arg(self, script, arg):
                return page.evaluate(script, arg)

        loader = SessionLoader()
        injected_records = loader.inject_indexeddb(BrowserManagerAdapter(), idb_sample)
        results.append(("IndexedDB record injection", injected_records >= 2, f"records={injected_records}"))

        # Verify live IndexedDB contents via page evaluation
        retrieved_val = page.evaluate("""
        async () => {
            return await new Promise((resolve) => {
                const req = indexedDB.open("tokenade_witness_db", 1);
                req.onsuccess = (e) => {
                    const db = e.target.result;
                    const tx = db.transaction(["sessions"], "readonly");
                    const store = tx.objectStore("sessions");
                    const getReq = store.get("user_auth");
                    getReq.onsuccess = () => { db.close(); resolve(getReq.result); };
                };
                req.onerror = () => resolve(null);
            });
        }
        """)
        results.append(("IndexedDB live verification", retrieved_val and retrieved_val.get("uid") == "usr_99", f"val={retrieved_val}"))

        context.close()

        # 2. OAuth Automation Simulation Witness
        oauth_handler = GoogleOAuthAutomation()
        donor_session = {
            "site_name": "google.com",
            "cookies": [
                {"name": "SID", "value": "donor_secret_sid", "domain": ".google.com", "path": "/"},
                {"name": "HSID", "value": "donor_secret_hsid", "domain": ".google.com", "path": "/"},
            ]
        }

        ctx2 = browser.new_context()
        oauth_handler.inject_source_session(ctx2, donor_session)
        cookies_in_ctx = ctx2.cookies()
        sid_found = any(c["name"] == "SID" and c["value"] == "donor_secret_sid" for c in cookies_in_ctx)
        results.append(("OAuth donor cookie injection", sid_found, f"count={len(cookies_in_ctx)}"))
        ctx2.close()

        browser.close()

    failures = 0
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))

    print(f"RESULT: {'SUCCESS' if failures == 0 else f'{failures} FAILURES'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
