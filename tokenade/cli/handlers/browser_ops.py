"""Browser ops CLI — launch, refresh-browser, accounts, patch-chrome."""
import json
import logging
import os
import platform
import signal
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("tokenade")

from tokenade.cli.handlers.session_ops import (  # noqa: F401
    _resolve_upstream_proxy,
    _run_post_refresh_plugins,
)

def cmd_launch(args):
    """Launch undetectable system browser with CDP."""
    import asyncio

    from tokenade.core.browser.undetectable import SystemBrowserLauncher
    from tokenade.core.browser.cdp_connection import CDPConnection, get_undetectable_stealth_script
    from tokenade.core.importer.session_packager import SessionPackager

    print("\n" + "=" * 80)
    print("TOKENADE - Undetectable Browser")
    print("=" * 80)

    launcher = SystemBrowserLauncher()

    # Find browser
    browser_path = launcher.find_browser(args.browser)
    if not browser_path:
        print(f"❌ {args.browser} not found. Install it or specify --browser-path")
        return

    # --headless wins; otherwise default to visible UI
    visible = bool(getattr(args, "visible", False)) or not bool(getattr(args, "headless", False))
    if getattr(args, "headless", False):
        visible = False
    args.visible = visible  # normalize for rest of function

    print(f"\n🌐 Browser: {args.browser} ({browser_path})")
    print(f"🔌 CDP Port: {args.port}")
    print(f"👁️  Visible: {args.visible}")

    # Resolve upstream proxy
    upstream_proxy = _resolve_upstream_proxy(args)
    if upstream_proxy:
        print(f"🔀 Upstream proxy: {upstream_proxy}")

    try:
        # Profile lock only matters when reusing the *default system* profile.
        # Custom --profile-dir or --session uses a separate user-data-dir and can
        # run alongside an open browser (feature testing / multi-profile).
        using_isolated_profile = bool(args.profile_dir or args.session)
        if not using_isolated_profile:
            import subprocess as _sp
            _ps_cmd = ["pgrep", "-c", args.browser] if platform.system() != "Windows" else ["tasklist", "/fi", f"imagename eq {args.browser}.exe"]
            try:
                _running = _sp.run(_ps_cmd, capture_output=True, text=True, timeout=3)
                _is_running = False
                if platform.system() != "Windows" and _running.returncode == 0:
                    _is_running = int(_running.stdout.strip()) > 0
                elif platform.system() == "Windows" and args.browser.lower() in _running.stdout.lower():
                    _is_running = True
                if _is_running:
                    print(f"   ⚠️  {args.browser} is already running. Default profile is locked.")
                    print(f"   Close all {args.browser} windows first, then retry.")
                    print(f"   Or use --profile-dir / --session for an isolated profile.")
                    print(f"   Or start {args.browser} with: {args.browser} --remote-debugging-port={args.port}")
                    return
            except Exception:
                pass  # If we can't check, just try to launch

        # Copy real profile only when NO session file (cookies come from profile)
        # When session file IS provided, use fresh profile (session cookies are authoritative)
        profile_dir = args.profile_dir
        if not profile_dir and not args.session:
            real_dir = launcher._get_default_profile_dir(args.browser)
            if real_dir:
                import tempfile
                profile_dir = tempfile.mkdtemp(prefix=f"tokenade_{args.browser}_")
                print(f"   📁 Copying profile from: {real_dir}")
                if launcher._copy_profile(args.browser, profile_dir):
                    print(f"   ✅ Profile copied to: {profile_dir}")
                else:
                    print(f"   ⚠️  Profile copy failed, using fresh profile")

        browser = launcher.launch(
            browser=args.browser,
            visible=args.visible,
            port=args.port,
            profile_dir=profile_dir,
            extra_args=args.extra_args.split(",") if args.extra_args else [],
            upstream_proxy=upstream_proxy,
        )

        print(f"\n✅ Browser launched (PID: {browser.pid})")
        print(f"   CDP URL: {browser.cdp_url}")
        print(f"   Profile: {browser.profile_dir}")

        # Inject session if provided — session file is ALWAYS authoritative
        if args.session:
            print(f"\n📂 Loading session: {args.session}")

            session_path = args.session
            decrypt_password = getattr(args, 'decrypt_password', None)
            if decrypt_password:
                import tempfile
                try:
                    from tokenade.core.crypto.at_rest import load_encrypted
                    session = load_encrypted(session_path, password=decrypt_password)
                    # Write decrypted to temp file
                    temp_path = tempfile.mktemp(suffix='.tokenade')
                    with open(temp_path, 'w') as f:
                        json.dump(session, f)
                    session_path = temp_path
                    print(f"   🔓 Decrypted with password")
                except Exception as e:
                    print(f"❌ Decryption failed: {e}")
                    return

            packager = SessionPackager()
            session = packager.load(session_path)

            cookies = session.get("cookies", [])
            source_browser = session.get("source_device", {}).get("browser", "unknown")
            print(f"   Cookies: {len(cookies)} (from {source_browser})")

            # Site-handler plugin override: domains, dashboard URL, cookie filter
            site_handler = None
            site_hint = ""
            try:
                from tokenade.core.importer.plugin_export import PluginExporter
                exporter = PluginExporter()
                force_plugin = getattr(args, "plugin", None)
                cookie_domains = list({
                    (c.get("domain") or "").lstrip(".")
                    for c in cookies
                    if c.get("domain")
                })
                site_name = str(session.get("site_name") or session.get("site") or "")
                domain_guess = cookie_domains or ([site_name] if site_name else [])
                if force_plugin:
                    exporter._load_handlers()
                    site_handler = exporter._handlers.get(force_plugin)
                    if not site_handler:
                        print(f"   ⚠️  Plugin not found: {force_plugin} (using default launch path)")
                elif domain_guess:
                    site_handler = exporter.find_handler(domain_guess)

                if site_handler:
                    hname = getattr(site_handler, "name", type(site_handler).__name__)
                    print(f"   🔌 Site handler: {hname} (overrides default site worker)")
                    # Prefer plugin dashboard URL when user did not pass --url
                    if not args.url and hasattr(site_handler, "get_dashboard_url"):
                        dash = site_handler.get_dashboard_url()
                        if dash:
                            args.url = dash
                            print(f"   🔗 URL from plugin: {dash}")
                    # Prefer plugin cookie filter when available
                    if hasattr(site_handler, "get_critical_cookies") or hname:
                        try:
                            # google-handler style: filter via private helper if present
                            if hasattr(site_handler, "_is_google_cookie"):
                                filtered = [c for c in cookies if site_handler._is_google_cookie(c)]
                                if filtered:
                                    cookies = filtered
                                    print(f"   🎯 Plugin-filtered cookies: {len(cookies)}")
                        except Exception:
                            pass
                    if "google" in hname.lower() or any(
                        "google" in (d or "") for d in cookie_domains
                    ):
                        site_hint = "google"
            except Exception as e:
                logger.debug("Site handler resolution failed: %s", e)

            if not site_hint:
                _site = str(session.get("site_name") or session.get("site") or "").lower()
                _domains = " ".join(str(c.get("domain") or "") for c in cookies).lower()
                fname = str(args.session).lower()
                if "google" in _site or "google." in _domains or "youtube." in _domains or "gmail" in fname:
                    site_hint = "google"

            if site_hint == "google":
                print(f"   💡 Google: use Firefox/Brave/Edge/Vivaldi — not Chrome/Chromium/Google browsers.")
                print(f"   ✅ Same jar works multi-browser + multi-device on non-Chrome targets; use clean --profile-dir.")

            chrome_like = args.browser.lower() in ("chrome", "chromium", "chrome-canary", "chrome-beta")
            if site_hint == "google" and chrome_like:
                print(f"   ⚠️  Target is {args.browser}: Google often rejects portable sessions in Chrome-family browsers.")

            if source_browser != "unknown" and source_browser != args.browser:
                print(f"   ⚠️  Cross-browser: {source_browser} → {args.browser}")
            # Connect via CDP and inject (use actual port from browser)
            actual_port = browser.port

            # Create new tab synchronously before entering async
            import urllib.request as _urllib_req
            try:
                _req = _urllib_req.Request(
                    f"http://127.0.0.1:{actual_port}/json/new?about:blank",
                    method='PUT'
                )
                with _urllib_req.urlopen(_req, timeout=5) as _resp:
                    _new_tab = json.loads(_resp.read().decode())
                _tab_ws_url = _new_tab.get("webSocketDebuggerUrl")
                _tab_id = _new_tab.get("id")
            except Exception as e:
                print(f"❌ Failed to create new tab: {e}")
                _tab_ws_url = None
                _tab_id = None

            async def inject():
                import websockets

                msg_id_counter = [0]

                async def cdp_cmd(ws, method, params=None):
                    msg_id_counter[0] += 1
                    current_id = msg_id_counter[0]
                    msg = {"id": current_id, "method": method}
                    if params:
                        msg["params"] = params
                    await ws.send(json.dumps(msg))
                    deadline = time.time() + 30
                    while time.time() < deadline:
                        try:
                            raw = await asyncio.wait_for(
                                ws.recv(),
                                timeout=min(5, deadline - time.time()),
                            )
                        except asyncio.TimeoutError:
                            continue
                        data = json.loads(raw)
                        if "id" in data and data["id"] == current_id:
                            if "error" in data:
                                raise RuntimeError(data["error"].get("message", "CDP error"))
                            return data.get("result", {})
                    raise RuntimeError(f"CDP timeout: {method}")

                if not _tab_ws_url:
                    print("❌ Failed to create tab")
                    return

                print(f"   Tab: {_tab_id}")

                # Step 2: Connect to the new tab's WebSocket
                print("   Connecting to tab WS...")
                tab_ws = await websockets.connect(
                    _tab_ws_url,
                    max_size=10 * 1024 * 1024,
                    ping_interval=30,
                    ping_timeout=10,
                )
                print("   Connected.")

                # Step 3: Inject stealth FIRST (before page load)
                print("   Injecting stealth script...", flush=True)
                stealth_script = get_undetectable_stealth_script()

                await cdp_cmd(tab_ws, "Page.enable")
                await cdp_cmd(tab_ws, "Page.addScriptToEvaluateOnNewDocument", {"source": stealth_script})

                # Step 4: Inject cookies (per-cookie — batch setCookies fails hard on one bad field)
                print(f"   Injecting {len(cookies)} cookies...", flush=True)
                cdp_cookies = []
                for cookie in cookies:
                    name = cookie.get("name") or ""
                    if not name:
                        continue
                    domain = cookie.get("domain") or ""
                    # CDP rejects empty domain without url
                    if not domain and not cookie.get("url"):
                        continue
                    cdp_cookie = {
                        "name": name,
                        "value": str(cookie.get("value", "")),
                        "path": cookie.get("path") or "/",
                    }
                    if domain:
                        cdp_cookie["domain"] = domain
                    elif cookie.get("url"):
                        cdp_cookie["url"] = cookie["url"]
                    if cookie.get("secure"):
                        cdp_cookie["secure"] = True
                    if cookie.get("httpOnly"):
                        cdp_cookie["httpOnly"] = True
                    if cookie.get("sameSite"):
                        same_site = str(cookie["sameSite"])
                        # Normalize common variants
                        ss_map = {
                            "strict": "Strict",
                            "lax": "Lax",
                            "none": "None",
                            "no_restriction": "None",
                            "unspecified": "Lax",
                        }
                        same_site = ss_map.get(same_site.lower(), same_site)
                        if same_site in ("Strict", "Lax", "None"):
                            cdp_cookie["sameSite"] = same_site
                    expires = cookie.get("expires", 0) or 0
                    try:
                        exp = int(float(expires))
                    except (TypeError, ValueError):
                        exp = 0
                    if exp > 0:
                        # ms → s
                        if exp > 1262304000000:
                            exp = exp // 1000
                        # skip already-expired (Chrome can reject)
                        if exp > time.time():
                            cdp_cookie["expires"] = exp
                    # CDP requires secure=true when sameSite=None
                    if cdp_cookie.get("sameSite") == "None" and not cdp_cookie.get("secure"):
                        cdp_cookie["secure"] = True
                    # __Host- / __Secure- cookies need secure + correct domain shape
                    if name.startswith("__Host-"):
                        cdp_cookie["secure"] = True
                        cdp_cookie["path"] = "/"
                        # __Host- must not have Domain attribute
                        cdp_cookie.pop("domain", None)
                        if not cdp_cookie.get("url"):
                            # best-effort origin from domain-like data
                            host = (domain or "").lstrip(".")
                            if host:
                                cdp_cookie["url"] = f"https://{host}/"
                    elif name.startswith("__Secure-"):
                        cdp_cookie["secure"] = True
                    cdp_cookies.append(cdp_cookie)

                await cdp_cmd(tab_ws, "Network.enable")
                injected = 0
                failed = 0
                # Try batch first for speed
                try:
                    await cdp_cmd(tab_ws, "Network.setCookies", {"cookies": cdp_cookies})
                    injected = len(cdp_cookies)
                except Exception as batch_err:
                    print(f"   ⚠️  Batch cookie inject failed ({batch_err}); retrying per-cookie...", flush=True)
                    for cdp_cookie in cdp_cookies:
                        try:
                            await cdp_cmd(tab_ws, "Network.setCookie", cdp_cookie)
                            injected += 1
                        except Exception:
                            failed += 1
                print(f"   Cookies injected: {injected}/{len(cdp_cookies)}"
                      + (f" (skipped {failed})" if failed else ""), flush=True)
                if injected == 0 and cdp_cookies:
                    raise RuntimeError(f"Failed to inject any of {len(cdp_cookies)} cookies")

                # Step 5: Navigate to site
                if args.url:
                    print(f"   Navigating to: {args.url}", flush=True)
                    await cdp_cmd(tab_ws, "Page.navigate", {"url": args.url})

                    # Wait for page load
                    await asyncio.sleep(5)

                    # Step 6: Inject localStorage + sessionStorage (after navigation, on correct origin)
                    session_data = session.get("session_storage", {})
                    local_data = session.get("local_storage", {})

                    if local_data:
                        print(f"   Injecting {len(local_data)} localStorage entries...", flush=True)
                        ls_json = json.dumps(local_data)
                        await cdp_cmd(tab_ws, "Runtime.evaluate", {
                            "expression": f"(function(d){{Object.entries(d).forEach(function(e){{localStorage.setItem(e[0],e[1])}})}})({ls_json})",
                            "returnByValue": True,
                        })

                    if session_data:
                        print(f"   Injecting {len(session_data)} sessionStorage entries...", flush=True)
                        ss_json = json.dumps(session_data)
                        await cdp_cmd(tab_ws, "Runtime.evaluate", {
                            "expression": f"(function(d){{Object.entries(d).forEach(function(e){{sessionStorage.setItem(e[0],e[1])}})}})({ss_json})",
                            "returnByValue": True,
                        })

                    # Step 7: Re-navigate with full session state
                    if local_data or session_data:
                        print(f"   Re-navigating with full session state...", flush=True)
                        await cdp_cmd(tab_ws, "Page.navigate", {"url": args.url})
                        await asyncio.sleep(5)

                    # NOTE: Do NOT bounce through accounts.google.com after inject.
                    # That page often shows "Signed out" / accountchooser and can
                    # poison a portable Google session that would otherwise work
                    # when navigating straight to mail.google.com / myaccount.

                    # Get page info
                    title_result = await cdp_cmd(
                        tab_ws, "Runtime.evaluate",
                        {"expression": "document.title", "returnByValue": True},
                    )
                    title = title_result.get("result", {}).get("value", "")

                    url_result = await cdp_cmd(
                        tab_ws, "Runtime.evaluate",
                        {"expression": "window.location.href", "returnByValue": True},
                    )
                    url = url_result.get("result", {}).get("value", "")

                    print(f"\n   📄 Page: {title}")
                    print(f"   🔗 URL: {url}")

                # Brief post-load tips (only when Google-ish session)
                if site_hint == "google" or "google" in str(args.session).lower() or "gmail" in str(args.session).lower():
                    print(f"\n   Tips: keep targets off Chrome; same jar can run on multiple non-Chrome browsers/devices.")

                await tab_ws.close()

            asyncio.run(inject())

        elif args.url:
            # Just navigate to URL — same PUT /json/new approach
            actual_port = browser.port

            async def navigate_only():
                import urllib.request
                import websockets

                msg_id_counter = [0]

                async def cdp_cmd(ws, method, params=None):
                    msg_id_counter[0] += 1
                    current_id = msg_id_counter[0]
                    msg = {"id": current_id, "method": method}
                    if params:
                        msg["params"] = params
                    await ws.send(json.dumps(msg))
                    deadline = time.time() + 30
                    while time.time() < deadline:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=min(5, deadline - time.time()))
                        except asyncio.TimeoutError:
                            continue
                        data = json.loads(raw)
                        if "id" in data and data["id"] == current_id:
                            return data.get("result", {})
                    return {}

                # Create new tab
                def _create_tab():
                    req = urllib.request.Request(
                        f"http://127.0.0.1:{actual_port}/json/new?about:blank",
                        method='PUT'
                    )
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        return json.loads(resp.read().decode())

                try:
                    new_tab = await asyncio.to_thread(_create_tab)
                    tab_ws_url = new_tab.get("webSocketDebuggerUrl")
                except Exception as e:
                    print(f"❌ Failed to create tab: {e}")
                    return

                tab_ws = await websockets.connect(
                    tab_ws_url, max_size=10 * 1024 * 1024,
                    ping_interval=30, ping_timeout=10,
                )

                # Inject stealth
                stealth_script = get_undetectable_stealth_script()
                await cdp_cmd(tab_ws, "Page.enable")
                await cdp_cmd(tab_ws, "Page.addScriptToEvaluateOnNewDocument", {"source": stealth_script})

                # Navigate
                print(f"\n   Navigating to: {args.url}")
                await cdp_cmd(tab_ws, "Page.navigate", {"url": args.url})
                await asyncio.sleep(4)

                title_result = await cdp_cmd(tab_ws, "Runtime.evaluate", {"expression": "document.title", "returnByValue": True})
                title = title_result.get("result", {}).get("value", "")

                url_result = await cdp_cmd(tab_ws, "Runtime.evaluate", {"expression": "window.location.href", "returnByValue": True})
                url = url_result.get("result", {}).get("value", "")

                print(f"\n   📄 Page: {title}")
                print(f"   🔗 URL: {url}")

                await tab_ws.close()

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(navigate_only())
            finally:
                loop.close()

        print(f"\n{'=' * 80}")
        print("Browser is running. You can:")
        print(f"  1. Open http://127.0.0.1:{browser.port} in another browser")
        print(f"  2. Use Chrome DevTools to connect to ws://127.0.0.1:{browser.port}")
        print("  3. Or let it run and control via CDP WebSocket")
        print("\nPress Ctrl+C to close the browser")
        print(f"{'=' * 80}\n")

        # Keep browser running
        try:
            browser.process.wait()
        except KeyboardInterrupt:
            print("\n⏹️  Closing browser...")
            browser.close()

    except RuntimeError as e:
        print(f"\n❌ {e}")
    except Exception as e:
        logger.error(f"Launch failed: {e}", exc_info=True)
        print(f"\n❌ Launch failed: {e}")



def cmd_refresh_browser(args):
    """Refresh session by launching undetectable browser, injecting cookies, navigating, and extracting fresh cookies."""
    from tokenade.core.importer.session_packager import SessionPackager
    from tokenade.core.browser.undetectable import SystemBrowserLauncher

    print("\n" + "=" * 80)
    print("TOKENADE - Cookie-Based Session Refresh")
    print("=" * 80)

    # 1. Load existing session
    session_file = Path(args.session)
    if not session_file.exists():
        print(f"❌ Session file not found: {args.session}")
        return

    packager = SessionPackager()
    try:
        session = packager.load(str(session_file))
    except Exception as e:
        print(f"❌ Failed to load session: {e}")
        return

    cookies = session.get("cookies", [])
    site_name = session.get("site_name", "unknown")
    source_browser = session.get("source_device", {}).get("browser", "unknown")

    if not cookies:
        print("❌ No cookies in session file")
        return

    # 2. Try plugin refresh first (if --plugin specified)
    plugin_name = getattr(args, "plugin", None)
    plugin_args_list = getattr(args, "plugin_arg", [])
    output = getattr(args, "output", None)

    if plugin_name:
        plugin_creds = {}
        for key, value in plugin_args_list:
            plugin_creds[key] = value

        try:
            from tokenade.core.integration.plugin_loader import PluginLoader
            loader = PluginLoader()
            loader.load_all()

            refresher = loader.get_refresher(plugin_name)
            if not refresher:
                print(f"⚠️  Plugin not found: {plugin_name}. Proceeding with browser refresh.")
            elif not refresher.can_refresh(session):
                print(f"⚠️  Plugin '{plugin_name}' cannot refresh this session. Proceeding with browser refresh.")
            else:
                print(f"\n🔌 Using plugin: {plugin_name} v{refresher.version}")

                # Collect credentials from plugin args if not provided
                if hasattr(refresher, "get_credentials_args"):
                    for cred_arg in refresher.get_credentials_args():
                        arg_name = cred_arg["name"].lstrip("-").replace("-", "_")
                        if arg_name not in plugin_creds and cred_arg.get("required"):
                            print(f"❌ Missing required plugin credential: {cred_arg['name']}")
                            print(f"   Use: --plugin-arg {arg_name} <value>")
                            return

                try:
                    session = refresher.refresh(session, plugin_creds)

                    # Save updated session
                    save_path = output or str(session_file)
                    packager.save(session, save_path)
                    print(f"✅ Session refreshed via plugin: {save_path}")

                    # Run post-refresh plugins (webhooks, etc.)
                    _run_post_refresh_plugins(loader, session)

                    return
                except Exception as e:
                    print(f"⚠️  Plugin refresh failed: {e}")
                    print("   Falling back to browser-based refresh...")
        except ImportError:
            print(f"⚠️  Plugin system not available. Proceeding with browser refresh.")
        except Exception as e:
            print(f"⚠️  Plugin error: {e}. Proceeding with browser refresh.")

    # Determine target URL
    target_url = args.url
    if not target_url:
        # Try to infer from cookies
        domains = {c.get("domain", "").lstrip(".") for c in cookies}
        if "google.com" in domains or "gmail.com" in domains:
            target_url = "https://mail.google.com"
        elif "github.com" in domains:
            target_url = "https://github.com"
        elif "twitter.com" in domains or "x.com" in domains:
            target_url = "https://x.com"
        elif "linkedin.com" in domains:
            target_url = "https://www.linkedin.com"
        else:
            # Use the first non-empty domain
            for d in sorted(domains):
                if d and "." in d:
                    target_url = f"https://{d}"
                    break
        if not target_url:
            print("❌ Could not determine target URL. Use --url to specify.")
            return

    print(f"\n📂 Session: {args.session}")
    print(f"   Site: {site_name}")
    print(f"   Cookies: {len(cookies)}")
    print(f"   Source: {source_browser}")
    print(f"\n🌐 Target: {target_url}")
    print(f"   Browser: {args.browser}")

    # 2. Check if browser is already running
    import subprocess as _sp
    _ps_cmd = ["pgrep", "-c", args.browser] if platform.system() != "Windows" else ["tasklist", "/fi", f"imagename eq {args.browser}.exe"]
    try:
        _running = _sp.run(_ps_cmd, capture_output=True, text=True, timeout=3)
        _is_running = False
        if platform.system() != "Windows" and _running.returncode == 0:
            _is_running = int(_running.stdout.strip()) > 0
        elif platform.system() == "Windows" and args.browser.lower() in _running.stdout.lower():
            _is_running = True
        if _is_running:
            print(f"\n   ⚠️  {args.browser} is already running. Close it first or use a different port.")
            return
    except Exception:
        pass

    # 3. Launch undetectable browser (headless for refresh)
    launcher = SystemBrowserLauncher()
    port = args.port
    browser = None

    # Resolve upstream proxy using ProxyManager
    from tokenade.core.proxy.manager import ProxyManager
    proxy_mgr = ProxyManager(
        cli_proxy=getattr(args, "proxy", None),
    )
    proxy = proxy_mgr.get_proxy(session_id=args.session, mode="sticky")
    upstream_proxy = proxy.server_url if proxy else None
    if upstream_proxy:
        print(f"   🔀 Upstream proxy: {upstream_proxy}")

    try:
        print(f"\n🚀 Launching {args.browser} (headless={args.headless})...")
        browser = launcher.launch(
            browser=args.browser,
            visible=not args.headless,
            port=port,
            upstream_proxy=upstream_proxy,
        )
        print(f"   ✅ Browser ready (PID: {browser.pid}, CDP: {browser.cdp_url})")

        # 4. Inject cookies via CDP
        import asyncio
        import websockets

        # Create new tab
        import urllib.request as _urllib_req
        _req = _urllib_req.Request(
            f"http://127.0.0.1:{port}/json/new?about:blank",
            method="PUT",
        )
        _resp = _urllib_req.urlopen(_req, timeout=10)
        _tab_info = json.loads(_resp.read().decode())
        _tab_id = _tab_info.get("id")
        _tab_ws_url = _tab_info.get("webSocketDebuggerUrl")

        if not _tab_ws_url:
            print("❌ Failed to create tab")
            return

        async def refresh():
            msg_id_counter = [0]

            async def cdp_cmd(ws, method, params=None):
                msg_id_counter[0] += 1
                current_id = msg_id_counter[0]
                msg = {"id": current_id, "method": method}
                if params:
                    msg["params"] = params
                await ws.send(json.dumps(msg))
                deadline = time.time() + 30
                while time.time() < deadline:
                    try:
                        raw = await asyncio.wait_for(
                            ws.recv(),
                            timeout=min(5, deadline - time.time()),
                        )
                    except asyncio.TimeoutError:
                        continue
                    data = json.loads(raw)
                    if "id" in data and data["id"] == current_id:
                        if "error" in data:
                            raise RuntimeError(data["error"].get("message", "CDP error"))
                        return data.get("result", {})
                raise RuntimeError(f"CDP timeout: {method}")

            tab_ws = await websockets.connect(
                _tab_ws_url,
                max_size=10 * 1024 * 1024,
                ping_interval=30,
                ping_timeout=10,
            )

            # Inject stealth
            from tokenade.core.browser.cdp_connection import get_undetectable_stealth_script
            stealth_script = get_undetectable_stealth_script()
            await cdp_cmd(tab_ws, "Page.enable")
            await cdp_cmd(tab_ws, "Page.addScriptToEvaluateOnNewDocument", {"source": stealth_script})

            # Inject cookies
            print(f"\n🍪 Injecting {len(cookies)} cookies...")
            cdp_cookies = []
            for cookie in cookies:
                cdp_cookie = {
                    "name": cookie.get("name", ""),
                    "value": cookie.get("value", ""),
                    "domain": cookie.get("domain", ""),
                    "path": cookie.get("path", "/"),
                }
                if cookie.get("secure"):
                    cdp_cookie["secure"] = True
                if cookie.get("httpOnly"):
                    cdp_cookie["httpOnly"] = True
                if cookie.get("sameSite"):
                    same_site = cookie["sameSite"]
                    if same_site in ("Strict", "Lax", "None"):
                        cdp_cookie["sameSite"] = same_site
                expires = cookie.get("expires", 0)
                if expires and int(expires) > 0:
                    exp = int(expires)
                    if exp > 1262304000000:
                        exp = exp // 1000
                    cdp_cookie["expires"] = exp
                if cdp_cookie.get("sameSite") == "None" and not cdp_cookie.get("secure"):
                    cdp_cookie["secure"] = True
                cdp_cookies.append(cdp_cookie)

            await cdp_cmd(tab_ws, "Network.enable")
            await cdp_cmd(tab_ws, "Network.setCookies", {"cookies": cdp_cookies})
            print(f"   ✅ Cookies injected")

            # Navigate to target
            print(f"\n🌐 Navigating to: {target_url}")
            await cdp_cmd(tab_ws, "Page.navigate", {"url": target_url})

            # Wait for page load and "warm up" the session
            wait_time = args.wait
            print(f"   ⏳ Waiting {wait_time}s for session refresh...")
            await asyncio.sleep(wait_time)

            # Get page info
            title_result = await cdp_cmd(
                tab_ws, "Runtime.evaluate",
                {"expression": "document.title", "returnByValue": True},
            )
            title = title_result.get("result", {}).get("value", "")
            print(f"   📄 Page: {title}")

            # Extract fresh cookies
            print(f"\n🔄 Extracting refreshed cookies...")
            from tokenade.cli.session import _extract_via_cdp
            session_state = _extract_via_cdp(port, domain_filter=None)
            fresh_cookies = session_state["cookies"]
            fresh_ls = session_state.get("local_storage", {})
            fresh_ss = session_state.get("session_storage", {})

            await tab_ws.close()
            return fresh_cookies, fresh_ls, fresh_ss

        fresh_cookies, fresh_ls, fresh_ss = asyncio.run(refresh())

        if not fresh_cookies:
            print("\n❌ No cookies extracted after refresh. Session may be expired.")
            return

        print(f"\n   ✅ Extracted {len(fresh_cookies)} fresh cookies")
        if fresh_ls:
            print(f"   ✅ Extracted {len(fresh_ls)} localStorage entries")
        if fresh_ss:
            print(f"   ✅ Extracted {len(fresh_ss)} sessionStorage entries")

        # 5. Compare old vs new
        old_names = {c.get("name") for c in cookies}
        new_names = {c.get("name") for c in fresh_cookies}
        added = new_names - old_names
        removed = old_names - new_names
        kept = old_names & new_names

        print(f"\n📊 Cookie changes:")
        print(f"   Kept: {len(kept)}")
        if added:
            print(f"   Added: {len(added)} ({', '.join(sorted(added)[:5])}{'...' if len(added) > 5 else ''})")
        if removed:
            print(f"   Removed: {len(removed)} ({', '.join(sorted(removed)[:5])}{'...' if len(removed) > 5 else ''})")

        # 6. Update session file
        session["cookies"] = fresh_cookies
        if fresh_ls:
            session["local_storage"] = fresh_ls
        if fresh_ss:
            session["session_storage"] = fresh_ss

        # Update metadata
        if "metadata" not in session:
            session["metadata"] = {}
        session["metadata"]["cookie_count"] = len(fresh_cookies)
        session["metadata"]["local_storage_count"] = len(fresh_ls) if fresh_ls else 0
        session["metadata"]["session_storage_count"] = len(fresh_ss) if fresh_ss else 0

        from datetime import datetime, timezone
        session["metadata"]["last_refreshed"] = datetime.now(timezone.utc).isoformat()

        # Save
        output = args.output or str(session_file)
        packager.save(session, output)
        print(f"\n💾 Session saved: {output}")
        print(f"   Cookies: {len(fresh_cookies)}")
        if fresh_ls:
            print(f"   localStorage: {len(fresh_ls)} entries")
        if fresh_ss:
            print(f"   sessionStorage: {len(fresh_ss)} entries")

        print(f"\n✅ Session refreshed successfully!")

    except Exception as e:
        print(f"\n❌ Refresh failed: {e}")
        logger.error(f"Refresh failed: {e}", exc_info=True)
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass


def cmd_accounts(args):
    """Multi-account orchestration — list, status, refresh multiple sessions."""
    from tokenade.core.importer.session_manager import SessionManager

    sessions_dir = args.sessions_dir or "."
    manager = SessionManager(sessions_dir)

    subcommand = args.accounts_action

    if subcommand == "list":
        _accounts_list(manager, args)
    elif subcommand == "status":
        _accounts_status(manager, args)
    elif subcommand == "refresh":
        _accounts_refresh(manager, args)
    else:
        print(f"❌ Unknown action: {subcommand}")
        print("   Use: list, status, or refresh")


def _accounts_list(manager, args):
    """List all session files with metadata."""
    sessions = manager.list_sessions()

    if not sessions:
        print(f"\n📂 No .tokenade files found in {manager.sessions_dir}")
        return

    # Filter by site if specified
    if args.site:
        sessions = [s for s in sessions if args.site.lower() in s.site_name.lower()]

    # Filter by browser if specified
    if args.browser:
        sessions = [s for s in sessions if s.source_browser == args.browser]

    print(f"\n{'=' * 80}")
    print(f"TOKENADE - Accounts ({len(sessions)} sessions)")
    print(f"{'=' * 80}")

    if not sessions:
        print("   No matching sessions found")
        return

    # Print table
    print(f"\n{'Site':<15} {'Cookies':<10} {'Browser':<12} {'Size':<10} {'Path'}")
    print(f"{'-' * 15} {'-' * 10} {'-' * 12} {'-' * 10} {'-' * 30}")

    total_cookies = 0
    for s in sessions:
        size_kb = s.file_size / 1024
        browser = s.source_browser or "unknown"
        path_display = Path(s.path).name
        if len(path_display) > 35:
            path_display = "..." + path_display[-32:]
        print(f"{s.site_name:<15} {s.cookie_count:<10} {browser:<12} {size_kb:>7.1f}KB  {path_display}")
        total_cookies += s.cookie_count

    print(f"\n   Total: {len(sessions)} sessions, {total_cookies} cookies")

    # Show unique sites
    sites = {s.site_name for s in sessions}
    if len(sites) > 1:
        print(f"   Sites: {', '.join(sorted(sites))}")

    # Show unique browsers
    browsers = {s.source_browser for s in sessions if s.source_browser}
    if len(browsers) > 1:
        print(f"   Browsers: {', '.join(sorted(browsers))}")


def _accounts_status(manager, args):
    """Show health/status of all sessions."""
    sessions = manager.list_sessions()

    if not sessions:
        print(f"\n📂 No .tokenade files found in {manager.sessions_dir}")
        return

    if args.site:
        sessions = [s for s in sessions if args.site.lower() in s.site_name.lower()]

    print(f"\n{'=' * 80}")
    print(f"TOKENADE - Account Status ({len(sessions)} sessions)")
    print(f"{'=' * 80}")

    from tokenade.core.importer.session_packager import SessionPackager
    packager = SessionPackager()

    print(f"\n{'Site':<15} {'Cookies':<10} {'Auth':<12} {'Critical':<10} {'Last Refreshed':<20} {'Status'}")
    print(f"{'-' * 15} {'-' * 10} {'-' * 12} {'-' * 10} {'-' * 20} {'-' * 10}")

    healthy = 0
    expiring = 0
    expired = 0

    for s in sessions:
        try:
            session = packager.load(s.path)
            cookies = session.get("cookies", [])
            auth_status = session.get("auth_status", "unknown")
            critical = session.get("metadata", {}).get("critical_cookie_count", 0)
            last_refreshed = session.get("metadata", {}).get("last_refreshed", "never")

            if last_refreshed and last_refreshed != "never":
                # Parse ISO timestamp
                try:
                    from datetime import datetime, timezone
                    dt = datetime.fromisoformat(last_refreshed.replace("Z", "+00:00"))
                    age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
                    if age_hours < 1:
                        last_display = f"{int(age_hours * 60)}m ago"
                        status = "🟢 FRESH"
                        healthy += 1
                    elif age_hours < 24:
                        last_display = f"{int(age_hours)}h ago"
                        status = "🟡 OK"
                        healthy += 1
                    elif age_hours < 72:
                        last_display = f"{int(age_hours / 24)}d ago"
                        status = "🟠 STALE"
                        expiring += 1
                    else:
                        last_display = f"{int(age_hours / 24)}d ago"
                        status = "🔴 OLD"
                        expired += 1
                except (ValueError, TypeError):
                    last_display = last_refreshed
                    status = "❓ UNKNOWN"
            else:
                last_display = "never"
                status = "⚪ UNUSED"

            print(f"{s.site_name:<15} {len(cookies):<10} {auth_status:<12} {critical:<10} {last_display:<20} {status}")

        except Exception as e:
            print(f"{s.site_name:<15} {'?':<10} {'?':<12} {'?':<10} {'?':<20} ❌ ERROR: {e}")

    print(f"\n   🟢 Fresh: {healthy}  🟠 Stale: {expiring}  🔴 Old: {expired}")
    print(f"   💡 Run 'tokenade accounts refresh' to refresh stale sessions")


def _accounts_refresh(manager, args):
    """Refresh sessions — uses refresh-browser for each, with optional plugin support."""
    sessions = manager.list_sessions()

    if not sessions:
        print(f"\n📂 No .tokenade files found in {manager.sessions_dir}")
        return

    if args.site:
        sessions = [s for s in sessions if args.site.lower() in s.site_name.lower()]

    if args.browser:
        sessions = [s for s in sessions if s.source_browser == args.browser]

    if not sessions:
        print("   No matching sessions to refresh")
        return

    # If specific files given, filter to those
    if args.files:
        session_paths = {str(Path(f).resolve()) for f in args.files}
        sessions = [s for s in sessions if str(Path(s.path).resolve()) in session_paths]

    print(f"\n{'=' * 80}")
    print(f"TOKENADE - Refresh {len(sessions)} Accounts")
    print(f"{'=' * 80}")

    for s in sessions:
        print(f"   • {s.site_name} ({s.cookie_count} cookies) — {Path(s.path).name}")

    if not args.yes:
        response = input(f"\n🔄 Refresh all {len(sessions)} sessions? [y/N]: ").strip().lower()
        if response != "y":
            print("Cancelled")
            return

    # Refresh each session
    browser = args.browser or "chrome"
    headless = not args.visible
    wait = args.wait
    port = args.port

    # Load plugin if specified
    plugin_name = getattr(args, "plugin", None)
    plugin_args_list = getattr(args, "plugin_arg", [])
    plugin_creds = {}
    for key, value in plugin_args_list:
        plugin_creds[key] = value

    plugin_loader = None
    refresher = None
    if plugin_name:
        try:
            from tokenade.core.integration.plugin_loader import PluginLoader
            plugin_loader = PluginLoader()
            plugin_loader.load_all()
            refresher = plugin_loader.get_refresher(plugin_name)
            if refresher:
                print(f"\n🔌 Using plugin: {plugin_name} v{refresher.version}")
            else:
                print(f"\n⚠️  Plugin not found: {plugin_name}. Using browser refresh only.")
        except Exception as e:
            print(f"\n⚠️  Plugin error: {e}. Using browser refresh only.")

    succeeded = 0
    failed = 0
    skipped = 0

    for i, s in enumerate(sessions):
        print(f"\n{'─' * 60}")
        print(f"[{i + 1}/{len(sessions)}] Refreshing: {s.site_name} ({Path(s.path).name})")

        # Check if browser is already running
        import subprocess as _sp
        _ps_cmd = ["pgrep", "-c", browser] if platform.system() != "Windows" else ["tasklist", "/fi", f"imagename eq {browser}.exe"]
        try:
            _running = _sp.run(_ps_cmd, capture_output=True, text=True, timeout=3)
            _is_running = False
            if platform.system() != "Windows" and _running.returncode == 0:
                _is_running = int(_running.stdout.strip()) > 0
            elif platform.system() == "Windows" and browser.lower() in _running.stdout.lower():
                _is_running = True
            if _is_running:
                print(f"   ⚠️  {browser} is running. Close it first or use --port for next session.")
                skipped += 1
                continue
        except Exception:
            pass

        try:
            # Try plugin refresh first
            if refresher:
                try:
                    session = packager.load(s.path)
                    if refresher.can_refresh(session):
                        print(f"   🔌 Trying plugin {plugin_name}...")
                        session = refresher.refresh(session, plugin_creds)
                        __import__("tokenade.core.importer.session_packager", fromlist=["SessionPackager"]).SessionPackager().save(session, s.path)
                        print(f"   ✅ Plugin refresh: {s.site_name}")
                        succeeded += 1
                        _run_post_refresh_plugins(plugin_loader, session)
                        continue
                    else:
                        print(f"   ⚠️  Plugin can't handle this session, falling back to browser")
                except Exception as e:
                    print(f"   ⚠️  Plugin refresh failed: {e}, falling back to browser")

            # Browser-based refresh (existing logic)
            from tokenade.core.browser.undetectable import SystemBrowserLauncher

            session = packager = __import__("tokenade.core.importer.session_packager", fromlist=["SessionPackager"]).SessionPackager().load(s.path)
            cookies = session.get("cookies", [])

            if not cookies:
                print(f"   ⚠️  No cookies, skipping")
                skipped += 1
                continue

            # Auto-detect URL
            target_url = _detect_url_from_cookies(cookies)
            if not target_url:
                print(f"   ⚠️  Could not detect URL, skipping")
                skipped += 1
                continue

            # Use unique port per session to avoid conflicts
            session_port = port + i

            launcher = SystemBrowserLauncher()
            browser_proc = launcher.launch(
                browser=browser,
                visible=not headless,
                port=session_port,
                upstream_proxy=_resolve_upstream_proxy(args),
            )

            # Inject → navigate → extract → save
            fresh_cookies, fresh_ls, fresh_ss = _refresh_session_cookies(
                browser_proc, session_port, cookies, target_url, wait
            )

            browser_proc.close()

            if fresh_cookies:
                session["cookies"] = fresh_cookies
                if fresh_ls:
                    session["local_storage"] = fresh_ls
                if fresh_ss:
                    session["session_storage"] = fresh_ss

                if "metadata" not in session:
                    session["metadata"] = {}
                session["metadata"]["cookie_count"] = len(fresh_cookies)
                session["metadata"]["last_refreshed"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()

                __import__("tokenade.core.importer.session_packager", fromlist=["SessionPackager"]).SessionPackager().save(session, s.path)
                print(f"   ✅ Refreshed: {len(fresh_cookies)} cookies")
                succeeded += 1
                if plugin_loader:
                    _run_post_refresh_plugins(plugin_loader, session)
            else:
                print(f"   ❌ No cookies extracted")
                failed += 1

        except Exception as e:
            print(f"   ❌ Failed: {e}")
            logger.error(f"Refresh failed for {s.path}: {e}", exc_info=True)
            failed += 1

    # Summary
    print(f"\n{'=' * 80}")
    print(f"REFRESH COMPLETE")
    print(f"{'=' * 80}")
    print(f"   ✅ Succeeded: {succeeded}")
    print(f"   ❌ Failed: {failed}")
    print(f"   ⏭️  Skipped: {skipped}")
    print(f"   Total: {len(sessions)}")


def _detect_url_from_cookies(cookies):
    """Auto-detect target URL from cookie domains."""
    domains = {c.get("domain", "").lstrip(".") for c in cookies}

    if "google.com" in domains or "gmail.com" in domains:
        return "https://mail.google.com"
    elif "github.com" in domains:
        return "https://github.com"
    elif "twitter.com" in domains or "x.com" in domains:
        return "https://x.com"
    elif "linkedin.com" in domains:
        return "https://www.linkedin.com"
    elif "reddit.com" in domains:
        return "https://www.reddit.com"
    elif "facebook.com" in domains:
        return "https://www.facebook.com"
    elif "instagram.com" in domains:
        return "https://www.instagram.com"
    elif "slack.com" in domains:
        return "https://slack.com"

    # Fallback: use first non-empty domain
    for d in sorted(domains):
        if d and "." in d:
            return f"https://{d}"
    return None


def _refresh_session_cookies(browser_proc, port, cookies, target_url, wait_time):
    """Refresh cookies by injecting into browser, navigating, and extracting."""
    import asyncio
    import json
    import websockets
    import urllib.request as _urllib_req

    # Create new tab
    _req = _urllib_req.Request(
        f"http://127.0.0.1:{port}/json/new?about:blank",
        method="PUT",
    )
    _resp = _urllib_req.urlopen(_req, timeout=10)
    _tab_info = json.loads(_resp.read().decode())
    _tab_ws_url = _tab_info.get("webSocketDebuggerUrl")

    if not _tab_ws_url:
        raise RuntimeError("Failed to create tab")

    async def _do_refresh():
        msg_id_counter = [0]

        async def cdp_cmd(ws, method, params=None):
            msg_id_counter[0] += 1
            current_id = msg_id_counter[0]
            msg = {"id": current_id, "method": method}
            if params:
                msg["params"] = params
            await ws.send(json.dumps(msg))
            deadline = time.time() + 30
            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(
                        ws.recv(),
                        timeout=min(5, deadline - time.time()),
                    )
                except asyncio.TimeoutError:
                    continue
                data = json.loads(raw)
                if "id" in data and data["id"] == current_id:
                    if "error" in data:
                        raise RuntimeError(data["error"].get("message", "CDP error"))
                    return data.get("result", {})
            raise RuntimeError(f"CDP timeout: {method}")

        tab_ws = await websockets.connect(
            _tab_ws_url,
            max_size=10 * 1024 * 1024,
            ping_interval=30,
            ping_timeout=10,
        )

        # Inject stealth
        from tokenade.core.browser.cdp_connection import get_undetectable_stealth_script
        stealth_script = get_undetectable_stealth_script()
        await cdp_cmd(tab_ws, "Page.enable")
        await cdp_cmd(tab_ws, "Page.addScriptToEvaluateOnNewDocument", {"source": stealth_script})

        # Inject cookies
        cdp_cookies = []
        for cookie in cookies:
            cdp_cookie = {
                "name": cookie.get("name", ""),
                "value": cookie.get("value", ""),
                "domain": cookie.get("domain", ""),
                "path": cookie.get("path", "/"),
            }
            if cookie.get("secure"):
                cdp_cookie["secure"] = True
            if cookie.get("httpOnly"):
                cdp_cookie["httpOnly"] = True
            if cookie.get("sameSite"):
                ss = cookie["sameSite"]
                if ss in ("Strict", "Lax", "None"):
                    cdp_cookie["sameSite"] = ss
            expires = cookie.get("expires", 0)
            if expires and int(expires) > 0:
                exp = int(expires)
                if exp > 1262304000000:
                    exp = exp // 1000
                cdp_cookie["expires"] = exp
            if cdp_cookie.get("sameSite") == "None" and not cdp_cookie.get("secure"):
                cdp_cookie["secure"] = True
            cdp_cookies.append(cdp_cookie)

        await cdp_cmd(tab_ws, "Network.enable")
        await cdp_cmd(tab_ws, "Network.setCookies", {"cookies": cdp_cookies})

        # Navigate
        await cdp_cmd(tab_ws, "Page.navigate", {"url": target_url})
        await asyncio.sleep(wait_time)

        # Extract fresh cookies
        from tokenade.cli.session import _extract_via_cdp
        session_state = _extract_via_cdp(port, domain_filter=None)

        await tab_ws.close()
        return session_state["cookies"], session_state.get("local_storage", {}), session_state.get("session_storage", {})

    return asyncio.run(_do_refresh())


def cmd_patch_chrome(args):
    """Patch Chrome/Chromium binary to remove cdc_ artifacts."""
    from tokenade.core.browser.patcher import ChromePatcher

    patcher = ChromePatcher()
    browser = getattr(args, "browser", "chrome")
    binary_path = getattr(args, "binary", None)
    output_path = getattr(args, "output", None)
    action = getattr(args, "patch_action", "scan")

    # Find binary if not specified
    if not binary_path:
        binary_path = patcher.find_browser_binary(browser)
        if not binary_path:
            print(f"❌ Could not find {browser} binary. Use --binary to specify path.")
            return
        print(f"🔍 Found {browser}: {binary_path}")

    if action == "scan":
        print(f"\n🔍 Scanning {binary_path} for cdc_ artifacts...")
        result = patcher.scan(binary_path)
        if result.get("error"):
            print(f"❌ {result['error']}")
            return
        matches = result.get("matches", [])
        if not matches:
            print("✅ Binary is clean — no cdc_ artifacts found")
        else:
            print(f"⚠️  Found {len(matches)} cdc_ artifact(s):")
            for i, m in enumerate(matches, 1):
                raw_preview = m["raw"][:60]
                if len(m["raw"]) > 60:
                    raw_preview += b"..."
                print(f"   {i}. Offset {m['offset']} ({m['length']} bytes): {raw_preview}")

    elif action == "patch":
        print(f"\n🔧 Patching {binary_path}...")
        result = patcher.patch(binary_path, output_path=output_path)
        if result.success:
            print(f"✅ {result.summary}")
            if result.backup_path:
                print(f"📦 Backup: {result.backup_path}")
        else:
            print(f"❌ {result.summary}")

    elif action == "restore":
        print(f"\n♻️  Restoring {binary_path} from backup...")
        if patcher.restore(binary_path):
            print(f"✅ Restored {binary_path}")
        else:
            print(f"❌ No backup found for {binary_path}")

    elif action == "verify":
        print(f"\n🔎 Verifying {binary_path}...")
        result = patcher.verify(binary_path)
        if result["patched"]:
            print("✅ Binary is patched (no cdc_ artifacts)")
        else:
            print(f"⚠️  Binary is NOT patched ({result['remaining_artifacts']} artifact(s) remain)")
        if result["has_backup"]:
            print(f"📦 Backup available: {binary_path}.backup")
        if result["has_patched_variant"]:
            print(f"🔧 Patched variant: {binary_path}.patched")


# ── Daemon Commands ─────────────────────────────────────────────


