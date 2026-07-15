"""Session export CLI command."""
import json
import logging
import os

from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery
from tokenade.core.importer.cookie_extractor import CookieExtractor
from tokenade.core.importer.local_storage_extractor import LocalStorageExtractor
from tokenade.core.importer.session_packager import SessionPackager

logger = logging.getLogger("tokenade")


def cmd_export(args):
    """Export session from existing browser to .tokenade file."""
    from tokenade.cli.session import _extract_via_cdp

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
    cdp_port = getattr(args, 'cdp_port', None)

    from tokenade.core.config import load_config
    config = load_config()
    if not browser_name or browser_name == "unknown":
        browser_name = config.get("default_browser") or browser_name
    if not args.profile:
        args.profile = config.get("default_profile")

    # CDP export talks to a running browser — no local profile required
    if not cdp_port:
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

        if not browser_path:
            print("❌ No browser path specified.")
            print("   Use --browser-name (e.g., --browser-name firefox) or --browser-path /path/to/profile")
            print("   Or use --cdp-port N to extract from a running browser")
            print("   Run 'tokenade export --list-profiles' to discover available profiles")
            return

    if cdp_port:
        launched_browser = None
        import urllib.request as _urllib_req
        try:
            _urllib_req.urlopen(f"http://127.0.0.1:{cdp_port}/json/version", timeout=2)
            print(f"\n🔌 Connected to existing browser on port {cdp_port}")
        except Exception:
            import subprocess
            import platform

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
                pass

            print(f"\n🚀 Launching {browser_name} with CDP on port {cdp_port}...")
            from tokenade.core.browser.undetectable import SystemBrowserLauncher
            launcher = SystemBrowserLauncher()
            try:
                real_profile = launcher._get_default_profile_dir(browser_name)
                launched_browser = launcher.launch(
                    browser=browser_name,
                    visible=True,
                    port=cdp_port,
                    profile_dir=real_profile,
                )
                print(f"   ✅ Browser launched (PID: {launched_browser.pid})")
                import time as _time
                _time.sleep(3)
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

    plugin_name = getattr(args, 'plugin', None)
    use_plugin = not getattr(args, 'no_plugin', False)
    site_handler = None

    if plugin_name or use_plugin:
        from tokenade.core.importer.plugin_export import PluginExporter
        exporter = PluginExporter()
        exporter._load_handlers()

        if plugin_name:
            site_handler = exporter.get_handler(plugin_name)
            if site_handler:
                print(f"   🔌 Using plugin: {plugin_name} (overrides default export worker)")
                if hasattr(site_handler, "get_site_config"):
                    try:
                        sc = site_handler.get_site_config() or {}
                        if sc.get("domains"):
                            print(f"   📄 site_config.json: {sc.get('name', '?')} ({len(sc.get('domains') or [])} domains)")
                    except Exception:
                        pass
            else:
                print(f"   ⚠️  Plugin not found: {plugin_name} — falling back to default extraction")
                print(f"   ➡️  Install: tokenade plugin install {plugin_name}")
        elif domain_filter:
            site_handler = exporter.find_handler(domain_filter)
            if site_handler:
                print(f"   🔌 Auto-discovered handler: {getattr(site_handler, 'name', '?')} (overrides default)")
            else:
                print("   ℹ️  No handler found for domains, using default extraction")
                joined = ",".join(domain_filter).lower()
                if "google" in joined or "gmail" in joined:
                    print("   💡 Google tip: tokenade export --browser-name firefox --plugin google-handler -o gmail.tokenade")
                elif "github" in joined:
                    print("   💡 GitHub tip: tokenade export --browser-name firefox --plugin github-handler -o github.tokenade")
        else:
            print("   ℹ️  No --domains / --plugin: exporting unfiltered cookies from the profile.")
            print("   💡 Prefer a site plugin (domains from site_config.json):")
            print("      tokenade export --list-handlers")
            print("      tokenade export --browser-name firefox --plugin google-handler -o gmail.tokenade")

        if site_handler and not domain_filter and hasattr(site_handler, "get_export_domains"):
            try:
                plugin_domains = site_handler.get_export_domains() or []
                if plugin_domains:
                    domain_filter = list(plugin_domains)
                    print(f"   🎯 Plugin export domains: {', '.join(domain_filter)}")
            except Exception as e:
                logger.debug(f"get_export_domains failed: {e}")

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

    if not cdp_port and not args.file_path and browser_name and browser_name != "unknown":
        try:
            import platform
            import subprocess as _sp
            _name = browser_name.lower()
            if platform.system() != "Windows":
                _patterns = {
                    "firefox": "firefox",
                    "chrome": "chrome",
                    "brave": "brave",
                    "edge": "msedge",
                }
                _pat = _patterns.get(_name, _name)
                _r = _sp.run(["pgrep", "-x", _pat], capture_output=True, text=True, timeout=3)
                if _r.returncode != 0 and _pat == "brave":
                    _r = _sp.run(["pgrep", "-x", "brave-browser"], capture_output=True, text=True, timeout=3)
                if _r.returncode == 0 and (_r.stdout or "").strip():
                    print(f"   ⚠️  {browser_name} appears to be running — cookie DB may be locked.")
                    print(f"   ➡️  Fully quit {browser_name} (check system tray / process list), then re-run export.")
            else:
                _r = _sp.run(
                    ["tasklist", "/fi", f"imagename eq {browser_name}.exe"],
                    capture_output=True, text=True, timeout=3,
                )
                if browser_name.lower() in (_r.stdout or "").lower():
                    print(f"   ⚠️  {browser_name} appears to be running — cookie DB may be locked.")
                    print(f"   ➡️  Fully quit {browser_name} (Task Manager), then re-run export.")
        except Exception:
            pass

    try:
        if cdp_port:
            pass
        elif args.file_path:
            cookies = extractor.extract_from_file(args.file_path, args.format or "netscape")
        else:
            cookies = extractor.extract(site_filter=None, progress_callback=_progress)
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)
        err = str(e).lower()
        print("❌ Extraction failed")
        if "locked" in err or "busy" in err or "sqlite" in err:
            print("   Cookie database is locked (browser still open or crashed with lock held).")
            print(f"   ➡️  Fully quit {browser_name}, wait a few seconds, then retry export.")
            print("   ➡️  On Linux/macOS: ensure no leftover browser processes remain.")
        else:
            print("   Check browser profile is accessible and you have read permission.")
            print(f"   Detail: {e}")
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

    extra_cookies = []
    if cookies:
        for c in cookies:
            name = c.get("name", "")
            if name in ("EMAIL", "email"):
                extra_cookies.append(c)

    package = packager.package(
        cookies=cookies,
        browser=browser_name,
        profile=args.profile or "unknown",
        local_storage=local_storage if local_storage else None,
        session_storage=session_storage if session_storage else None,
        extra_cookies=extra_cookies if extra_cookies else None,
    )

    site_name = package.get("site_name", "session")
    output = args.output or f"{site_name}_session"

    encrypt_password = getattr(args, 'encrypt_password', None)
    if encrypt_password:
        saved_path = packager.save(package, output, encrypt=True)
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
