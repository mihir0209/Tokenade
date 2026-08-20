#!/usr/bin/env python3
"""E2E witness for the browser extension running in real Chromium.

Loads extension/ into a headed Chromium persistent context, serves a local
test page with seeded cookies + localStorage + sessionStorage, then:

1. Verifies the popup scans and displays live cookie/storage stats.
2. Downloads the generated .tokenade export and round-trips it through the
   SessionPackager / SDK health check.
3. Verifies the window.Tokenade content-script bridge (cookies + sessionStorage).
4. Verifies the SEND_TO_PROXY background bridge against a local echo server.

Exit code 0 on success, 1 on failure. Skips cleanly if Chromium is unavailable.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DIR = REPO_ROOT / "extension"

sys.path.insert(0, str(REPO_ROOT))

TEST_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>tokenade-e2e</title></head>
<body><h1>Tokenade E2E Test Page</h1></body></html>"""


class _EchoHandler(BaseHTTPRequestHandler):
    """Serves the test page and answers POST /send with a JSON ack."""

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = TEST_HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        body = json.dumps({"success": True, "echo": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _start_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _EchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _find_extension_id(context) -> str | None:
    for sw in context.service_workers:
        url = sw.url
        if url.startswith("chrome-extension://"):
            return url.split("/")[2]
    return None


def main() -> int:
    if not EXTENSION_DIR.is_dir() or not (EXTENSION_DIR / "manifest.json").is_file():
        print(f"SKIP: extension dir not found at {EXTENSION_DIR}")
        return 0

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP: playwright not installed")
        return 0

    server, thread = _start_server()
    site_url = f"http://127.0.0.1:{server.server_port}/index.html"

    results = []
    failures = 0

    def check(name, ok, detail=""):
        nonlocal failures
        results.append((name, ok, detail))
        if not ok:
            failures += 1

    with sync_playwright() as p:
        try:
            browser = p.chromium
            browser.executable_path  # raises if no browser installed
        except Exception:
            print("SKIP: chromium executable not installed")
            return 0

        with tempfile.TemporaryDirectory(prefix="tokenade-ext-e2e-") as profile_dir:
            try:
                context = browser.launch_persistent_context(
                    profile_dir,
                    headless=False,
                    accept_downloads=True,
                    args=[
                        f"--disable-extensions-except={EXTENSION_DIR}",
                        f"--load-extension={EXTENSION_DIR}",
                        "--no-first-run",
                    ],
                )
            except Exception as e:
                print(f"SKIP: could not launch headed chromium with extension: {e}")
                return 0

            try:
                page = context.new_page()
                page.goto(site_url, wait_until="domcontentloaded")

                # Seed cookies + web storage on the test origin
                origin = f"http://127.0.0.1:{server.server_port}"
                context.add_cookies(
                    [
                        {
                            "name": "session_id",
                            "value": "e2e_secret_token",
                            "domain": "127.0.0.1",
                            "path": "/",
                            "secure": False,
                            "httpOnly": True,
                            "sameSite": "Lax",
                            "expires": 1800000000,
                        },
                        {
                            "name": "other_site_cookie",
                            "value": "other_val",
                            "domain": "other.example",
                            "path": "/",
                            "secure": False,
                            "sameSite": "Lax",
                            "expires": 1800000000,
                        },
                    ]
                )
                page.evaluate(
                    """() => {
                        localStorage.setItem("theme", "dark");
                        localStorage.setItem("user_token", "ls_val_1");
                        sessionStorage.setItem("tab_state", "active_chat_1");
                    }"""
                )

                # The page should have window.Tokenade injected by content.js.
                # On a fresh profile the service worker cold-starts and
                # registers the MAIN-world script asynchronously; a fast local
                # page may load first. One reload covers it (matches real
                # first-install UX where the registration then persists).
                try:
                    page.wait_for_function(
                        "() => typeof window.Tokenade !== 'undefined'",
                        timeout=4000,
                    )
                    tokenade_ready = True
                    injection_path = "direct"
                except Exception:
                    injection_path = "reload"
                    page.reload(wait_until="domcontentloaded")
                    try:
                        page.wait_for_function(
                            "() => typeof window.Tokenade !== 'undefined'",
                            timeout=8000,
                        )
                        tokenade_ready = True
                    except Exception:
                        tokenade_ready = False
                check("content script injects window.Tokenade", tokenade_ready is True)
                print(f'STEP: injection path={injection_path}', flush=True)

                print('STEP: bridge checks', flush=True)
                print('STEP: getCookies', flush=True)
                # Bridge: cookies via background
                try:
                    bridge_cookies = page.evaluate(
                        "() => window.Tokenade.getCookies()"
                    )
                    names = {c.get("name") for c in bridge_cookies or []}
                    check(
                        "window.Tokenade.getCookies bridge",
                        "session_id" in names,
                        f"got {sorted(names)}",
                    )
                except Exception as e:
                    check("window.Tokenade.getCookies bridge", False, str(e))

                print('STEP: getSessionStorage', flush=True)
                # Bridge: sessionStorage via content script
                try:
                    ss = page.evaluate(
                        "() => window.Tokenade.getSessionStorage()"
                    )
                    check(
                        "window.Tokenade.getSessionStorage bridge",
                        bool(ss) and ss.get("tab_state") == "active_chat_1",
                        f"got {ss}",
                    )
                except Exception as e:
                    check("window.Tokenade.getSessionStorage bridge", False, str(e))

                print('STEP: sendSession', flush=True)
                # Bridge: SEND_TO_PROXY via background fetch against the echo server
                try:
                    send_result = page.evaluate(
                        """(proxyUrl) => window.Tokenade.sendSession(
                            { site_name: "127.0.0.1", cookies: [] }, proxyUrl)""",
                        f"{site_url}/send",
                    )
                    check(
                        "SEND_TO_PROXY bridge succeeds",
                        isinstance(send_result, dict)
                        and send_result.get("success") is True,
                        f"got {send_result}",
                    )
                except Exception as e:
                    check("SEND_TO_PROXY bridge succeeds", False, str(e))

                print('STEP: popup checks', flush=True)
                # Popup: open as a tab, then bring the site tab to front so the
                # popup's active-tab query sees the site (as when using the icon).
                ext_id = _find_extension_id(context)
                check("extension id discovered", bool(ext_id), f"id={ext_id}")

                if ext_id:
                    popup = context.new_page()
                    popup.goto(
                        f"chrome-extension://{ext_id}/popup.html",
                        wait_until="domcontentloaded",
                    )
                    # Activate the site tab so the popup scans it
                    cdp = context.new_cdp_session(page)
                    cdp.send("Page.bringToFront")
                    popup.reload(wait_until="domcontentloaded")
                    popup.wait_for_timeout(1500)

                    domain_text = popup.text_content("#active-domain") or ""
                    total_text = popup.text_content("#stat-cookies-count") or ""
                    storage_text = popup.text_content("#stat-storage-count") or ""
                    health_text = popup.text_content("#stat-health-score") or ""

                    check(
                        "popup shows site domain",
                        "127.0.0.1" in domain_text,
                        f"domain={domain_text!r}",
                    )
                    check(
                        "popup counts cookies",
                        total_text.strip() == "1",
                        f"total={total_text!r}",
                    )
                    check(
                        "popup counts storage keys",
                        storage_text.strip() == "3",
                        f"storage={storage_text!r}",
                    )
                    check(
                        "popup health 100%",
                        health_text.strip().startswith("100"),
                        f"health={health_text!r}",
                    )

                    print('STEP: download roundtrip', flush=True)
                    # Download the .tokenade export and round-trip it
                    try:
                        with popup.expect_download(timeout=15000) as dl_info:
                            popup.click("#btn-export-download")
                        download = dl_info.value
                        download_path = download.path()
                        payload = json.loads(Path(download_path).read_text())
                        check(
                            "download produces v3 .tokenade",
                            payload.get("version") == "3.0.0"
                            and payload.get("site_name") == "127.0.0.1"
                            and len(payload.get("cookies", [])) == 1,
                            f"keys={sorted(payload.keys())[:8]}",
                        )
                        ls = payload.get("storage", {}).get("local", {})
                        ss_map = payload.get("storage", {}).get("session", {})
                        check(
                            "payload carries localStorage",
                            ls.get(origin, {}).get("theme") == "dark",
                            f"local={list(ls.keys())}",
                        )
                        check(
                            "payload carries sessionStorage",
                            ss_map.get(origin, {}).get("tab_state") == "active_chat_1",
                            f"session={list(ss_map.keys())}",
                        )

                        # Round-trip through the packager + SDK health check
                        from tokenade.core.importer.session_packager import SessionPackager
                        from tokenade.sdk import TokenadeClient

                        packager = SessionPackager()
                        loaded = packager.load(download_path)
                        client = TokenadeClient()
                        health = client.health_check(download_path)
                        check(
                            "packager round-trips export",
                            loaded is not None and len(loaded["cookies"]) == 1,
                        )
                        check(
                            "SDK health check on export",
                            health.get("health_score", 0) >= 0.5,
                            f"score={health.get('health_score')}",
                        )
                    except Exception as e:
                        check("download + round-trip", False, str(e))

                    # Test WebCrypto AES-256-GCM encryption in popup
                    try:
                        popup.fill("#export-password", "witness-secret-pass!")
                        with popup.expect_download(timeout=15000) as enc_dl_info:
                            popup.click("#btn-export-download")
                        enc_download = enc_dl_info.value
                        enc_path = enc_download.path()
                        from tokenade.core.crypto.encryptor import TokenadeEncryptor
                        enc_bytes = Path(enc_path).read_bytes()
                        decrypted_bytes = TokenadeEncryptor().decrypt(enc_bytes, "witness-secret-pass!")
                        dec_json = json.loads(decrypted_bytes.decode("utf-8"))
                        check(
                            "WebCrypto popup encryption roundtrips through TokenadeEncryptor",
                            dec_json.get("site_name") == "127.0.0.1" and len(dec_json.get("cookies", [])) == 1,
                            f"decrypted site={dec_json.get('site_name')}",
                        )
                        popup.fill("#export-password", "")
                    except Exception as e:
                        check("WebCrypto popup encryption", False, str(e))

                    # Test Sidebar Tab switching: Inspect table
                    try:
                        popup.click("#nav-inspect")
                        popup.wait_for_timeout(300)
                        inspect_active = popup.is_visible("#tab-inspect")
                        check("Inspect tab activates on click", inspect_active)
                        rows = popup.query_selector_all("#cookie-table-body tr")
                        check("Inspect table displays active cookies", len(rows) >= 1)
                    except Exception as e:
                        check("Inspect tab test", False, str(e))

                    # Test Sidebar Tab switching: Import view
                    try:
                        popup.click("#nav-import")
                        popup.wait_for_timeout(300)
                        import_active = popup.is_visible("#tab-import")
                        check("Import/Inject tab activates on click", import_active)
                        dropzone_visible = popup.is_visible("#import-dropzone")
                        check("Dropzone visible in Import tab", dropzone_visible)
                    except Exception as e:
                        check("Import tab test", False, str(e))

                    # Test Sidebar Tab switching: Settings view
                    try:
                        popup.click("#nav-settings")
                        popup.wait_for_timeout(300)
                        settings_active = popup.is_visible("#tab-settings")
                        check("Settings tab activates on click", settings_active)
                    except Exception as e:
                        check("Settings tab test", False, str(e))

                    popup.close()
                print('STEP: closing context', flush=True)
            finally:
                context.close()

    thread.join(timeout=2)
    server.shutdown()

    print(f"=== Extension E2E witness: {len(results)} checks ===")
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    print(f"RESULT: {'SUCCESS' if failures == 0 else f'{failures} FAILURES'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
