#!/usr/bin/env python3
"""Local clean-profile cookie portability witness for installed CDP browsers."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tokenade.core.browser.stealth.launcher import SystemBrowserLauncher
from tokenade.core.importer.session_loader import SessionLoader


async def _cdp(ws, counter: list[int], method: str, params=None):
    counter[0] += 1
    request_id = counter[0]
    message = {"id": request_id, "method": method}
    if params:
        message["params"] = params
    await ws.send(json.dumps(message))
    while True:
        response = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        if response.get("id") != request_id:
            continue
        if "error" in response:
            raise RuntimeError(response["error"].get("message", "CDP error"))
        return response.get("result", {})


def _create_tab(port: int):
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT"
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read())


async def _witness(browser_name: str, port: int) -> None:
    launcher = SystemBrowserLauncher()
    if not launcher.find_browser(browser_name):
        print(f"SKIP {browser_name}: executable not installed")
        return

    with tempfile.TemporaryDirectory(prefix=f"tokenade-{browser_name}-witness-") as profile:
        browser = launcher.launch(
            browser=browser_name,
            visible=False,
            port=port,
            profile_dir=profile,
        )
        try:
            target = await asyncio.to_thread(_create_tab, browser.port)
            async with websockets.connect(target["webSocketDebuggerUrl"]) as ws:
                counter = [0]
                await _cdp(ws, counter, "Network.enable")
                await _cdp(
                    ws,
                    counter,
                    "Network.setCookie",
                    {
                        "name": "tokenade_portability",
                        "value": browser_name,
                        "domain": ".example.com",
                        "path": "/",
                    },
                )
                cookies = await _cdp(ws, counter, "Network.getAllCookies")
            values = {
                item["value"]
                for item in cookies.get("cookies", [])
                if item.get("name") == "tokenade_portability"
            }
            if browser_name not in values:
                raise RuntimeError(f"{browser_name} did not retain the injected cookie")
            print(f"PASS {browser_name}: clean-profile cookie injection and readback")
        finally:
            browser.close()


def _witness_firefox() -> None:
    with tempfile.TemporaryDirectory(prefix="tokenade-firefox-witness-") as tmp:
        root = Path(tmp)
        session_file = root / "firefox.tokenade"
        session_file.write_text(
            json.dumps(
                {
                    "version": "3.0",
                    "site_name": "example.com",
                    "auth_status": "unknown",
                    "cookies": [
                        {
                            "name": "tokenade_portability",
                            "value": "firefox",
                            "domain": ".example.com",
                            "path": "/",
                        }
                    ],
                    "storage": {
                        "local": {
                            "https://example.com": {"ff_local": "1"},
                            "https://example.com^partitionKey=%28https%2Cthirdparty.com%29": {"ff_part": "1"},
                        },
                        "session": {
                            "https://example.com": {"ff_session": "1"},
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        loader = SessionLoader()
        result = loader.load(
            str(session_file),
            validate=False,
            visible=True,
            profile_dir=str(root / "profile"),
            browser_type="firefox",
            target_url="https://example.com",
        )
        try:
            if not result["success"]:
                raise RuntimeError(result["error"] or "Firefox Session load failed")
            if result.get("local_storage_injected", 0) < 1 or result.get("session_storage_injected", 0) < 1:
                raise RuntimeError(f"Storage injection incomplete: {result}")
            cookies = loader._browser.get_cookies(["https://example.com"])
            if not any(
                cookie.get("name") == "tokenade_portability"
                and cookie.get("value") == "firefox"
                for cookie in cookies
            ):
                raise RuntimeError("Firefox did not retain the injected cookie")
            print("PASS firefox: clean-profile cookie and web-storage injection and readback")
        finally:
            if loader._browser:
                loader._browser.close()
                loader._browser = None


async def main() -> int:
    await asyncio.to_thread(_witness_firefox)
    await _witness("brave", 19920)
    await _witness("chromium", 19930)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
