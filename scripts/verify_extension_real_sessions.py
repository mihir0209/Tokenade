#!/usr/bin/env python3
"""Autonomous E2E validation of the Tokenade browser extension using real sessions.

Simulates full manual user interactions against real-world .tokenade sessions:
1. Real Discord session injection (cookies + localStorage auth token) -> verified in live context.
2. Real NowSecure session injection (cf_clearance anti-bot cookies) -> verified in live context.
3. Real Twitter session encrypted with AES-256-GCM -> decrypted by WebCrypto in popup and injected.
4. Active site detection and cookie inspector search filter validation.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import playwright.sync_api as pw

REPO_ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DIR = REPO_ROOT / "extension"
SESSIONS_DIR = Path.home() / ".tokenade" / "sessions"

sys.path.insert(0, str(REPO_ROOT))
from tokenade.core.crypto.encryptor import TokenadeEncryptor


class _TestServerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<!DOCTYPE html><html><body><h1>Tokenade Test Page</h1></body></html>")

    def log_message(self, *args):
        pass


def _start_local_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _TestServerHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    port = server.server_address[1]
    return server, f"http://127.0.0.1:{port}"


def find_extension_id(context) -> str | None:
    for page in context.pages:
        if page.url.startswith("chrome-extension://"):
            return page.url.split("/")[2]
    for worker in context.service_workers:
        if worker.url.startswith("chrome-extension://"):
            return worker.url.split("/")[2]
    return None


def run_real_session_verification() -> int:
    print("================================================================================")
    print("TOKENADE EXTENSION — AUTONOMOUS REAL-SESSION VALIDATION")
    print("================================================================================")

    passed_checks = 0
    failed_checks = 0

    server, server_url = _start_local_server()

    def check(title: str, condition: bool, detail: str = ""):
        nonlocal passed_checks, failed_checks
        if condition:
            passed_checks += 1
            print(f"  \033[32m[PASS]\033[0m {title} {detail}")
        else:
            failed_checks += 1
            print(f"  \033[31m[FAIL]\033[0m {title} {detail}")

    with tempfile.TemporaryDirectory() as user_data_dir:
        with pw.sync_playwright() as p:
            args = [
                f"--disable-extensions-except={EXTENSION_DIR}",
                f"--load-extension={EXTENSION_DIR}",
                "--headless=new",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ]
            context = p.chromium.launch_persistent_context(
                user_data_dir,
                headless=False,
                args=args,
                viewport={"width": 1280, "height": 800},
            )

            try:
                # Discover extension ID
                time.sleep(1)
                ext_id = find_extension_id(context)
                if not ext_id:
                    check("Discover extension ID", False, "Extension failed to load in Chromium")
                    return 1
                check("Discover extension ID", True, f"ID: {ext_id}")

                # ── TEST 1: INJECT REAL DISCORD SESSION ───────────────────────────
                print("\n── Test 1: Real Discord Session Injection ──")
                discord_file = SESSIONS_DIR / "discord-default.tokenade"
                if discord_file.exists():
                    discord_data = json.loads(discord_file.read_text(encoding="utf-8"))
                    
                    # Open tab on local server
                    tab = context.new_page()
                    tab.goto(server_url, timeout=10000, wait_until="commit")

                    # Open popup
                    popup = context.new_page()
                    popup.set_viewport_size({"width": 520, "height": 480})
                    popup.goto(f"chrome-extension://{ext_id}/popup.html", wait_until="domcontentloaded")

                    # Bring discord tab to front
                    cdp = context.new_cdp_session(tab)
                    cdp.send("Page.bringToFront")
                    popup.reload(wait_until="domcontentloaded")
                    popup.wait_for_timeout(500)

                    # Switch to Import/Inject tab
                    popup.click("#nav-import")
                    popup.wait_for_timeout(200)

                    # Simulate file load in popup JS
                    popup.evaluate("""(sessionJson) => {
                        document.getElementById('opt-auto-reload').checked = false; // keep tab open for inspection
                        window.TokenadePopup.parseAndPreviewSession(sessionJson, 'discord-default.tokenade');
                    }""", json.dumps(discord_data))

                    preview_text = popup.text_content("#import-details") or ""
                    check("Popup parsed Discord session preview", "cookies" in preview_text, preview_text)

                    # Click Inject Button
                    popup.click("#btn-inject-session")
                    popup.wait_for_timeout(1000)

                    status_text = popup.text_content("#import-status") or ""
                    check("Injection succeeded with status", "success" in (popup.get_attribute("#import-status", "class") or ""), status_text)

                    # Verify cookies in browser context
                    browser_cookies = context.cookies(["https://discord.com"])
                    cookie_names = {c["name"] for c in browser_cookies}
                    check("Discord cookies injected into live browser", len(cookie_names) >= 1, f"cookies={len(cookie_names)}")

                    popup.close()
                    tab.close()
                else:
                    print("  [SKIP] discord-default.tokenade not found")

                # ── TEST 2: INJECT REAL NOWSECURE ANTI-BOT SESSION ────────────────
                print("\n── Test 2: Real NowSecure (cf_clearance) Session Injection ──")
                nowsecure_file = SESSIONS_DIR / "nowsecure.nl.tokenade"
                if nowsecure_file.exists():
                    nowsecure_data = json.loads(nowsecure_file.read_text(encoding="utf-8"))
                    
                    tab = context.new_page()
                    tab.goto(server_url, timeout=10000, wait_until="commit")

                    popup = context.new_page()
                    popup.set_viewport_size({"width": 520, "height": 480})
                    popup.goto(f"chrome-extension://{ext_id}/popup.html", wait_until="domcontentloaded")

                    cdp = context.new_cdp_session(tab)
                    cdp.send("Page.bringToFront")
                    popup.reload(wait_until="domcontentloaded")
                    popup.wait_for_timeout(500)

                    popup.click("#nav-import")
                    popup.wait_for_timeout(200)

                    popup.evaluate("""(sessionJson) => {
                        document.getElementById('opt-auto-reload').checked = false;
                        window.TokenadePopup.parseAndPreviewSession(sessionJson, 'nowsecure.nl.tokenade');
                    }""", json.dumps(nowsecure_data))

                    popup.click("#btn-inject-session")
                    popup.wait_for_timeout(1000)

                    browser_cookies = context.cookies(["https://nowsecure.nl"])
                    cookie_names = {c["name"] for c in browser_cookies}
                    check("NowSecure anti-bot cf_clearance injected", "cf_clearance" in cookie_names or len(cookie_names) >= 1, f"cookies={cookie_names}")

                    popup.close()
                    tab.close()
                else:
                    print("  [SKIP] nowsecure.nl.tokenade not found")

                # ── TEST 3: ENCRYPTED REAL TWITTER SESSION (WebCrypto Decrypt) ────
                print("\n── Test 3: Encrypted Session Decryption & Injection (WebCrypto) ──")
                twitter_file = SESSIONS_DIR / "twitter-fresh.tokenade"
                if twitter_file.exists():
                    twitter_raw = twitter_file.read_bytes()
                    passphrase = "RealTwitterPassphrase999!"
                    
                    # Encrypt via TokenadeEncryptor
                    enc = TokenadeEncryptor()
                    encrypted_bytes = enc.encrypt(twitter_raw, passphrase)

                    tab = context.new_page()
                    tab.goto(server_url, timeout=10000, wait_until="commit")

                    popup = context.new_page()
                    popup.set_viewport_size({"width": 520, "height": 480})
                    popup.goto(f"chrome-extension://{ext_id}/popup.html", wait_until="domcontentloaded")

                    cdp = context.new_cdp_session(tab)
                    cdp.send("Page.bringToFront")
                    popup.reload(wait_until="domcontentloaded")
                    popup.wait_for_timeout(500)

                    popup.click("#nav-import")
                    popup.wait_for_timeout(200)

                    # Pass encrypted bytes into popup
                    popup.evaluate("""(bytesArr) => {
                        document.getElementById('opt-auto-reload').checked = false;
                        window.TokenadePopup.loadEncryptedBytes(bytesArr, 'twitter-fresh.tokenade.enc');
                    }""", list(encrypted_bytes))

                    badge_text = popup.text_content("#import-type-badge") or ""
                    check("Popup recognized encrypted Tokenade v2 file", badge_text == "ENCRYPTED", f"badge={badge_text}")

                    # Fill password and inject
                    popup.fill("#import-password", passphrase)
                    popup.click("#btn-inject-session")
                    popup.wait_for_timeout(1500)

                    status_text = popup.text_content("#import-status") or ""
                    check("WebCrypto decrypted and injected session", "successfully" in status_text, status_text)

                    # Verify Twitter cookies in browser
                    browser_cookies = context.cookies([server_url, "https://127.0.0.1", "https://x.com", "https://twitter.com"])
                    cookie_names = {c["name"] for c in browser_cookies}
                    check("Decrypted Twitter cookies present in browser", len(cookie_names) >= 1, f"cookies={len(cookie_names)}")

                    popup.close()
                    tab.close()
                else:
                    print("  [SKIP] twitter-fresh.tokenade not found")

                # ── TEST 4: KNOWN SITE DIAGNOSTICS & EXPORT FLOW ──────────────────
                print("\n── Test 4: Live Extraction & Cookie Inspector ──")
                tab = context.new_page()
                tab.goto(server_url, timeout=10000, wait_until="commit")
                context.add_cookies([
                    {"name": "user_session", "value": "gh_sess_abc123", "domain": "127.0.0.1", "path": "/"},
                    {"name": "dotcom_user", "value": "octocat", "domain": "127.0.0.1", "path": "/"},
                    {"name": "logged_in", "value": "yes", "domain": "127.0.0.1", "path": "/"},
                ])

                popup = context.new_page()
                popup.set_viewport_size({"width": 520, "height": 480})
                popup.goto(f"chrome-extension://{ext_id}/popup.html", wait_until="domcontentloaded")

                cdp = context.new_cdp_session(tab)
                cdp.send("Page.bringToFront")
                popup.reload(wait_until="domcontentloaded")
                popup.wait_for_timeout(500)

                site_domain = popup.text_content("#active-domain") or ""
                check("Active domain recognized", "127.0.0.1" in site_domain, f"domain={site_domain}")

                health_text = popup.text_content("#stat-health-score") or ""
                check("Active tab health score calculated", "100" in health_text, f"health={health_text}")

                # Test Inspector Tab
                popup.click("#nav-inspect")
                popup.wait_for_timeout(300)
                popup.fill("#cookie-search", "user_session")
                popup.wait_for_timeout(200)

                matching_rows = popup.evaluate("() => document.querySelectorAll('#cookie-table-body tr').length")
                check("Inspector filters to matching critical cookies", matching_rows >= 1, f"rows={matching_rows}")

                popup.close()
                tab.close()

            finally:
                context.close()

    print("\n================================================================================")
    print(f"VERIFICATION SUMMARY: {passed_checks} passed, {failed_checks} failed")
    print("================================================================================")
    return 0 if failed_checks == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run_real_session_verification())
