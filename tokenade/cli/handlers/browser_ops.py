"""Browser ops CLI - launch, refresh-browser, accounts."""
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


def _resolve_launch_profile(browser: str, profile_name: Optional[str], refresh_profiles: bool = False):
    """Resolve a launch profile by browser/name using browser discovery cache."""
    from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery

    discovery = BrowserProfileDiscovery()
    profiles_by_browser = discovery.refresh_cache() if refresh_profiles else None
    profiles = profiles_by_browser.get(browser, []) if profiles_by_browser is not None else discovery.discover_browser(browser)
    if not profiles:
        return None
    if profile_name:
        wanted = profile_name.lower()
        for profile in profiles:
            if profile.name.lower() == wanted or Path(profile.path).name.lower() == wanted:
                return profile
        return None
    for profile in profiles:
        if profile.is_default:
            return profile
    return profiles[0]


def _copy_launch_profile(source_dir: str, dest_dir: str) -> bool:
    """Copy a discovered launch profile into an isolated working directory."""
    import shutil

    skip_dirs = {
        "Cache", "Code Cache", "GPUCache", "ShaderCache", "GrShaderCache",
        "Service Worker", "ServiceWorker", "ScriptCache", "component_crx_cache",
        "extensions_crx_cache", "cache2", "startupCache", "thumbnails",
    }

    def _ignore(_directory, contents):
        return [name for name in contents if name in skip_dirs]

    try:
        shutil.copytree(source_dir, dest_dir, ignore=_ignore, dirs_exist_ok=True)
        return True
    except Exception as e:
        logger.warning("Profile copy failed from %s to %s: %s", source_dir, dest_dir, e)
        return False


def cmd_launch(args):
    """Launch undetectable browser with CDP (CloakBrowser default)."""
    import asyncio

    from tokenade.core.browser.undetectable import SystemBrowserLauncher, BrowserProcess
    from tokenade.core.browser.cdp_connection import CDPConnection, get_undetectable_stealth_script
    from tokenade.core.importer.session_packager import SessionPackager

    print("\n" + "=" * 80)
    print("TOKENADE - Undetectable Browser")
    print("=" * 80)

    browser_name = (getattr(args, "browser", None) or "cloak").lower()
    if browser_name in ("cloakbrowser", "default"):
        browser_name = "cloak"
    args.browser = browser_name

    # --headless wins; otherwise default to visible UI
    visible = bool(getattr(args, "visible", False)) or not bool(getattr(args, "headless", False))
    if getattr(args, "headless", False):
        visible = False
    args.visible = visible  # normalize for rest of function

    session = None
    site_handler = None
    session_path = getattr(args, "session", None)
    if session_path:
        decrypt_password = getattr(args, "decrypt_password", None)
        try:
            session = SessionPackager().load(session_path, password=decrypt_password)
        except Exception as e:
            print(f"[ERROR] Session load failed: {e}")
            return

        from tokenade.core.artifacts import ProfileArtifactManager, SessionPolicyError
        try:
            ProfileArtifactManager.preflight(
                session,
                purpose="launch",
                acknowledge_exclusive_move=bool(getattr(args, "acknowledge_exclusive_move", False)),
                allow_single_use=bool(getattr(args, "claim_single_use", False)),
            )
        except (SessionPolicyError, ValueError) as exc:
            print(f"[ERROR] {exc}")
            print("   Browser was not launched.")
            return

        metadata = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
        required_plugins = metadata.get("required_plugins", [])
        if not isinstance(required_plugins, list):
            print("[ERROR] Session required_plugins metadata must be a list")
            return
        if not required_plugins:
            plugin_data = session.get("plugin_data", {})
            if isinstance(plugin_data, dict):
                required_plugins = [
                    {"name": name, "reason": "embedded site-specific browser storage"}
                    for name in plugin_data
                ]
        if required_plugins and getattr(args, "no_plugin", False):
            names = ", ".join(str(item.get("name")) for item in required_plugins)
            print(f"[ERROR] Session requires plugin behavior that --no-plugin disables: {names}")
            print("   Browser was not launched. Remove --no-plugin and retry.")
            return
        elif required_plugins:
            exclusive = [
                item for item in required_plugins
                if isinstance(item, dict) and item.get("access_mode") == "exclusive_move"
            ]
            if exclusive and not getattr(args, "acknowledge_exclusive_move", False):
                print("[ERROR] This Session is an exclusive linked-device move, not a clone.")
                print("   Fully close the source browser and do not reopen its original WhatsApp profile.")
                print("   Concurrent source/target use can corrupt message sending and call state.")
                print("   Retry with --acknowledge-exclusive-move after the source is retired.")
                return
            from tokenade import __version__
            from tokenade.core.integration.plugin_dependencies import (
                check_runtime_dependencies,
                check_tokenade_compatibility,
            )
            from tokenade.core.integration.plugin_loader import PluginLoader

            requirement_loader = PluginLoader()
            requirement_failures = []
            for requirement in required_plugins:
                if not isinstance(requirement, dict):
                    requirement_failures.append(("unknown", "invalid requirement metadata"))
                    continue
                name = str(requirement.get("name") or "").strip()
                manifest = requirement_loader.get_manifest(name) if name else None
                if not manifest:
                    requirement_failures.append((name or "unknown", "not installed"))
                    continue
                if requirement_loader.is_disabled(name):
                    requirement_failures.append((name, "disabled"))
                    continue
                installed_version = str(manifest.get("version") or "0")
                minimum = requirement.get("min_version")
                if minimum:
                    from packaging.version import InvalidVersion, Version
                    try:
                        too_old = Version(installed_version) < Version(str(minimum))
                    except InvalidVersion:
                        requirement_failures.append((name, "invalid plugin version requirement"))
                        continue
                    if too_old:
                        requirement_failures.append((
                            name,
                            f"installed version {installed_version}; requires >= {minimum}",
                        ))
                        continue
                missing_dependencies = [
                    dependency for dependency in manifest.get("dependencies", [])
                    if not requirement_loader.get_manifest(str(dependency))
                ]
                if missing_dependencies:
                    requirement_failures.append((
                        name,
                        f"missing plugin dependencies: {', '.join(missing_dependencies)}",
                    ))
                    continue
                reports = [
                    check_tokenade_compatibility(manifest, __version__),
                    check_runtime_dependencies(manifest),
                ]
                issues = [issue for report in reports for issue in report.issues]
                if issues:
                    requirement_failures.append((
                        name,
                        "; ".join(f"{issue.requirement}: {issue.reason}" for issue in issues),
                    ))
                    continue
                loaded = requirement_loader.load_by_name(name)
                if not loaded:
                    requirement_failures.append((name, "failed to load"))
                    continue
                if not loaded.is_active:
                    requirement_failures.append(
                        (name, f"plugin is not active (state: {loaded.state.value})")
                    )
                    continue
                validator = getattr(loaded.instance, "validate_launch_requirements", None)
                if validator:
                    validation = validator(session, browser_name)
                    if not validation.success:
                        requirement_failures.append((
                            name,
                            validation.error or "Session is incompatible with this target",
                        ))

            if requirement_failures:
                print("[ERROR] Session requires unavailable plugins:")
                for name, reason in requirement_failures:
                    print(f"   - {name}: {reason}")
                    if reason == "not installed":
                        print(f"     Install: tokenade plugin install {name}")
                print("   Browser was not launched; install/fix the requirements and retry.")
                return

        if not getattr(args, "no_plugin", False):
            try:
                from tokenade.core.importer.plugin_export import PluginExporter

                exporter = PluginExporter()
                force_plugin = getattr(args, "plugin", None)
                recorded_plugin = (
                    session.get("metadata", {}).get("site_handler", {}).get("plugin_name")
                    if isinstance(session.get("metadata"), dict) else None
                )
                plugin_data = session.get("plugin_data", {})
                if not recorded_plugin and isinstance(plugin_data, dict) and len(plugin_data) == 1:
                    recorded_plugin = next(iter(plugin_data))
                if force_plugin:
                    site_handler = exporter.get_handler(force_plugin)
                elif recorded_plugin:
                    site_handler = exporter.get_handler(str(recorded_plugin))
                else:
                    domains = [
                        str(cookie.get("domain") or "").lstrip(".")
                        for cookie in session.get("cookies", [])
                        if cookie.get("domain")
                    ]
                    site_name = str(session.get("site_name") or "")
                    site_handler = exporter.find_handler(domains or ([site_name] if site_name else []))
            except Exception as e:
                logger.debug("Pre-launch site handler resolution failed: %s", e)

    # Resolve upstream proxy
    upstream_proxy = _resolve_upstream_proxy(args)
    if upstream_proxy:
        print(f"[PROXY] Upstream proxy: {upstream_proxy}")

    try:
        if browser_name == "firefox":
            if not session_path:
                print("[ERROR] Firefox launch requires --session")
                return
            from tokenade.core.importer.session_loader import SessionLoader

            proxy = {"server": upstream_proxy} if upstream_proxy else None
            loader = SessionLoader()
            result = loader.load(
                session_path,
                validate=False,
                visible=args.visible,
                profile_dir=args.profile_dir,
                inject_local_storage=True,
                acknowledge_exclusive_move=bool(
                    getattr(args, "acknowledge_exclusive_move", False)
                ),
                allow_single_use=bool(getattr(args, "claim_single_use", False)),
                browser_type="firefox",
                proxy=proxy,
                target_url=args.url,
            )
            if not result.get("success"):
                print(f"[ERROR] Firefox Session load failed: {result.get('error')}")
                return
            print(
                f"[OK] Firefox Session loaded: {result['cookies_injected']}/"
                f"{result['cookies_total']} cookies"
            )
            if args.visible and loader._browser:
                print("Press Ctrl+C to close Firefox")
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    print("\n[STOP] Closing Firefox...")
                finally:
                    loader._browser.close()
                    loader._browser = None
            return

        # --- CloakBrowser path (project default) ---
        if browser_name == "cloak" and not getattr(args, "no_cloak", False):
            from tokenade.core.browser.stealth.cloak import (
                CloakBrowserBackend,
                is_cloakbrowser_available,
            )
            backend = CloakBrowserBackend()
            if not backend.is_available():
                if is_cloakbrowser_available():
                    print("[...] CloakBrowser binary missing - downloading...")
                    if not backend.ensure_ready():
                        print(
                            "[ERROR] CloakBrowser download failed. "
                            "Retry: tokenade cloak install"
                        )
                        print("   Or use: tokenade launch --browser firefox|brave|edge|chrome")
                        raise SystemExit(1)
                    print("[OK] CloakBrowser installed - launching...")
                else:
                    print(
                        "[ERROR] cloakbrowser package not installed. "
                        "Run: pip install cloakbrowser && tokenade cloak install"
                    )
                    print("   Or use: tokenade launch --browser firefox|brave|edge|chrome")
                    raise SystemExit(1)
            print(f"\n[NET] Browser: cloak (CloakBrowser)")
            print(f"[CDP] CDP Port: {args.port}")
            print(f"[UI] Visible: {args.visible}")
            import tempfile
            profile_dir = args.profile_dir or ""
            if not profile_dir:
                profile_dir = tempfile.mkdtemp(prefix="tokenade_cloak_clean_")
                print(f"   [DIR] Clean profile (session inject): {profile_dir}")
            else:
                print(f"   [DIR] Profile: {profile_dir}")
            if session and session.get("profile_artifacts"):
                try:
                    restored = ProfileArtifactManager.restore(
                        session, profile_dir, "cloak",
                        allow_single_use=bool(getattr(args, "claim_single_use", False)),
                    )
                    print(f"   [OK] Restored {restored['restored']} profile artifact(s)")
                except Exception as exc:
                    print(f"[ERROR] Profile artifact restore failed: {exc}")
                    return
            # Pick a free port if default is busy
            cdp_port = int(args.port or 9222)
            try:
                import socket
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as _s:
                    if _s.connect_ex(("127.0.0.1", cdp_port)) == 0:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as _s2:
                            _s2.bind(("127.0.0.1", 0))
                            cdp_port = _s2.getsockname()[1]
                        print(f"   [WARN] Port {args.port} busy - using {cdp_port}")
                        args.port = cdp_port
            except Exception:
                pass
            proc = backend.serve_cdp(
                port=cdp_port,
                proxy=upstream_proxy,
                headless=not args.visible,
                user_data_dir=profile_dir,
            )
            browser = BrowserProcess(
                process=proc,
                port=cdp_port,
                profile_dir=profile_dir or "(cloak)",
                browser_name="cloak",
            )
        else:
            # --- System browser path (explicit override) ---
            launcher = SystemBrowserLauncher()
            system_browser = browser_name
            if system_browser == "cloak":
                # --no-cloak with default name: fall back to brave (not chrome)
                system_browser = "brave"
                args.browser = system_browser

            browser_path = getattr(args, "browser_path", None) or launcher.find_browser(system_browser)
            if not browser_path:
                print(f"[ERROR] {system_browser} not found. Install it or specify --browser-path")
                return

            print(f"\n[NET] Browser: {system_browser} ({browser_path})")
            print(f"[CDP] CDP Port: {args.port}")
            print(f"[UI] Visible: {args.visible}")

            # Profile lock only matters when directly reusing a real system profile.
            using_original_profile = bool(getattr(args, "use_original_profile", False))
            if using_original_profile and bool(getattr(args, "copy_profile", False)):
                print("[ERROR] Use either --copy-profile or --use-original-profile, not both.")
                return
            using_isolated_profile = bool(args.profile_dir or args.session or not using_original_profile)
            if not using_isolated_profile:
                import subprocess as _sp
                _ps_cmd = ["pgrep", "-c", system_browser] if platform.system() != "Windows" else ["tasklist", "/fi", f"imagename eq {system_browser}.exe"]
                try:
                    _running = _sp.run(_ps_cmd, capture_output=True, text=True, timeout=3)
                    _is_running = False
                    if platform.system() != "Windows" and _running.returncode == 0:
                        _is_running = int(_running.stdout.strip()) > 0
                    elif platform.system() == "Windows" and system_browser.lower() in _running.stdout.lower():
                        _is_running = True
                    if _is_running:
                        print(f"   [WARN] {system_browser} is already running. Default profile is locked.")
                        print(f"   Close all {system_browser} windows first, then retry.")
                        print(f"   Or omit --use-original-profile to launch an isolated profile copy.")
                        return
                except Exception:
                    pass

            profile_dir = args.profile_dir
            selected_profile = None
            profile_name = getattr(args, "profile", None)
            if profile_name and profile_dir:
                print("[ERROR] Use either --profile NAME or --profile-dir PATH, not both.")
                return
            if profile_name or (not profile_dir and not args.session):
                selected_profile = _resolve_launch_profile(
                    system_browser,
                    profile_name,
                    refresh_profiles=bool(getattr(args, "refresh_profiles", False)),
                )
                if profile_name and not selected_profile:
                    print(f"[ERROR] Profile '{profile_name}' not found for {system_browser}")
                    print("   Run 'tokenade export --list-profiles' to refresh and inspect profiles.")
                    return

            if args.session and not profile_dir:
                import tempfile
                if selected_profile and selected_profile.path:
                    profile_dir = tempfile.mkdtemp(
                        prefix=f"tokenade_{system_browser}_{selected_profile.name}_"
                    )
                    print(
                        f"   [DIR] Copying profile '{selected_profile.name}' "
                        f"for session inject from: {selected_profile.path}"
                    )
                    if _copy_launch_profile(selected_profile.path, profile_dir):
                        print(f"   [OK] Profile copied to: {profile_dir}")
                    else:
                        print("   [WARN] Profile copy failed, using fresh clean profile")
                        profile_dir = tempfile.mkdtemp(
                            prefix=f"tokenade_{system_browser}_clean_"
                        )
                else:
                    profile_dir = tempfile.mkdtemp(
                        prefix=f"tokenade_{system_browser}_clean_"
                    )
                    print(f"   [DIR] Clean profile (session inject): {profile_dir}")
                    print("   [TIP] Pass --profile NAME to base inject on a discovered profile.")
            elif not profile_dir and not args.session:
                real_dir = selected_profile.path if selected_profile else launcher._get_default_profile_dir(system_browser)
                if real_dir and using_original_profile:
                    profile_dir = real_dir
                    label = selected_profile.name if selected_profile else "default"
                    print(f"   [DIR] Using original profile: {label} ({real_dir})")
                elif real_dir:
                    import tempfile
                    profile_dir = tempfile.mkdtemp(prefix=f"tokenade_{system_browser}_")
                    label = selected_profile.name if selected_profile else "default"
                    print(f"   [DIR] Copying profile '{label}' from: {real_dir}")
                    if _copy_launch_profile(real_dir, profile_dir):
                        print(f"   [OK] Profile copied to: {profile_dir}")
                    else:
                        print(f"   [WARN] Profile copy failed, using fresh profile")

            if session and session.get("profile_artifacts"):
                try:
                    restored = ProfileArtifactManager.restore(
                        session, profile_dir, system_browser,
                        allow_single_use=bool(getattr(args, "claim_single_use", False)),
                    )
                    print(f"   [OK] Restored {restored['restored']} profile artifact(s)")
                except Exception as exc:
                    print(f"[ERROR] Profile artifact restore failed: {exc}")
                    return

            browser = launcher.launch(
                browser=system_browser,
                visible=args.visible,
                port=args.port,
                profile_dir=profile_dir,
                extra_args=args.extra_args.split(",") if args.extra_args else [],
                upstream_proxy=upstream_proxy,
            )

        print(f"\n[OK] Browser launched (PID: {browser.pid})")
        print(f"   CDP URL: {browser.cdp_url}")
        print(f"   Profile: {browser.profile_dir}")

        # Inject session if provided - session file is ALWAYS authoritative
        if args.session:
            print(f"\n[DIR] Loading session: {args.session}")

            cookies = session.get("cookies", [])
            source_browser = session.get("source_device", {}).get("browser", "unknown")
            if isinstance(source_browser, dict):
                source_browser = source_browser.get("name") or source_browser.get("browser") or "unknown"
            print(f"   Cookies: {len(cookies)} (from {source_browser})")

            # Site-handler plugin override: domains, dashboard URL, cookie filter
            site_hint = ""
            cookie_domains = list({
                (c.get("domain") or "").lstrip(".")
                for c in cookies
                if c.get("domain")
            })
            if not site_handler and not getattr(args, "no_plugin", False):
                try:
                    from tokenade.core.importer.plugin_export import PluginExporter
                    exporter = PluginExporter()
                    force_plugin = getattr(args, "plugin", None)
                    site_name = str(session.get("site_name") or session.get("site") or "")
                    domain_guess = cookie_domains or ([site_name] if site_name else [])
                    if force_plugin:
                        exporter._load_handlers()
                        site_handler = exporter._handlers.get(force_plugin)
                        if not site_handler:
                            print(f"   [WARN] Plugin not found: {force_plugin} (using default launch path)")
                    elif domain_guess:
                        site_handler = exporter.find_handler(domain_guess)

                    if site_handler:
                        hname = getattr(site_handler, "name", type(site_handler).__name__)
                        # session-backup is a generic helper, not a real site handler
                        if "session-backup" in str(hname).lower() or "backup" == str(hname).lower():
                            site_handler = None
                        else:
                            print(f"   [CDP] Site handler: {hname}")
                            # Prefer plugin dashboard URL when user did not pass --url
                            if not args.url and hasattr(site_handler, "get_dashboard_url"):
                                dash = site_handler.get_dashboard_url()
                                if dash:
                                    args.url = dash
                                    print(f"   [URL] URL from plugin: {dash}")
                            # Prefer plugin cookie filter when available
                            try:
                                if hasattr(site_handler, "_is_google_cookie"):
                                    filtered = [c for c in cookies if site_handler._is_google_cookie(c)]
                                    if filtered:
                                        cookies = filtered
                                        print(f"   [HIT] Plugin-filtered cookies: {len(cookies)}")
                            except Exception:
                                pass
                            if "google" in hname.lower() or any(
                                "google" in (d or "") for d in cookie_domains
                            ):
                                site_hint = "google"
                except Exception as e:
                    logger.debug("Site handler resolution failed: %s", e)

            # Always auto-detect destination URL when user did not pass --url
            # (prevents stuck about:blank after cookie inject)
            if not getattr(args, "url", None):
                detected = _detect_url_from_cookies(cookies)
                if not detected:
                    site_name = str(session.get("site_name") or session.get("site") or "").strip()
                    if site_name and "." in site_name:
                        detected = f"https://{site_name.lstrip('.')}"
                    elif site_name:
                        # common short names
                        _name_map = {
                            "spotify": "https://open.spotify.com",
                            "google": "https://mail.google.com",
                            "gmail": "https://mail.google.com",
                            "github": "https://github.com",
                            "linkedin": "https://www.linkedin.com",
                            "reddit": "https://www.reddit.com",
                            "amazon": "https://www.amazon.com",
                            "facebook": "https://www.facebook.com",
                            "twitter": "https://x.com",
                            "x": "https://x.com",
                        }
                        detected = _name_map.get(site_name.lower())
                if detected:
                    args.url = detected
                    print(f"   [URL] Auto URL: {detected}")
                else:
                    print("   [WARN] No destination URL detected - staying on about:blank")
                    print("      Pass --url https://example.com to navigate after inject")

            if not site_hint:
                _site = str(session.get("site_name") or session.get("site") or "").lower()
                _domains = " ".join(str(c.get("domain") or "") for c in cookies).lower()
                fname = str(args.session).lower()
                if "google" in _site or "google." in _domains or "youtube." in _domains or "gmail" in fname:
                    site_hint = "google"

            # Sanity-check the inline guess against the unified recommend()
            # engine. Mismatch is logged at debug level so future contributors
            # can see the seam (the inline block above is the historical path;
            # recommend() is the canonical one per ADR-0003).
            try:
                from tokenade.core.recommend import recommend
                rec = recommend(
                    session=session,
                    domains=cookie_domains if 'cookie_domains' in locals() else None,
                )
                if rec.site and rec.site != site_hint:
                    logger.debug(
                        "recommend() suggests site=%s (inline hint=%s); "
                        "future cleanup: prefer recommend() per ADR-0003",
                        rec.site, site_hint,
                    )
                    if not site_hint:
                        site_hint = rec.site
                if rec.plugin and not getattr(args, "plugin", None):
                    logger.debug("recommend() suggests plugin=%s", rec.plugin)
            except Exception as _e:
                logger.debug("recommend() sanity-check failed: %s", _e)

            chrome_like = args.browser.lower() in (
                "chrome", "chromium", "chrome-canary", "chrome-beta", "google-chrome",
            )
            if site_hint == "google":
                print(f"   [TIP] Google recipe: donor + target should be Firefox/Brave/Edge (not Chrome).")
                print(f"   [OK] Same .tokenade works multi-browser + multi-device on non-Chrome targets.")
                print(f"   [NAV] Open the product URL (mail.google.com) - avoid bouncing through accounts.google.com after inject.")
            if site_hint == "google" and chrome_like:
                print(f"   [WARN] Target is {args.browser}: Google usually rejects portable sessions in Chrome-family browsers.")
                print(f"   ->  Prefer: tokenade launch --browser brave --session {args.session} --profile-dir /tmp/tokenade-brave-clean --visible")

            if source_browser != "unknown" and source_browser != args.browser:
                print(f"   [WARN] Cross-browser: {source_browser} -> {args.browser}")
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
                print(f"[ERROR] Failed to create new tab: {e}")
                _tab_ws_url = None
                _tab_id = None

            if not _tab_ws_url:
                print("[ERROR] Failed to create tab")
                return

            print(f"   Tab: {_tab_id}")
            stealth_script = get_undetectable_stealth_script()
            storage = session.get("storage") if isinstance(session.get("storage"), dict) else {}
            local_by_origin = storage.get("local") if isinstance(storage.get("local"), dict) else {}
            session_by_origin = storage.get("session") if isinstance(storage.get("session"), dict) else {}
            current_origin = None
            if args.url:
                try:
                    from urllib.parse import urlparse

                    parsed = urlparse(args.url)
                    if parsed.scheme and parsed.netloc:
                        current_origin = f"{parsed.scheme}://{parsed.netloc}"
                except Exception:
                    pass
            local_data = local_by_origin.get(current_origin, {}) if current_origin else {}
            session_data = session_by_origin.get(current_origin, {}) if current_origin else {}
            if not local_data and len(local_by_origin) == 1:
                local_data = next(iter(local_by_origin.values())) or {}
            if not session_data and len(session_by_origin) == 1:
                session_data = next(iter(session_by_origin.values())) or {}
            local_data = local_data or session.get("local_storage", {})
            session_data = session_data or session.get("session_storage", {})
            if ProfileArtifactManager.web_storage_is_superseded(session):
                local_data = {}
                session_data = {}

            from tokenade.core.importer.session_loader import SessionLoader

            try:
                inject_res = asyncio.run(
                    SessionLoader().inject_into_cdp_tab(
                        _tab_ws_url,
                        cookies,
                        local_data=local_data,
                        session_data=session_data,
                        url=args.url,
                        stealth_script=stealth_script,
                    )
                )
                print(
                    f"   Cookies injected: {inject_res['injected_cookies']}/{inject_res['total_cookies']}"
                    + (f" (skipped {inject_res['failed_cookies']})" if inject_res['failed_cookies'] else ""),
                    flush=True,
                )
                from tokenade.core.importer.session_loader import (
                    storage_shortfall_message,
                )

                _shortfall = storage_shortfall_message(inject_res)
                if _shortfall:
                    print(f"   [WARN] {_shortfall}")
                if inject_res.get("title") or inject_res.get("url"):
                    print(f"\n   [FILE] Page: {inject_res.get('title')}")
                    print(f"   [URL] URL: {inject_res.get('url')}")
            except Exception as e:
                print(f"[ERROR] CDP injection failed: {e}")
                return

        elif args.url:
            # Just navigate to URL - same PUT /json/new approach
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
                    print(f"[ERROR] Failed to create tab: {e}")
                    return

                tab_ws = await websockets.connect(
                    tab_ws_url, max_size=10 * 1024 * 1024,
                    ping_interval=30, ping_timeout=10,
                )

                # Inject stealth (best-effort - some browsers hang on Page.enable)
                stealth_script = get_undetectable_stealth_script()
                try:
                    await cdp_cmd(tab_ws, "Page.enable")
                    await cdp_cmd(
                        tab_ws,
                        "Page.addScriptToEvaluateOnNewDocument",
                        {"source": stealth_script},
                    )
                except Exception as _stealth_err:
                    print(f"   [WARN] Stealth inject skipped ({_stealth_err}); continuing")

                # Navigate
                print(f"\n   Navigating to: {args.url}")
                await cdp_cmd(tab_ws, "Page.navigate", {"url": args.url})
                await asyncio.sleep(4)

                title_result = await cdp_cmd(tab_ws, "Runtime.evaluate", {"expression": "document.title", "returnByValue": True})
                title = title_result.get("result", {}).get("value", "")

                url_result = await cdp_cmd(tab_ws, "Runtime.evaluate", {"expression": "window.location.href", "returnByValue": True})
                url = url_result.get("result", {}).get("value", "")

                print(f"\n   [FILE] Page: {title}")
                print(f"   [URL] URL: {url}")

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
        launch_timeout = 0
        try:
            launch_timeout = int(getattr(args, "timeout", 0) or 0)
        except (TypeError, ValueError):
            launch_timeout = 0
        if launch_timeout > 0:
            print(f"\nAuto-closing in {launch_timeout}s (--timeout); Ctrl+C closes now")
        else:
            print("\nPress Ctrl+C to close the browser")
        print(f"{'=' * 80}\n")

        # Keep browser running (forever, or until --timeout elapses)
        try:
            if launch_timeout > 0:
                deadline = time.time() + launch_timeout
                _proc = getattr(browser, "process", None)
                _poll = getattr(_proc, "poll", None) if _proc is not None else None
                while time.time() < deadline:
                    if _proc is None:
                        break
                    if callable(_poll):
                        try:
                            if _proc.poll() is not None:
                                break
                        except Exception:
                            break
                    time.sleep(1)
                print(f"\n[TIME] --timeout {launch_timeout}s elapsed - closing browser...")
                browser.close()
            else:
                browser.process.wait()
        except KeyboardInterrupt:
            print("\n[STOP] Closing browser...")
            browser.close()

    except RuntimeError as e:
        print(f"\n[ERROR] {e}")
    except Exception as e:
        logger.error(f"Launch failed: {e}", exc_info=True)
        print(f"\n[ERROR] Launch failed: {e}")


def _unwrap_refresh_result(result, original_session):
    """Normalize plugin refresh() return value to a plain session dict.

    Plugins return PluginResult; older code returned a bare dict. Never pass
    PluginResult into SessionPackager.save (not JSON-serializable -> 0-byte files).
    """
    if result is None:
        raise ValueError("plugin refresh returned None")
    # PluginResult dataclass / duck-type
    if hasattr(result, "success") and hasattr(result, "data"):
        if not getattr(result, "success", False):
            err = getattr(result, "error", None) or "plugin refresh failed"
            raise ValueError(err)
        data = getattr(result, "data", None) or {}
        if isinstance(data, dict):
            if isinstance(data.get("session"), dict):
                return data["session"]
            # some plugins put cookies at top level of data
            if "cookies" in data:
                merged = dict(original_session)
                merged.update(data)
                return merged
        raise ValueError("plugin refresh succeeded but returned no session data")
    if isinstance(result, dict):
        if "cookies" in result or "site_name" in result:
            return result
        if isinstance(result.get("session"), dict):
            return result["session"]
    raise TypeError(f"plugin refresh returned unsupported type: {type(result)!r}")


def _refresh_logged_in_heuristic(page_url: str, page_title: str, cookies) -> bool:
    """Best-effort login check after browser refresh."""
    url_l = (page_url or "").lower()
    title_l = (page_title or "").lower()
    signin_markers = (
        "accountchooser", "servicelogin", "/signin", "/login", "login?",
        "accounts.google.com/v3/signin", "oauth/authorize",
    )
    if any(m in url_l for m in signin_markers):
        return False
    if any(x in title_l for x in ("sign in", "log in", "login")):
        return False
    if not cookies:
        return False
    return True


_GENERIC_LOGOUT_SELECTORS = (
    "a[href='/login']",
    "a[href='/signin']",
    # A visible password field on a dashboard URL means logged out even
    # when the SPA has not redirected yet (Discord serves the login form
    # at /channels/@me's shell without flipping URL/title in time).
    "input[type='password']",
)


def _resolve_logout_selectors(cookies, site_name="", use_plugins=True):
    """Collect DOM logged-out selectors for the refresh login check.

    Prefers the site handler's ``site_config.json``
    (``logged_out_selectors`` + ``login_indicator_css``), falls back to
    generic login-link selectors. With ``use_plugins=False`` (``--no-plugin``)
    no plugin code runs at all. Never raises; returns at most 8.
    """
    selectors = []
    if not use_plugins:
        return list(_GENERIC_LOGOUT_SELECTORS)
    try:
        from tokenade.core.importer.plugin_export import PluginExporter

        domains = sorted(
            {
                (c.get("domain") or "").lstrip(".")
                for c in cookies or []
                if c.get("domain")
            }
        )
        if not domains and site_name and "." in str(site_name):
            domains = [str(site_name).lstrip(".")]
        handler = PluginExporter().find_handler(domains) if domains else None
        if handler is not None and hasattr(handler, "get_site_config"):
            try:
                cfg = handler.get_site_config() or {}
            except Exception:
                cfg = {}
            for sel in cfg.get("logged_out_selectors") or []:
                if sel and str(sel) not in selectors:
                    selectors.append(str(sel))
            login_css = cfg.get("login_indicator_css")
            if login_css and str(login_css) not in selectors:
                selectors.append(str(login_css))
    except Exception as e:
        logger.debug("logout selector resolution failed: %s", e)
    for sel in _GENERIC_LOGOUT_SELECTORS:
        if sel not in selectors:
            selectors.append(sel)
    return selectors[:8]


def _resolve_login_selectors(cookies, site_name="", use_plugins=True):
    """Collect DOM logged-in selectors for the refresh login check.

    Uses the site handler's ``logged_in_selectors`` (positive proof of an
    authenticated page). Empty when the handler declares none — callers
    then fall back to the negative heuristic. Never raises.
    """
    selectors = []
    if not use_plugins:
        return selectors
    try:
        from tokenade.core.importer.plugin_export import PluginExporter

        domains = sorted(
            {
                (c.get("domain") or "").lstrip(".")
                for c in cookies or []
                if c.get("domain")
            }
        )
        if not domains and site_name and "." in str(site_name):
            domains = [str(site_name).lstrip(".")]
        handler = PluginExporter().find_handler(domains) if domains else None
        if handler is not None and hasattr(handler, "get_logged_in_selectors"):
            try:
                for sel in handler.get_logged_in_selectors() or []:
                    if sel and str(sel) not in selectors:
                        selectors.append(str(sel))
            except Exception:
                pass
    except Exception as e:
        logger.debug("login selector resolution failed: %s", e)
    return selectors[:8]


def _default_refresh_output(session_file):
    """Default refresh output: ``<stem>.refreshed.tokenade`` next to input.

    The source session is never overwritten unless ``--output`` points at
    it explicitly (refreshing merges target-browser cookies into the jar,
    which would otherwise pollute the donor file).
    """
    from pathlib import Path as _Path

    p = _Path(str(session_file))
    return str(p.with_name(p.stem + ".refreshed" + p.suffix))


def cmd_refresh_browser(args):
    """Refresh session: inject -> navigate -> extract -> login-check -> exit.

    Exit 0 = logged in / refreshed OK. Exit 1 = failed / signed out.
    Browser is always closed when the command finishes.
    """
    from tokenade.core.importer.session_packager import SessionPackager
    from tokenade.core.browser.undetectable import SystemBrowserLauncher, BrowserProcess

    print("\n" + "=" * 80)
    print("TOKENADE - Cookie-Based Session Refresh")
    print("=" * 80)

    exit_ok = False
    browser = None
    profile_dir = ""
    session_file = Path(args.session)
    if not session_file.exists():
        print(f"[ERROR] Session file not found: {args.session}")
        raise SystemExit(1)

    packager = SessionPackager()
    try:
        session = packager.load(str(session_file))
    except Exception as e:
        print(f"[ERROR] Failed to load session: {e}")
        raise SystemExit(1)

    cookies = session.get("cookies", [])
    site_name = session.get("site_name", "unknown")
    source_browser = session.get("source_device", {}).get("browser", "unknown")

    if not cookies:
        print("[ERROR] No cookies in session file")
        raise SystemExit(1)

    # 2. Try plugin refresh first (auto-discover unless --no-plugin)
    plugin_name = getattr(args, "plugin", None)
    no_plugin = getattr(args, "no_plugin", False)
    plugin_args_list = getattr(args, "plugin_arg", None) or []
    output = getattr(args, "output", None)

    # Prefer real site refreshers over catch-all plugins (auto-refresh, session-share, ...)
    _GENERIC_REFRESHERS = {
        "auto-refresh", "session-share", "session-encrypt", "proxy-rotate",
        "session-backup", "session-merge", "session-expiry-alert",
    }
    auto_refresher = None
    if not plugin_name and not no_plugin:
        try:
            from tokenade.core.integration.plugin_loader import PluginLoader
            _loader = PluginLoader()
            _loader.load_all()
            # Prefer non-generic first
            for name, refresher in (_loader.list_refreshers() or {}).items():
                try:
                    if name in _GENERIC_REFRESHERS:
                        continue
                    if refresher.can_refresh(session):
                        auto_refresher = refresher
                        plugin_name = name
                        break
                except Exception:
                    continue
            if not auto_refresher:
                # only use generic if explicitly the only option and can_refresh
                auto_refresher = None  # skip generic auto-refresh for CLI browser path
            if plugin_name:
                print(f"\n[CDP] Auto-discovered refresher: {plugin_name} v{getattr(auto_refresher, 'version', '?')}")
        except Exception as e:
            logger.debug("Auto-discovery of refresher failed: %s", e)

    if plugin_name and not no_plugin:
        plugin_creds = {}
        for item in plugin_args_list:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                plugin_creds[item[0]] = item[1]

        try:
            from tokenade.core.integration.plugin_loader import PluginLoader
            loader = PluginLoader()
            loader.load_all()

            if auto_refresher and (
                not getattr(args, "plugin", None)
                or getattr(auto_refresher, "name", None) == plugin_name
            ):
                refresher = auto_refresher
            else:
                refresher = loader.get_refresher(plugin_name)
            if not refresher:
                print(f"[WARN] Plugin not found: {plugin_name}. Proceeding with browser refresh.")
            elif not refresher.can_refresh(session):
                print(f"[WARN] Plugin '{plugin_name}' cannot refresh this session. Proceeding with browser refresh.")
            else:
                print(f"\n[CDP] Using plugin: {plugin_name} v{getattr(refresher, 'version', '?')}")

                if hasattr(refresher, "get_credentials_args"):
                    for cred_arg in refresher.get_credentials_args():
                        arg_name = cred_arg["name"].lstrip("-").replace("-", "_")
                        if arg_name not in plugin_creds and cred_arg.get("required"):
                            print(f"[ERROR] Missing required plugin credential: {cred_arg['name']}")
                            print(f"   Use: --plugin-arg {arg_name} <value>")
                            raise SystemExit(1)

                try:
                    raw = refresher.refresh(session, plugin_creds)
                    session = _unwrap_refresh_result(raw, session)

                    save_path = output or _default_refresh_output(session_file)
                    if not output:
                        print(f"   [i] Source left unchanged; refreshed copy: {save_path}")
                    packager.save(session, save_path)
                    print(f"[OK] Session refreshed via plugin: {save_path}")
                    _run_post_refresh_plugins(loader, session)
                    print("\n[OK] REFRESH PASS (plugin)")
                    raise SystemExit(0)
                except SystemExit:
                    raise
                except Exception as e:
                    print(f"[WARN] Plugin refresh failed: {e}")
                    print("   Falling back to browser-based refresh...")
        except SystemExit:
            raise
        except ImportError:
            print("[WARN] Plugin system not available. Proceeding with browser refresh.")
        except Exception as e:
            print(f"[WARN] Plugin error: {e}. Proceeding with browser refresh.")

    # DOM login-check selectors (site handler config + generic fallbacks).
    # URL/title heuristics alone pass SPA shells that redirect to /login
    # after the wait (observed with Discord), so selector hits veto PASS.
    logout_selectors = _resolve_logout_selectors(
        cookies, site_name, use_plugins=not no_plugin
    )
    if logout_selectors:
        print(f"   [CDP] Logout selectors: {', '.join(logout_selectors)}")
    login_selectors = _resolve_login_selectors(
        cookies, site_name, use_plugins=not no_plugin
    )
    if login_selectors:
        print(f"   [CDP] Login selectors (positive proof): {', '.join(login_selectors)}")

    # Determine target URL
    target_url = getattr(args, "url", None)
    if not target_url:
        target_url = _detect_url_from_cookies(cookies)
        if not target_url:
            sn = str(site_name or "").strip()
            if sn and "." in sn:
                target_url = f"https://{sn.lstrip('.')}"
            elif sn and sn not in ("unknown", "session-backup"):
                _name_map = {
                    "spotify": "https://open.spotify.com",
                    "google": "https://myaccount.google.com",
                    "gmail": "https://mail.google.com",
                    "github": "https://github.com",
                    "linkedin": "https://www.linkedin.com",
                    "reddit": "https://www.reddit.com",
                    "twitter": "https://x.com",
                    "x": "https://x.com",
                    "youtube": "https://www.youtube.com",
                    "amazon": "https://www.amazon.com",
                }
                target_url = _name_map.get(sn.lower())
        if not target_url:
            print("[ERROR] Could not determine target URL. Use --url to specify.")
            raise SystemExit(1)

    browser_name = (getattr(args, "browser", None) or "cloak").lower()
    # Default headless=True; --visible forces a window (still closes at end)
    headless = True
    if getattr(args, "visible", False):
        headless = False
    elif getattr(args, "headless", None) is False:
        headless = False
    elif getattr(args, "headless", True):
        headless = True

    print(f"\n[DIR] Session: {args.session}")
    print(f"   Site: {site_name}")
    print(f"   Cookies: {len(cookies)}")
    print(f"   Source: {source_browser}")
    print(f"\n[NET] Target: {target_url}")
    print(f"   Browser: {browser_name}")

    port = int(getattr(args, "port", None) or 9222)
    try:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as _s:
            if _s.connect_ex(("127.0.0.1", port)) == 0:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as _s2:
                    _s2.bind(("127.0.0.1", 0))
                    port = _s2.getsockname()[1]
                print(f"   [WARN] Port busy - using {port}")
    except Exception:
        pass

    from tokenade.core.proxy.manager import ProxyManager
    proxy_mgr = ProxyManager(cli_proxy=getattr(args, "proxy", None))
    proxy = proxy_mgr.get_proxy(session_id=args.session, mode="sticky")
    upstream_proxy = proxy.server_url if proxy else None
    if upstream_proxy:
        print(f"   [PROXY] Upstream proxy: {upstream_proxy}")

    try:
        import tempfile
        profile_dir = tempfile.mkdtemp(prefix="tokenade_refresh_")

        if browser_name in ("cloak", "cloakbrowser"):
            from tokenade.core.browser.stealth.cloak import (
                CloakBrowserBackend,
                is_cloakbrowser_available,
            )
            print(f"\n[...] Launching cloak (headless={headless})...")
            backend = CloakBrowserBackend()
            if not backend.is_available():
                if is_cloakbrowser_available():
                    print("   [...] CloakBrowser binary missing - downloading...")
                    if not backend.ensure_ready():
                        print("[ERROR] CloakBrowser download failed. Retry: tokenade cloak install")
                        raise SystemExit(1)
                    print("   [OK] CloakBrowser installed - continuing...")
                else:
                    print(
                        "[ERROR] cloakbrowser package not installed. "
                        "Run: pip install cloakbrowser && tokenade cloak install"
                    )
                    raise SystemExit(1)
            proc = backend.serve_cdp(
                port=port,
                proxy=upstream_proxy,
                headless=headless,
                user_data_dir=profile_dir,
            )
            browser = BrowserProcess(
                process=proc,
                port=port,
                profile_dir=profile_dir,
                browser_name="cloak",
            )
        else:
            # Don't refuse refresh just because a desktop browser is open
            launcher = SystemBrowserLauncher()
            print(f"\n[...] Launching {browser_name} (headless={headless})...")
            browser = launcher.launch(
                browser=browser_name,
                visible=not headless,
                port=port,
                upstream_proxy=upstream_proxy,
                profile_dir=profile_dir,
            )
            port = getattr(browser, "port", port) or port

        print(f"   [OK] Browser ready (PID: {getattr(browser, 'pid', '?')}, CDP: {port})")

        import asyncio
        import websockets
        import urllib.request as _urllib_req

        _req = _urllib_req.Request(
            f"http://127.0.0.1:{port}/json/new?about:blank",
            method="PUT",
        )
        _resp = _urllib_req.urlopen(_req, timeout=10)
        _tab_info = json.loads(_resp.read().decode())
        _tab_ws_url = _tab_info.get("webSocketDebuggerUrl")
        if not _tab_ws_url:
            print("[ERROR] Failed to create tab")
            raise SystemExit(1)

        page_url_holder = [""]
        page_title_holder = [""]
        dom_hits_holder = [[]]
        dom_login_hits_holder = [[]]

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
            try:
                from tokenade.core.browser.cdp_connection import get_undetectable_stealth_script
                stealth_script = get_undetectable_stealth_script()
                try:
                    await cdp_cmd(tab_ws, "Page.enable")
                    await cdp_cmd(
                        tab_ws,
                        "Page.addScriptToEvaluateOnNewDocument",
                        {"source": stealth_script},
                    )
                except Exception as _stealth_err:
                    print(f"   [WARN] Stealth inject skipped ({_stealth_err}); continuing cookies")

                # Storage injection at document-start (before any navigate):
                # pages like discord.com delete window.localStorage after
                # boot, so post-load writes silently no-op. Seeding here is
                # the only programmatic path; the DOM login check afterwards
                # verifies it took effect.
                _storage = session.get("storage") if isinstance(session.get("storage"), dict) else {}
                _local_by_origin = _storage.get("local") if isinstance(_storage.get("local"), dict) else {}
                _sess_by_origin = _storage.get("session") if isinstance(_storage.get("session"), dict) else {}
                _seed_local = dict(session.get("local_storage") or {})
                _seed_session = dict(session.get("session_storage") or {})
                for _origin, _entries in _local_by_origin.items():
                    if isinstance(_entries, dict):
                        _seed_local.update(_entries)
                for _origin, _entries in _sess_by_origin.items():
                    if isinstance(_entries, dict):
                        _seed_session.update(_entries)
                if _seed_local or _seed_session:
                    try:
                        _seed_payload = json.dumps({"local": _seed_local, "session": _seed_session})
                        await cdp_cmd(tab_ws, "Page.addScriptToEvaluateOnNewDocument", {
                            "source": (
                                "(function(){try{var d=" + _seed_payload + ";"
                                "if(d.local&&typeof localStorage!=='undefined'){"
                                "Object.entries(d.local).forEach(function(e){"
                                "try{localStorage.setItem(e[0],typeof e[1]==='string'?e[1]:JSON.stringify(e[1]))}catch(_){}});}"
                                "if(d.session&&typeof sessionStorage!=='undefined'){"
                                "Object.entries(d.session).forEach(function(e){"
                                "try{sessionStorage.setItem(e[0],typeof e[1]==='string'?e[1]:JSON.stringify(e[1]))}catch(_){}});}"
                                "}catch(_){}})();"
                            ),
                        })
                        print(f"   [OK] Storage seed registered ({len(_seed_local)} local, {len(_seed_session)} session)")
                    except Exception as _seed_err:
                        print(f"   [WARN] Storage seed skipped ({_seed_err}); cookies only")

                print(f"\n Injecting {len(cookies)} cookies...")
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
                print("   [OK] Cookies injected")

                print(f"\n[NET] Navigating to: {target_url}")
                await cdp_cmd(tab_ws, "Page.navigate", {"url": target_url})

                wait_time = int(getattr(args, "wait", None) or 8)
                print(f"   [WAIT] Waiting {wait_time}s for session refresh...")
                await asyncio.sleep(wait_time)

                title_result = await cdp_cmd(
                    tab_ws, "Runtime.evaluate",
                    {"expression": "document.title", "returnByValue": True},
                )
                page_title_holder[0] = title_result.get("result", {}).get("value", "") or ""
                url_result = await cdp_cmd(
                    tab_ws, "Runtime.evaluate",
                    {"expression": "window.location.href", "returnByValue": True},
                )
                page_url_holder[0] = url_result.get("result", {}).get("value", "") or ""
                print(f"   [FILE] Page: {page_title_holder[0]}")
                print(f"   [URL] URL: {page_url_holder[0]}")

                async def _dom_hits(selectors):
                    hits = []
                    for sel in selectors:
                        try:
                            expr = "document.querySelector(%s) !== null" % json.dumps(sel)
                            r = await cdp_cmd(
                                tab_ws, "Runtime.evaluate",
                                {"expression": expr, "returnByValue": True},
                            )
                            if ((r.get("result") or {}).get("value")):
                                hits.append(sel)
                        except Exception:
                            # No signal (e.g. frame detached): never fail on it.
                            continue
                    return hits

                dom_hits_holder[0] = await _dom_hits(logout_selectors)
                if dom_hits_holder[0]:
                    print(f"   [WARN] Logout markers in DOM: {', '.join(dom_hits_holder[0])}")

                # SPAs often redirect to /login *after* the wait above
                # (Discord did at ~8-12s). Settle, then re-read URL + DOM;
                # either reading showing logged-out state fails the check.
                await asyncio.sleep(5)
                try:
                    url2 = await cdp_cmd(
                        tab_ws, "Runtime.evaluate",
                        {"expression": "window.location.href", "returnByValue": True},
                    )
                    page_url_holder[0] = (url2.get("result") or {}).get("value", "") or page_url_holder[0]
                    hits2 = await _dom_hits(logout_selectors)
                    for sel in hits2:
                        if sel not in dom_hits_holder[0]:
                            dom_hits_holder[0].append(sel)
                    if hits2:
                        print(f"   [WARN] Logout markers in DOM (settled): {', '.join(hits2)}")
                    if page_url_holder[0]:
                        print(f"   [URL] Settled URL: {page_url_holder[0]}")
                except Exception as _settle_err:
                    logger.debug("settle re-read failed: %s", _settle_err)

                # Positive proof: when the handler declares logged_in
                # selectors, absence of logout markers is not enough (SPA
                # shells render cleanly while logged out) — poll briefly
                # for authenticated content and fail without it.
                dom_login_hits_holder[0] = []
                if login_selectors and not dom_hits_holder[0]:
                    for _poll in range(3):
                        _pos = await _dom_hits(login_selectors)
                        if _pos:
                            dom_login_hits_holder[0] = _pos
                            print(f"   [OK] Authenticated markers: {', '.join(_pos)}")
                            break
                        await asyncio.sleep(4)
                    if not dom_login_hits_holder[0]:
                        print(
                            "   [WARN] No authenticated content "
                            f"({', '.join(login_selectors)}) after settle."
                        )

                print("\n[SYNC] Extracting refreshed cookies...")
                # Use the open tab WS - avoid nested asyncio.run(_extract_via_cdp)
                all_ck = await cdp_cmd(tab_ws, "Network.getAllCookies")
                raw_cookies = (all_ck or {}).get("cookies") or []
                fresh_cookies = []
                for c in raw_cookies:
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
                    fresh_cookies.append(cookie)

                fresh_ls, fresh_ss = {}, {}
                try:
                    ls_r = await cdp_cmd(
                        tab_ws, "Runtime.evaluate",
                        {
                            "expression": "JSON.stringify(Object.entries(localStorage||{}))",
                            "returnByValue": True,
                        },
                    )
                    ss_r = await cdp_cmd(
                        tab_ws, "Runtime.evaluate",
                        {
                            "expression": "JSON.stringify(Object.entries(sessionStorage||{}))",
                            "returnByValue": True,
                        },
                    )
                    import json as _json
                    ls_raw = (ls_r.get("result") or {}).get("value") or "[]"
                    ss_raw = (ss_r.get("result") or {}).get("value") or "[]"
                    for k, v in _json.loads(ls_raw):
                        fresh_ls[k] = v
                    for k, v in _json.loads(ss_raw):
                        fresh_ss[k] = v
                except Exception as _st_err:
                    print(f"   [WARN] storage extract skipped: {_st_err}")

                return fresh_cookies, fresh_ls, fresh_ss
            finally:
                try:
                    await tab_ws.close()
                except Exception:
                    pass

        fresh_cookies, fresh_ls, fresh_ss = asyncio.run(refresh())

        logged_in = _refresh_logged_in_heuristic(
            page_url_holder[0], page_title_holder[0], fresh_cookies or cookies
        )
        if logged_in and dom_hits_holder[0]:
            print(
                "\n[ERROR] Login check failed (logout markers in page DOM: "
                f"{', '.join(dom_hits_holder[0])})."
            )
            logged_in = False
        if logged_in and login_selectors and not dom_login_hits_holder[0]:
            print(
                "\n[ERROR] Login check failed (no authenticated content for "
                f"{', '.join(login_selectors)}; declare logged_in_selectors "
                "in the handler to prove login, or check the session)."
            )
            logged_in = False

        if not fresh_cookies:
            print("\n[ERROR] No cookies extracted after refresh. Session may be expired.")
            print("\n[ERROR] REFRESH FAIL (no cookies)")
            raise SystemExit(1)

        print(f"\n   [OK] Extracted {len(fresh_cookies)} fresh cookies")
        if fresh_ls:
            print(f"   [OK] Extracted {len(fresh_ls)} localStorage entries")
        if fresh_ss:
            print(f"   [OK] Extracted {len(fresh_ss)} sessionStorage entries")

        old_names = {c.get("name") for c in cookies}
        new_names = {c.get("name") for c in fresh_cookies}
        added = new_names - old_names
        removed = old_names - new_names
        kept = old_names & new_names

        print("\n[STATS] Cookie changes:")
        print(f"   Kept: {len(kept)}")
        if added:
            print(f"   Added: {len(added)} ({', '.join(sorted(str(a) for a in added if a)[:5])}{'...' if len(added) > 5 else ''})")
        if removed:
            print(f"   Removed: {len(removed)} ({', '.join(sorted(str(a) for a in removed if a)[:5])}{'...' if len(removed) > 5 else ''})")

        # Only overwrite session when still logged in
        if not logged_in:
            print("\n[ERROR] Login check failed (signed-out / login page).")
            print("   Session file left unchanged.")
            print("\n[ERROR] REFRESH FAIL (not logged in)")
            raise SystemExit(1)

        session["cookies"] = fresh_cookies
        if fresh_ls:
            session["local_storage"] = fresh_ls
        if fresh_ss:
            session["session_storage"] = fresh_ss
        if "metadata" not in session or not isinstance(session.get("metadata"), dict):
            session["metadata"] = {}
        session["metadata"]["cookie_count"] = len(fresh_cookies)
        session["metadata"]["local_storage_count"] = len(fresh_ls) if fresh_ls else 0
        session["metadata"]["session_storage_count"] = len(fresh_ss) if fresh_ss else 0
        from datetime import datetime, timezone
        session["metadata"]["last_refreshed"] = datetime.now(timezone.utc).isoformat()
        session["auth_status"] = "authenticated"

        out_path = output or _default_refresh_output(session_file)
        if not output:
            print(f"   [i] Source left unchanged; refreshed copy: {out_path}")
        packager.save(session, out_path)
        print(f"\n[SAVE] Session saved: {out_path}")
        print(f"   Cookies: {len(fresh_cookies)}")
        print("\n[OK] REFRESH PASS (logged in)")
        exit_ok = True

    except SystemExit:
        raise
    except Exception as e:
        print(f"\n[ERROR] Refresh failed: {e}")
        logger.error(f"Refresh failed: {e}", exc_info=True)
        print("\n[ERROR] REFRESH FAIL")
        exit_ok = False
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
            print("   [LOCK] Browser closed")
        # Remove our temp profile copy (never a real profile: always a
        # fresh mkdtemp dir). Guarded by basename so a programming error
        # can never wipe anything else.
        try:
            import shutil
            import tempfile as _tempfile

            _tmp_root = os.path.realpath(_tempfile.gettempdir())
            _prof = os.path.realpath(profile_dir) if profile_dir else ""
            if (
                _prof
                and os.path.basename(_prof).startswith("tokenade_refresh_")
                and os.path.dirname(_prof) == _tmp_root
                and os.path.isdir(_prof)
            ):
                shutil.rmtree(_prof, ignore_errors=True)
        except Exception as e:
            logger.debug("temp profile cleanup skipped: %s", e)

    raise SystemExit(0 if exit_ok else 1)


def cmd_accounts(args):
    """Multi-account orchestration - list, status, refresh multiple sessions."""
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
        print(f"[ERROR] Unknown action: {subcommand}")
        print("   Use: list, status, or refresh")


def _accounts_list(manager, args):
    """List all session files with metadata."""
    sessions = manager.list_sessions()

    if not sessions:
        print(f"\n[DIR] No .tokenade files found in {manager.sessions_dir}")
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
        print(f"\n[DIR] No .tokenade files found in {manager.sessions_dir}")
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
                        status = "[+] FRESH"
                        healthy += 1
                    elif age_hours < 24:
                        last_display = f"{int(age_hours)}h ago"
                        status = "[~] OK"
                        healthy += 1
                    elif age_hours < 72:
                        last_display = f"{int(age_hours / 24)}d ago"
                        status = " STALE"
                        expiring += 1
                    else:
                        last_display = f"{int(age_hours / 24)}d ago"
                        status = "[!] OLD"
                        expired += 1
                except (ValueError, TypeError):
                    last_display = last_refreshed
                    status = "? UNKNOWN"
            else:
                last_display = "never"
                status = " UNUSED"

            print(f"{s.site_name:<15} {len(cookies):<10} {auth_status:<12} {critical:<10} {last_display:<20} {status}")

        except Exception as e:
            print(f"{s.site_name:<15} {'?':<10} {'?':<12} {'?':<10} {'?':<20} [ERROR] ERROR: {e}")

    print(f"\n   [+] Fresh: {healthy}   Stale: {expiring}  [!] Old: {expired}")
    print(f"   [TIP] Run 'tokenade accounts refresh' to refresh stale sessions")


def _accounts_refresh(manager, args):
    """Refresh sessions - uses refresh-browser for each, with optional plugin support."""
    sessions = manager.list_sessions()

    if not sessions:
        print(f"\n[DIR] No .tokenade files found in {manager.sessions_dir}")
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
        print(f"   - {s.site_name} ({s.cookie_count} cookies) - {Path(s.path).name}")

    if not args.yes:
        response = input(f"\n[SYNC] Refresh all {len(sessions)} sessions? [y/N]: ").strip().lower()
        if response != "y":
            print("Cancelled")
            return

    # Refresh each session
    browser = args.browser or "cloak"
    headless = not args.visible
    wait = args.wait
    port = args.port

    # Load plugin if specified, or auto-discover unless --no-plugin
    plugin_name = getattr(args, "plugin", None)
    no_plugin = getattr(args, "no_plugin", False)
    plugin_args_list = getattr(args, "plugin_arg", None) or []
    plugin_creds = {}
    for item in plugin_args_list:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            plugin_creds[item[0]] = item[1]

    plugin_loader = None
    refresher = None
    _GENERIC_REFRESHERS = {
        "auto-refresh", "session-share", "session-encrypt", "proxy-rotate",
        "session-backup", "session-merge", "session-expiry-alert",
    }
    if not no_plugin:
        try:
            from tokenade.core.integration.plugin_loader import PluginLoader
            plugin_loader = PluginLoader()
            plugin_loader.load_all()
            if plugin_name:
                refresher = plugin_loader.get_refresher(plugin_name)
                if refresher:
                    print(f"\n[CDP] Using plugin: {plugin_name} v{getattr(refresher, 'version', '?')}")
                else:
                    print(f"\n[WARN] Plugin not found: {plugin_name}. Will auto-discover per session.")
            if not refresher and sessions:
                try:
                    from tokenade.core.importer.session_packager import SessionPackager
                    _pkgr = SessionPackager()
                    _first_session = _pkgr.load(sessions[0].path)
                    for name, cand in (plugin_loader.list_refreshers() or {}).items():
                        if name in _GENERIC_REFRESHERS:
                            continue
                        try:
                            if cand.can_refresh(_first_session):
                                refresher = cand
                                plugin_name = name
                                break
                        except Exception:
                            continue
                    if refresher:
                        print(f"\n[CDP] Auto-discovered refresher: {plugin_name} v{getattr(refresher, 'version', '?')}")
                except Exception as _ae:
                    logger.debug("Auto-discovery in accounts refresh failed: %s", _ae)
        except Exception as e:
            print(f"\n[WARN] Plugin error: {e}. Using browser refresh only.")

    succeeded = 0
    failed = 0
    skipped = 0

    for i, s in enumerate(sessions):
        print(f"\n{'-' * 60}")
        print(f"[{i + 1}/{len(sessions)}] Refreshing: {s.site_name} ({Path(s.path).name})")

        try:
            # Try plugin refresh first
            if refresher:
                try:
                    from tokenade.core.importer.session_packager import SessionPackager as _SP
                    packager = _SP()
                    session = packager.load(s.path)
                    if refresher.can_refresh(session):
                        print(f"   [CDP] Trying plugin {plugin_name}...")
                        raw = refresher.refresh(session, plugin_creds)
                        session = _unwrap_refresh_result(raw, session)
                        packager.save(session, s.path)
                        print(f"   [OK] Plugin refresh: {s.site_name}")
                        succeeded += 1
                        _run_post_refresh_plugins(plugin_loader, session)
                        continue
                    else:
                        print(f"   [WARN] Plugin can't handle this session, falling back to browser")
                except Exception as e:
                    print(f"   [WARN] Plugin refresh failed: {e}, falling back to browser")

            # Browser-based refresh via the single-session path (closes browser)
            from types import SimpleNamespace
            sub = SimpleNamespace(
                session=s.path,
                browser=browser,
                url=None,
                port=port + i,
                headless=headless,
                wait=wait,
                output=None,
                plugin=None,
                no_plugin=True,
                plugin_arg=[],
                proxy=getattr(args, "proxy", None),
            )
            try:
                cmd_refresh_browser(sub)
                succeeded += 1
            except SystemExit as se:
                if int(getattr(se, "code", 1) or 1) == 0:
                    succeeded += 1
                else:
                    failed += 1

        except Exception as e:
            print(f"   [ERROR] Failed: {e}")
            logger.error(f"Refresh failed for {s.path}: {e}", exc_info=True)
            failed += 1

    # Summary
    print(f"\n{'=' * 80}")
    print(f"REFRESH COMPLETE")
    print(f"{'=' * 80}")
    print(f"   [OK] Succeeded: {succeeded}")
    print(f"   [ERROR] Failed: {failed}")
    print(f"   [SKIP] Skipped: {skipped}")
    print(f"   Total: {len(sessions)}")


def _detect_url_from_cookies(cookies):
    """Auto-detect target URL from cookie domains."""
    domains = {str(c.get("domain", "")).lstrip(".").lower() for c in cookies if c.get("domain")}
    domains.discard("")

    # Prefer known product URLs (order matters)
    rules = [
        (("mail.google.com", "gmail.com"), "https://mail.google.com"),
        (("accounts.google.com", "google.com", "youtube.com"), "https://myaccount.google.com"),
        (("github.com",), "https://github.com"),
        (("twitter.com", "x.com"), "https://x.com"),
        (("linkedin.com",), "https://www.linkedin.com"),
        (("reddit.com",), "https://www.reddit.com"),
        (("facebook.com", "fb.com"), "https://www.facebook.com"),
        (("instagram.com",), "https://www.instagram.com"),
        (("slack.com",), "https://slack.com"),
        (("open.spotify.com", "spotify.com"), "https://open.spotify.com"),
        (("amazon.com", "amazon."), "https://www.amazon.com"),
        (("netflix.com",), "https://www.netflix.com"),
        (("discord.com", "discordapp.com"), "https://discord.com/channels/@me"),
    ]
    joined = " ".join(sorted(domains))
    for keys, url in rules:
        if any(k in joined or any(d == k or d.endswith("." + k) for d in domains) for k in keys):
            return url

    # Fallback: most specific (longest) domain
    ranked = sorted((d for d in domains if "." in d), key=len, reverse=True)
    for d in ranked:
        # skip pure trackers
        if any(x in d for x in ("doubleclick", "googleadservices", "analytics", "hotjar")):
            continue
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

        # Inject stealth (best-effort - some browsers hang on Page.enable)
        from tokenade.core.browser.cdp_connection import get_undetectable_stealth_script
        stealth_script = get_undetectable_stealth_script()
        try:
            await cdp_cmd(tab_ws, "Page.enable")
            await cdp_cmd(
                tab_ws,
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": stealth_script},
            )
        except Exception as _stealth_err:
            print(f"   [WARN] Stealth inject skipped ({_stealth_err}); continuing cookies")

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

# -- Daemon Commands ---------------------------------------------
