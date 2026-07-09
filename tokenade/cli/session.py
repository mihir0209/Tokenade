"""Session-related CLI commands."""
import json
import logging
import os
from pathlib import Path

from tokenade.core.browser.manager import BrowserFactory, BrowserConfig
from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery
from tokenade.core.importer.cookie_extractor import CookieExtractor
from tokenade.core.importer.local_storage_extractor import LocalStorageExtractor
from tokenade.core.importer.session_packager import SessionPackager
from tokenade.core.importer.session_loader import SessionLoader
from tokenade.core.injector.profile_manager import inject_session_to_profile
from tokenade.handlers.resolve import resolve_legacy_handler_class

logger = logging.getLogger("tokenade")


async def _eval_with_session(ws, msg_id, session_id, expression):
    """Evaluate JS in a tab via CDP session (async)."""
    import asyncio
    import time as _time

    msg_id[0] += 1
    mid = msg_id[0]
    m = {
        "id": mid,
        "method": "Runtime.evaluate",
        "params": {"expression": expression, "returnByValue": True},
        "sessionId": session_id,
    }
    await ws.send(json.dumps(m))

    deadline = _time.time() + 10
    while _time.time() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=min(2, deadline - _time.time()))
        except asyncio.TimeoutError:
            continue
        d = json.loads(raw)
        if d.get("id") == mid:
            result = d.get("result", {}).get("result", {})
            return result.get("value")
    return None


def _extract_via_cdp(port: int, domain_filter: str = None) -> dict:
    """Extract cookies + localStorage + sessionStorage from running browser via CDP."""
    import urllib.request as _urllib_req

    try:
        resp = _urllib_req.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=5)
        version = json.loads(resp.read().decode())
        browser_ws = version.get("webSocketDebuggerUrl")
    except Exception as e:
        print(f"❌ Cannot connect to CDP on port {port}: {e}")
        return {"cookies": [], "local_storage": {}, "session_storage": {}}

    import asyncio
    import websockets

    async def _get_session_state():
        ws = await websockets.connect(
            browser_ws, max_size=50 * 1024 * 1024,
            ping_interval=30, ping_timeout=10,
        )
        msg_id = [0]

        async def cmd(method, params=None):
            msg_id[0] += 1
            mid = msg_id[0]
            m = {"id": mid, "method": method}
            if params:
                m["params"] = params
            await ws.send(json.dumps(m))
            import time as _time
            deadline = _time.time() + 15
            while _time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=min(3, deadline - _time.time()))
                except asyncio.TimeoutError:
                    continue
                d = json.loads(raw)
                if d.get("id") == mid:
                    return d.get("result", {})
            return {}

        # 1. Get all cookies
        result = await cmd("Storage.getCookies")
        cdp_cookies = result.get("cookies", [])

        # 2. Find tabs on target domains for localStorage/sessionStorage
        local_storage = {}
        session_storage = {}

        targets_result = await cmd("Target.getTargets")
        targets = targets_result.get("targetInfos", [])

        domains_needed = []
        if domain_filter:
            domains_needed = [d.strip().lstrip(".") for d in domain_filter.split(",") if d.strip()]

        # Collect localStorage/sessionStorage per origin
        import time as _time

        for domain in domains_needed:
            # Find existing tab for this domain, or create one
            target_page = None
            for t in targets:
                if t.get("type") == "page" and t.get("url") and domain in t["url"]:
                    target_page = t
                    break

            if not target_page:
                proto = "https" if domain not in ("localhost", "127.0.0.1") else "http"
                create_result = await cmd("Target.createTarget", {
                    "url": f"{proto}://{domain}"
                })
                target_id = create_result.get("targetId")
                if not target_id:
                    continue
                _time.sleep(3)  # Wait for page load
            else:
                target_id = target_page.get("targetId")

            # Attach to tab
            attach_result = await cmd("Target.attachToTarget", {
                "targetId": target_id,
                "flatten": True,
            })
            session_id = attach_result.get("sessionId")
            if not session_id:
                continue

            # Navigate to the domain to ensure correct origin
            proto = "https" if domain not in ("localhost", "127.0.0.1") else "http"
            nav_id = msg_id[0] + 5000
            msg_id[0] += 1
            await ws.send(json.dumps({
                "id": nav_id,
                "method": "Page.navigate",
                "params": {"url": f"{proto}://{domain}"},
                "sessionId": session_id,
            }))
            _time.sleep(3)  # Wait for navigation

            # Collect localStorage for this origin
            ls_result = await _eval_with_session(
                ws, msg_id, session_id,
                "JSON.stringify(Object.entries(localStorage))"
            )
            if ls_result:
                try:
                    entries = json.loads(ls_result)
                    for key, val in entries:
                        local_storage[key] = val
                    print(f"   📦 {domain}: {len(entries)} localStorage entries")
                except (json.JSONDecodeError, TypeError):
                    print(f"   ⚠️  {domain}: localStorage parse failed")

            # Collect sessionStorage for this origin
            ss_result = await _eval_with_session(
                ws, msg_id, session_id,
                "JSON.stringify(Object.entries(sessionStorage))"
            )
            if ss_result:
                try:
                    entries = json.loads(ss_result)
                    for key, val in entries:
                        session_storage[key] = val
                    print(f"   📦 {domain}: {len(entries)} sessionStorage entries")
                except (json.JSONDecodeError, TypeError):
                    print(f"   ⚠️  {domain}: sessionStorage parse failed")

            # Clean up tab we created (not if it was pre-existing)
            if not target_page:
                await cmd("Target.closeTarget", {"targetId": target_id})

        await ws.close()
        return {
            "cookies": cdp_cookies,
            "local_storage": local_storage,
            "session_storage": session_storage,
        }

    try:
        session_state = asyncio.run(_get_session_state())
    except Exception as e:
        print(f"❌ CDP extraction failed: {e}")
        return {"cookies": [], "local_storage": {}, "session_storage": {}}

    # Convert CDP format to tokenade format
    cookies = []
    for c in session_state["cookies"]:
        cookie = {
            "name": c.get("name", ""),
            "value": c.get("value", ""),
            "domain": c.get("domain", ""),
            "path": c.get("path", "/"),
            "secure": c.get("secure", False),
            "httpOnly": c.get("httpOnly", False),
        }
        same_site = c.get("sameSite", "None")
        if same_site in ("Strict", "Lax", "None"):
            cookie["sameSite"] = same_site
        expires = c.get("expires", -1)
        if expires and expires > 0:
            cookie["expires"] = int(expires)
        cookies.append(cookie)

    # Apply domain filter
    if domain_filter:
        domains = [d.strip() for d in domain_filter.split(",") if d.strip()]
        filtered = []
        for c in cookies:
            domain = c.get("domain", "")
            for d in domains:
                if d.startswith("."):
                    if domain.endswith(d) or domain == d[1:]:
                        filtered.append(c)
                        break
                else:
                    if domain == d or domain.endswith("." + d):
                        filtered.append(c)
                        break
        cookies = filtered

    return {
        "cookies": cookies,
        "local_storage": session_state["local_storage"],
        "session_storage": session_state["session_storage"],
    }


def cmd_extract(args):
    """Extract tokens from saved browser sessions."""
    from tokenade.core.security.credentials import CredentialManager

    print("\n" + "=" * 80)
    print("TOKENADE - Token Extraction")
    print("=" * 80)

    manager = CredentialManager()
    try:
        accounts = manager.load_accounts()
    except ValueError:
        print("❌ Accounts file is encrypted. Run with --master-password to decrypt.")
        return

    if not accounts:
        print("❌ No accounts configured. Run 'tokenade setup' first.")
        return

    output_dir = Path("sessions")
    output_dir.mkdir(exist_ok=True)

    results = []

    for account in accounts:
        account_num = account.number
        email = account.email
        profile_dir = account.profile_dir or f"browser_data/{account_num}"

        print(f"\n📋 Account #{account_num}: {email}")

        if not Path(profile_dir).exists():
            print(f"   ❌ Profile not found: {profile_dir}")
            continue

        config = BrowserConfig(
            headless=not args.visible,
            user_data_dir=profile_dir,
        )

        browser = BrowserFactory.create(**config.__dict__)

        try:
            browser.launch()

            site = getattr(account, "site", None)
            if not isinstance(site, str) or not site:
                site = "google"
            handler_cls = resolve_legacy_handler_class(site)
            handler = handler_cls(browser)
            hname = getattr(handler_cls, "__name__", handler_cls.__class__.__name__)
            print(f"   Handler: {hname} (legacy; prefer plugins)")
            session = handler.get_session()

            session_path = output_dir / f"{site}_{account_num}_{email.replace('@', '_at_')}.json"
            handler.save_session(str(session_path))

            token = session.get_token(handler.extract_tokens()[0].token_type if session.tokens else None)
            if token:
                token_path = output_dir / f"token_{account_num}.json"
                with open(token_path, "w") as f:
                    json.dump(token.to_dict(), f, indent=2)
                print(f"   ✅ Token saved: {token_path}")

            results.append({
                "account": account_num,
                "email": email,
                "status": session.auth_status.value,
                "tokens": len(session.tokens),
                "cookies": len(session.cookies),
            })

        except Exception as e:
            logger.error(f"Extraction failed for account {account_num}: {e}", exc_info=True)
            results.append({
                "account": account_num,
                "email": email,
                "status": "error",
                "error": "Extraction failed — check browser is running and profile is accessible",
            })
        finally:
            browser.close()

    print("\n" + "=" * 80)
    print("EXTRACTION COMPLETE")
    print("=" * 80)

    successful = sum(1 for r in results if r.get("status") == "logged_in")
    print(f"\n✅ Successful: {successful}/{len(accounts)}")
    print(f"📁 Sessions saved to: {output_dir}/")
    if successful == 0 and accounts:
        raise SystemExit(1)


def cmd_export(args):
    """Export session from existing browser to .tokenade file."""
    print("\n" + "=" * 80)
    print("TOKENADE - Session Export")
    print("=" * 80)

    if args.list_profiles:
        print("\n🔍 Discovering browser profiles...")
        discovery = BrowserProfileDiscovery()
        profiles = discovery.discover_all()

        if not profiles:
            print("   ❌ No browser profiles found")
            return

        print(f"\n📁 Found {len(profiles)} profile(s):\n")
        for browser_name, browser_profiles in profiles.items():
            for p in browser_profiles:
                print(f"   Browser: {p.browser}")
                print(f"   Profile: {p.name}")
                print(f"   Path: {p.path}")
                print(f"   Last Used: {p.last_used or 'unknown'}")
                print()
        return

    # List available site handler plugins
    if getattr(args, 'list_handlers', False):
        from tokenade.core.importer.plugin_export import PluginExporter
        exporter = PluginExporter()
        handlers = exporter.list_handlers()
        if not handlers:
            print("   No site handler plugins installed.")
            print("   Install one: tokenade plugin install google-handler")
        else:
            print(f"\n🔌 Available site handlers ({len(handlers)}):\n")
            for h in handlers:
                print(f"   {h['name']} v{h['version']} — {h['description']}")
        return

    browser_path = args.browser_path
    browser_name = args.browser_name or "unknown"

    # Apply config defaults
    from tokenade.core.config import load_config
    config = load_config()
    if not browser_name or browser_name == "unknown":
        browser_name = config.get("default_browser") or browser_name
    if not args.profile:
        args.profile = config.get("default_profile")

    if not browser_path and browser_name:
        discovery = BrowserProfileDiscovery()
        profiles = discovery.discover_all()
        all_profiles = []
        for browser_profiles in profiles.values():
            all_profiles.extend(browser_profiles)
        matching = [p for p in all_profiles if p.browser == browser_name]
        if args.profile:
            matching = [p for p in matching if p.name == args.profile]
        if matching:
            browser_path = str(matching[0].path)
            print(f"📁 Using profile: {matching[0].name}")
        else:
            print(f"❌ No profile found for '{browser_name}'")
            print("   Run 'tokenade export --list-profiles' to see available profiles")
            if args.profile:
                print(f"   Profile '{args.profile}' not found — check spelling and try again")
            return

    if not browser_path and not getattr(args, 'cdp_port', None):
        print("❌ No browser path specified.")
        print("   Use --browser-name (e.g., --browser-name firefox) or --browser-path /path/to/profile")
        print("   Run 'tokenade export --list-profiles' to discover available profiles")
        return

    # CDP-based extraction (auto-launches browser with CDP if needed)
    cdp_port = getattr(args, 'cdp_port', None)
    if cdp_port:
        # Auto-launch browser with CDP if not already running
        launched_browser = None
        import urllib.request as _urllib_req
        try:
            _urllib_req.urlopen(f"http://127.0.0.1:{cdp_port}/json/version", timeout=2)
            print(f"\n🔌 Connected to existing browser on port {cdp_port}")
        except Exception:
            # Browser not running — launch it with real profile
            import subprocess
            import platform

            # Check if browser is already running (profile locked)
            _ps_cmd = ["pgrep", "-c", browser_name] if platform.system() != "Windows" else ["tasklist", "/fi", f"imagename eq {browser_name}.exe"]
            try:
                _running = subprocess.run(_ps_cmd, capture_output=True, text=True, timeout=3)
                if platform.system() != "Windows" and _running.returncode == 0 and int(_running.stdout.strip()) > 0:
                    print(f"   ⚠️  {browser_name} is already running. Profile is locked.")
                    print(f"   Close all {browser_name} windows first, then retry.")
                    print(f"   Or start {browser_name} with: {browser_name} --remote-debugging-port={cdp_port}")
                    return
                elif platform.system() == "Windows" and browser_name.lower() in _running.stdout.lower():
                    print(f"   ⚠️  {browser_name} is already running. Profile is locked.")
                    print(f"   Close all {browser_name} windows first, then retry.")
                    print(f"   Or start {browser_name} with: {browser_name} --remote-debugging-port={cdp_port}")
                    return
            except Exception:
                pass  # If we can't check, just try to launch

            print(f"\n🚀 Launching {browser_name} with CDP on port {cdp_port}...")
            from tokenade.core.browser.undetectable import SystemBrowserLauncher
            launcher = SystemBrowserLauncher()
            try:
                # Find real profile for this browser
                real_profile = launcher._get_default_profile_dir(browser_name)
                launched_browser = launcher.launch(
                    browser=browser_name,
                    visible=True,
                    port=cdp_port,
                    profile_dir=real_profile,
                )
                print(f"   ✅ Browser launched (PID: {launched_browser.pid})")
                import time as _time
                _time.sleep(3)  # Wait for CDP to be ready
            except RuntimeError as e:
                print(f"❌ Failed to launch browser: {e}")
                return

        session_state = _extract_via_cdp(cdp_port, domain_filter=getattr(args, 'domains', None))
        cookies = session_state["cookies"]
        local_storage = session_state.get("local_storage", {})
        session_storage = session_state.get("session_storage", {})

        if launched_browser:
            try:
                launched_browser.close()
            except Exception:
                pass

        if not cookies:
            print("❌ No cookies extracted via CDP")
            return
        print(f"   ✅ Extracted {len(cookies)} cookies via CDP")
        if local_storage:
            print(f"   ✅ Extracted {len(local_storage)} localStorage entries")
        if session_storage:
            print(f"   ✅ Extracted {len(session_storage)} sessionStorage entries")
    else:
        print(f"\n🍪 Extracting cookies from: {browser_path}")
        extractor = CookieExtractor(browser_path, browser=browser_name)

    # Parse domain filter early (needed for plugin discovery)
    domain_filter = None
    if args.domains:
        cleaned = []
        for d in args.domains.split(","):
            d = d.strip()
            if not d:
                continue
            if "://" in d:
                d = d.split("://", 1)[1]
            d = d.split("/", 1)[0]
            d = d.split(":", 1)[0]
            if d:
                cleaned.append(d)
        domain_filter = cleaned if cleaned else None

    # Plugin-first: try site handler plugin if --plugin specified
    plugin_name = getattr(args, 'plugin', None)
    use_plugin = not getattr(args, 'no_plugin', False)

    if plugin_name or use_plugin:
        from tokenade.core.importer.plugin_export import PluginExporter
        exporter = PluginExporter()

        if plugin_name:
            handler = exporter._handlers.get(plugin_name)
            if handler:
                print(f"   🔌 Using plugin: {plugin_name}")
            else:
                print(f"   ⚠️  Plugin not found: {plugin_name}")
        elif domain_filter:
            handler = exporter.find_handler(domain_filter)
            if handler:
                print(f"   🔌 Auto-discovered handler: {handler.name}")
            else:
                print(f"   ℹ️  No handler found for domains, using default extraction")

    site_config = None
    if args.site_config:
        with open(args.site_config) as f:
            site_config = json.load(f)

    def _progress(current, total, stage):
        if stage == "copying_database":
            print("   📋 Copying cookie database...")
        elif stage == "extracting_cookies":
            if total > 0:
                pct = int((current / total) * 100)
                print(f"\r   ⏳ Extracting cookies... {current}/{total} ({pct}%)", end="", flush=True)
        elif stage == "complete":
            print("\r   ✅ Cookie extraction complete                    ", flush=True)

    try:
        if cdp_port:
            pass  # cookies already obtained via CDP above
        elif args.file_path:
            cookies = extractor.extract_from_file(args.file_path, args.format or "netscape")
        else:
            cookies = extractor.extract(site_filter=None, progress_callback=_progress)
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)
        print("❌ Extraction failed — check browser profile is accessible")
        raise SystemExit(1) from e

    print(f"   📊 Total cookies: {len(cookies)}")

    if domain_filter and not args.file_path:
        filtered = []
        for c in cookies:
            domain = c.get("domain", "")
            for d in domain_filter:
                if d.startswith("."):
                    if domain.endswith(d) or domain == d[1:]:
                        filtered.append(c)
                        break
                else:
                    if domain == d or domain.endswith("." + d):
                        filtered.append(c)
                        break
        cookies = filtered
        print(f"   🎯 Filtered to {len(cookies)} cookies for domains: {', '.join(domain_filter)}")

    elif site_config and not args.file_path:
        configs = site_config if isinstance(site_config, list) else [site_config]
        domains = []
        for cfg in configs:
            domains.extend(cfg.get("domains", []))
        if domains:
            filtered = []
            for c in cookies:
                domain = c.get("domain", "")
                for d in domains:
                    if d.startswith("."):
                        if domain.endswith(d) or domain == d[1:]:
                            filtered.append(c)
                            break
                    else:
                        if domain == d or domain.endswith("." + d):
                            filtered.append(c)
                            break
            cookies = filtered
            print(f"   🎯 Filtered to {len(cookies)} cookies for domains: {', '.join(domains)}")

    local_storage = {}
    session_storage = {}
    do_extract_storage = args.extract_local_storage or getattr(args, 'full', False)

    if do_extract_storage:
        print(f"\n💾 Extracting localStorage from: {browser_path}")
        ls_extractor = LocalStorageExtractor(browser_path, browser=browser_name)

        try:
            if args.local_storage_origin:
                local_storage = ls_extractor.extract(origin_filter=args.local_storage_origin)
                print(f"   📊 localStorage entries for {args.local_storage_origin}: {len(local_storage)}")
            else:
                origins = ls_extractor.list_origins()
                if origins:
                    print(f"   📋 Found {len(origins)} origin(s) with localStorage")
                    # Extract all origins for --full mode
                    for origin in origins:
                        try:
                            origin_data = ls_extractor.extract(origin_filter=origin)
                            local_storage.update(origin_data)
                        except Exception:
                            pass
                    print(f"   📊 Extracted {len(local_storage)} localStorage entries total")
                else:
                    print("   ⚠️  No localStorage data found")
        except Exception as e:
            logger.warning(f"localStorage extraction failed: {e}", exc_info=True)
            print("   ⚠️  localStorage extraction skipped — browser may be running")
    else:
        try:
            ls_extractor = LocalStorageExtractor(browser_path, browser=browser_name)
            origins = ls_extractor.list_origins()
            if origins and cookies:
                cookie_domains = {c.get("domain", "").lstrip(".") for c in cookies}
                matching_origins = [
                    o for o in origins
                    if any(d in o for d in cookie_domains)
                ]
                if matching_origins:
                    print(f"\n💾 Found localStorage for {len(matching_origins)} cookie domain(s): {', '.join(matching_origins)}")
                    print("   💡 Re-run with --extract-local-storage to include it")
        except Exception:
            pass

    if not cookies and not local_storage and not session_storage:
        print("❌ No cookies or localStorage to export")
        return

    packager = SessionPackager()
    package = packager.package(
        cookies=cookies,
        browser=browser_name,
        profile=args.profile or "unknown",
        local_storage=local_storage if local_storage else None,
        session_storage=session_storage if session_storage else None,
    )

    site_name = package.get("site_name", "session")
    output = args.output or f"{site_name}_session"

    # Handle --encrypt-password
    encrypt_password = getattr(args, 'encrypt_password', None)
    if encrypt_password:
        saved_path = packager.save(package, output, encrypt=True)
        # Encrypt with password
        from tokenade.core.crypto.encryptor import SessionEncryptor
        encryptor = SessionEncryptor()
        encryptor.encrypt_file(saved_path, saved_path + ".enc", encrypt_password)
        os.rename(saved_path + ".enc", saved_path)
        print(f"\n🔒 Encrypted and exported: {saved_path}")
    else:
        saved_path = packager.save(package, output)
        print(f"\n💾 Exported: {saved_path}")

    print(f"   Site: {package['site_name']}")
    print(f"   Auth: {package['auth_status']}")
    print(f"   Cookies: {package['metadata']['cookie_count']}")
    print(f"   Critical: {package['metadata']['critical_cookie_count']}")
    if package['metadata'].get('local_storage_count', 0) > 0:
        print(f"   localStorage: {package['metadata']['local_storage_count']} entries")
    if package['metadata'].get('session_storage_count', 0) > 0:
        print(f"   sessionStorage: {package['metadata']['session_storage_count']} entries")

    print("\n" + packager.get_summary(package))


def cmd_load(args):
    """Load session file into browser."""
    print("\n" + "=" * 80)
    print("TOKENADE - Session Load")
    print("=" * 80)

    file_path = args.file
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return

    print(f"\n📂 Loading: {file_path}")

    site_config = None
    if args.site_config:
        with open(args.site_config) as f:
            site_config = json.load(f)
        if isinstance(site_config, list):
            site_config = site_config[0] if site_config else None

    loader = SessionLoader()

    try:
        result = loader.load(
            file_path=file_path,
            target_fp_name=args.fingerprint,
            stealth_level=args.stealth_level,
            validate=args.validate,
            visible=args.visible,
            profile_dir=args.profile_dir,
            inject_local_storage=not args.no_local_storage,
            site_config=site_config,
        )

        if result["success"]:
            print("\n✅ Session loaded successfully")
            print(f"   Site: {result.get('site_name', 'unknown')}")
            print(f"   Cookies: {result['cookies_injected']}/{result['cookies_total']}")

            if result.get("local_storage_total", 0) > 0:
                print(f"   localStorage: {result['local_storage_injected']}/{result['local_storage_total']}")

            if result.get("validation"):
                v = result["validation"]
                print(f"   Auth: {v.get('auth_status', 'unknown')}")
                print(f"   Valid: {v.get('valid', False)}")

            if args.runtime:
                print("\n⚡ Loading into RuntimeEngine...")
                print("   ✅ RuntimeEngine ready")
        else:
            print("\n❌ Session load failed")
            if result.get("error"):
                print(f"   Error: {result['error']}")

    except Exception as e:
        logger.error(f"Load failed: {e}", exc_info=True)
        print("❌ Load failed — verify session file is valid and not corrupted")
        raise SystemExit(1) from e
    finally:
        loader.close()


def cmd_transfer(args):
    """Transfer session to target device/browser with fingerprint spoofing."""
    from tokenade.core.fingerprint.manager import FingerprintManager
    from tokenade.core.fingerprint.injector import validate_injection
    from tokenade.handlers.base import SessionData, AuthStatus

    print("\n" + "=" * 80)
    print("TOKENADE - Session Transfer")
    print("=" * 80)

    session_file = Path(args.session)
    if not session_file.exists():
        print(f"❌ Session file not found: {args.session}")
        raise SystemExit(1)

    with open(session_file) as f:
        session_data = json.load(f)

    fp_manager = FingerprintManager()
    fp_name = args.fingerprint or "default"

    print(f"\n📁 Session: {args.session}")
    print(f"🎯 Target fingerprint: {fp_name}")

    fp = fp_manager.load(fp_name)
    if fp:
        print(f"   User Agent: {fp.user_agent[:60]}...")
        print(f"   Screen: {fp.screen_width}x{fp.screen_height}")
        print(f"   Platform: {fp.platform}")

    config = BrowserConfig(
        headless=not args.visible,
        user_data_dir=args.profile_dir,
        fingerprint=fp.to_dict() if fp else None,
        stealth_level=args.stealth_level,
    )

    browser = BrowserFactory.create(**config.__dict__)

    try:
        browser.launch()

        if fp and args.validate_stealth:
            print("\n🔍 Validating stealth injection...")
            result = validate_injection(browser)
            if result["valid"]:
                print("   ✅ Stealth injection verified")
                print(f"   Webdriver: {result['webdriver_undefined']}")
                print(f"   User Agent: {result['user_agent'][:50]}...")
            else:
                print("   ⚠️  Stealth injection may not be fully active")

        site = session_data.get("site_name") or "google"
        handler_cls = resolve_legacy_handler_class(site)
        handler = handler_cls(browser)
        hname = getattr(handler_cls, "__name__", handler_cls.__class__.__name__)
        print(f"   Handler: {hname} (legacy; prefer plugins)")

        auth_raw = session_data.get("auth_status", "unknown")
        try:
            auth_status = AuthStatus(auth_raw)
        except (ValueError, KeyError):
            auth_status = AuthStatus.UNKNOWN

        session = SessionData(
            site_name=site,
            auth_status=auth_status,
            tokens=[],
            cookies=session_data.get("cookies", []),
        )

        success = handler.inject_session(session)

        if success:
            print("✅ Session transfer successful")
            if args.profile_dir:
                print(f"💾 Profile saved to: {args.profile_dir}")
        else:
            print("❌ Session transfer failed")
            raise SystemExit(1)

    finally:
        browser.close()


def cmd_inject_profile(args):
    """Inject cookies directly into browser profile."""
    print("\n" + "=" * 80)
    print("TOKENADE - Direct Profile Injection")
    print("=" * 80)

    session_file = Path(args.session)
    if not session_file.exists():
        print(f"❌ Session file not found: {args.session}")
        return

    print(f"\n📂 Session: {args.session}")
    print(f"🌐 Browser: {args.browser}")
    print(f"📁 Profile: {args.profile}")

    if args.dry_run:
        print("\n🔍 Dry run mode - no changes will be made")

    try:
        if args.dry_run:
            with open(session_file) as f:
                session = json.load(f)

            cookies = session.get('cookies', [])
            print("\n📊 Session info:")
            print(f"   Site: {session.get('site_name', 'unknown')}")
            print(f"   Cookies: {len(cookies)}")
            print(f"   Auth status: {session.get('auth_status', 'unknown')}")

            if cookies:
                print("\n🍪 Sample cookies:")
                for cookie in cookies[:5]:
                    print(f"   • {cookie.get('name')}: {cookie.get('domain')}")
                if len(cookies) > 5:
                    print(f"   ... and {len(cookies) - 5} more")
        else:
            result = inject_session_to_profile(
                session_file=str(session_file),
                profile_path=args.profile,
                browser=args.browser,
                backup=not args.no_backup
            )

            if result.success:
                print("\n✅ Injection successful")
                print(f"   Injected: {result.cookies_injected}/{result.cookies_total} cookies")
                if result.backup_path:
                    print(f"   Backup: {result.backup_path}")
            else:
                print("\n❌ Injection failed")
                if result.error:
                    print(f"   Error: {result.error}")
                raise SystemExit(1)

    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"Profile injection failed: {e}", exc_info=True)
        print("❌ Profile injection failed — check browser is not running")
        raise SystemExit(1) from e
