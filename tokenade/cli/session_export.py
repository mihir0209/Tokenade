"""Session export CLI command."""

import json
import logging
import os
from pathlib import Path

from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery
from tokenade.core.importer.cookie_extractor import CookieExtractor
from tokenade.core.importer.format_importer import FormatImporter
from tokenade.core.importer.local_storage_extractor import LocalStorageExtractor
from tokenade.core.importer.session_packager import SessionPackager

logger = logging.getLogger("tokenade")


def cmd_convert(args):
    """Convert a cookie file (JSON / Netscape / Playwright) into a .tokenade session."""
    input_path = getattr(args, "input", None) or getattr(args, "file", None)
    if not input_path:
        print("[ERROR] --input is required")
        raise SystemExit(2)

    out = getattr(args, "output", None)
    if not out:
        stem = Path(input_path).expanduser().stem or "converted"
        sessions_dir = Path.home() / ".tokenade" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        out = str(sessions_dir / f"{stem}.tokenade")

    fmt = getattr(args, "format", None) or "auto"
    encrypt = bool(getattr(args, "encrypt", False))
    # encrypt-password implies encrypt; SessionPackager.save uses at-rest config
    # for passwordless encrypt; password path is separate (export --encrypt-password).
    if getattr(args, "encrypt_password", None):
        encrypt = True
        os.environ.setdefault("TOKENADE_ENCRYPT_PASSWORD", args.encrypt_password)

    print(f"\n[CONVERT] {input_path}")
    print(f"   format: {fmt}")
    print(f"   output: {out}")

    domain = getattr(args, "domain", None) or ""
    result = FormatImporter.convert_file(
        input_path,
        out,
        format_hint=fmt,
        encrypt=encrypt,
        domain=domain,
    )
    if not result.get("success"):
        print(f"[ERROR] {result.get('error') or 'convert failed'}")
        raise SystemExit(1)

    print(
        f"   [OK] site={result.get('site_name')} cookies={result.get('cookie_count')}"
    )
    print(
        f"   [OK] format={result.get('format')} auth={result.get('auth_status')} "
        f"version={result.get('version') or '3.0'}"
    )
    if result.get("product_url"):
        print(f"   [OK] product_url={result.get('product_url')}")
    print(f"   [OK] saved: {result.get('output_path')}")
    return result


def _site_handler_metadata(
    site_handler, *, explicit_plugin=None, auto_discovered=False
):
    """Build reproducible export lineage metadata for a Site Handler."""
    if not site_handler:
        return None

    plugin_name = (
        explicit_plugin
        or getattr(site_handler, "name", None)
        or type(site_handler).__name__
    )
    metadata = {
        "plugin_name": plugin_name,
        "plugin_version": getattr(site_handler, "version", None) or "unknown",
        "handler_name": getattr(site_handler, "name", None) or plugin_name,
        "handler_class": type(site_handler).__name__,
        "auto_discovered": bool(auto_discovered),
    }
    try:
        metadata["export_domains"] = list(site_handler.get_export_domains() or [])
    except Exception:
        metadata["export_domains"] = []
    try:
        metadata["storage_origins"] = list(site_handler.get_storage_origins() or [])
    except Exception:
        metadata["storage_origins"] = []
    return metadata


def _snapshot_chromium_profile(profile_path):
    """Copy session-relevant profile files to a temp user-data tree.

    Layout out: ``<tmp>/User Data/<Profile>/{Network/Cookies*, Local
    Storage/leveldb, Session Storage, IndexedDB, Preferences}`` plus
    ``<tmp>/User Data/Local State``. Caches are skipped. Best-effort per
    file: a locked or missing file is skipped with a warning, never fatal.

    Returns the temp dir Path (caller must delete it when done).
    """
    import shutil
    import tempfile
    from pathlib import Path as _Path

    profile_path = _Path(str(profile_path))
    user_data = profile_path.parent
    tmp = _Path(tempfile.mkdtemp(prefix="tokenade_profile_snapshot_"))
    dest_profile = tmp / "User Data" / profile_path.name

    def _copy_glob(src_dir, pattern, dest_sub):
        try:
            matches = sorted(_Path(src_dir).glob(pattern))
        except Exception:
            return 0
        count = 0
        for src in matches:
            if not src.is_file():
                continue
            try:
                dst = dest_profile / dest_sub / src.name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                count += 1
            except Exception as exc:
                logger.warning(f"Snapshot skipped {src}: {exc}")
        return count

    def _copy_tree(src_dir, dest_sub):
        try:
            src = _Path(src_dir)
            if not src.is_dir():
                return 0
            count = 0
            for src_file in sorted(src.rglob("*")):
                if not src_file.is_file():
                    continue
                try:
                    rel = src_file.relative_to(src)
                    dst = dest_profile / dest_sub / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dst)
                    count += 1
                except Exception as exc:
                    logger.warning(f"Snapshot skipped {src_file}: {exc}")
            return count
        except Exception:
            return 0

    total = 0
    total += _copy_glob(str(profile_path / "Network"), "Cookies*", "Network")
    total += _copy_glob(str(profile_path), "Cookies*", "")
    total += _copy_tree(str(profile_path / "Local Storage" / "leveldb"), "Local Storage/leveldb")
    total += _copy_tree(str(profile_path / "Session Storage"), "Session Storage")
    total += _copy_tree(str(profile_path / "IndexedDB"), "IndexedDB")
    for single in ("Preferences", "Secure Preferences"):
        src = profile_path / single
        if src.is_file():
            try:
                dst = dest_profile / single
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                total += 1
            except Exception as exc:
                logger.warning(f"Snapshot skipped {src}: {exc}")
    try:
        src = user_data / "Local State"
        if src.is_file():
            shutil.copy2(src, tmp / "User Data" / "Local State")
            total += 1
    except Exception as exc:
        logger.warning(f"Snapshot skipped Local State: {exc}")

    print(f"   [DIR] Snapshotted {total} profile file(s) (caches skipped)")
    return tmp


def _backup_donor_profile(profile_path, browser_name):
    """Back up session-critical donor files before any destructive step.

    Copies ``Cookies*`` and ``Local State`` to
    ``~/.tokenade/profile-backups/<browser>-<timestamp>/``. Automation must
    never be the reason a donor profile loses data: Chromium prunes cookie
    rows it cannot decrypt, so a relaunch against live files can destroy
    sessions (observed on Windows Edge). Best-effort; returns the backup
    dir Path or None.
    """
    import time as _time
    from pathlib import Path as _Path

    from tokenade.core.utils.paths import tokenade_home

    try:
        profile_path = _Path(str(profile_path))
        stamp = _time.strftime("%Y%m%d-%H%M%S")
        dest = _Path(str(tokenade_home())) / ".tokenade" / "profile-backups" / f"{browser_name}-{stamp}"
        dest.mkdir(parents=True, exist_ok=True)
        import shutil as _shutil

        copied = 0
        for pattern in ("Network/Cookies*", "Cookies*"):
            for src in sorted(profile_path.glob(pattern)):
                if src.is_file():
                    _shutil.copy2(src, dest / src.name)
                    copied += 1
        src_state = profile_path.parent / "Local State"
        if src_state.is_file():
            _shutil.copy2(src_state, dest / "Local State")
            copied += 1
        if copied:
            print(f"   [DIR] Donor backup: {dest} ({copied} file(s))")
            return dest
    except Exception as exc:
        logger.warning(f"Donor backup failed: {exc}")
    return None


def _is_live_user_data_dir(launch_user_data_dir, real_profile):
    """True if a launch dir resolves inside the real browser data tree.

    Launching automation there risks mutating the donor profile (cookie
    pruning, lock fights). Callers must refuse and use a snapshot instead.
    """
    try:
        from pathlib import Path as _Path

        if not launch_user_data_dir or not real_profile:
            return False
        launch = _Path(str(launch_user_data_dir)).resolve()
        real_ud = _Path(str(real_profile)).resolve()
        if real_ud.is_file() or real_ud.suffix:
            real_ud = real_ud.parent
        if real_ud.name in ("Default",) or real_ud.name.startswith("Profile "):
            real_ud = real_ud.parent
        return launch == real_ud or real_ud in launch.parents
    except Exception:
        return False


def _merge_live_storage(local_storage, session_storage, storage,
                        live_local_storage, live_session_storage,
                        live_storage):
    """Merge live-extracted values (CDP / extension bridge) into file-based
    results. Live values take precedence: they are fresher than profile
    files on disk. Mutates and returns the ``(local, session, storage)``
    triple containers."""
    for _k, _v in (live_local_storage or {}).items():
        local_storage.setdefault(_k, _v)
    for _k, _v in (live_session_storage or {}).items():
        session_storage.setdefault(_k, _v)
    for _origin, _entries in (live_storage or {}).get("local", {}).items():
        if _entries:
            storage["local"].setdefault(_origin, dict(_entries))
    for _origin, _entries in (live_storage or {}).get("session", {}).items():
        if _entries:
            storage["session"].setdefault(_origin, dict(_entries))
    return local_storage, session_storage, storage


def cmd_export(args):
    """Export session from existing browser to .tokenade file."""
    from tokenade.cli.session import _extract_via_cdp

    if not getattr(args, "encrypt_password", None):
        args.encrypt_password = os.environ.get("TOKENADE_ENCRYPT_PASSWORD")

    print("\n" + "=" * 80)
    print("TOKENADE - Session Export")
    print("=" * 80)

    # Pre-initialized so the live-value snapshot below never hits
    # UnboundLocalError on paths that assign these names later.
    local_storage = {}
    session_storage = {}
    storage = {"local": {}, "session": {}}

    if args.list_profiles:
        print("\n[SEARCH] Discovering browser profiles...")
        discovery = BrowserProfileDiscovery()
        profiles = discovery.refresh_cache()
        total_profiles = sum(
            len(browser_profiles) for browser_profiles in profiles.values()
        )

        if total_profiles == 0:
            print("   [ERROR] No browser profiles found")
            return

        print(f"\n[DIR] Found {total_profiles} profile(s):\n")
        for browser_name, browser_profiles in profiles.items():
            for p in browser_profiles:
                print(f"   Browser: {p.browser}")
                print(f"   Profile: {p.name}")
                print(f"   Path: {p.path}")
                print(f"   Last Used: {p.last_used or 'unknown'}")
                print()
        return

    if getattr(args, "list_handlers", False):
        from tokenade.core.importer.plugin_export import PluginExporter

        exporter = PluginExporter()
        handlers = exporter.list_handlers()
        if not handlers:
            print("   No site handler plugins installed.")
            print("   Install one: tokenade plugin install generic-handler")
        else:
            print(f"\n[CDP] Available site handlers ({len(handlers)}):\n")
            for h in handlers:
                print(f"   {h['name']} v{h['version']} - {h['description']}")
        return

    browser_path = args.browser_path
    browser_name = args.browser_name or "unknown"
    cdp_port = getattr(args, "cdp_port", None)

    from tokenade.core.config import load_config

    config = load_config()
    if not browser_name or browser_name == "unknown":
        browser_name = config.get("default_browser") or browser_name
    if not args.profile:
        args.profile = config.get("default_profile")

    # CDP export talks to a running browser - no local profile required
    if not cdp_port:
        if not browser_path and browser_name:
            discovery = BrowserProfileDiscovery()
            matching = discovery.discover_browser(browser_name)
            if args.profile:
                wanted = args.profile.lower()
                matching = [
                    p
                    for p in matching
                    if p.name.lower() == wanted
                    or os.path.basename(str(p.path)).lower() == wanted
                ]
            if matching:
                browser_path = str(matching[0].path)
                print(f"[DIR] Using profile: {matching[0].name}")
            else:
                print(f"[ERROR] No profile found for '{browser_name}'")
                print(
                    "   Run 'tokenade export --list-profiles' to see available profiles"
                )
                if args.profile:
                    print(
                        f"   Profile '{args.profile}' not found - check spelling and try again"
                    )
                return

        if not browser_path:
            print("[ERROR] No browser path specified.")
            print(
                "   Use --browser-name (e.g., --browser-name firefox) or --browser-path /path/to/profile"
            )
            print("   Or use --cdp-port N to extract from a running browser")
            print(
                "   Run 'tokenade export --list-profiles' to discover available profiles"
            )
            return

    if cdp_port:
        launched_browser = None
        _snapshot_dir = None
        import urllib.request as _urllib_req

        try:
            _urllib_req.urlopen(f"http://127.0.0.1:{cdp_port}/json/version", timeout=2)
            print(f"\n[CDP] Connected to existing browser on port {cdp_port}")
        except Exception:
            import subprocess
            import platform

            _exe_names = {
                "chrome": "chrome",
                "chromium": "chromium",
                "edge": "msedge",
                "brave": "brave",
                "firefox": "firefox",
                "vivaldi": "vivaldi",
                "opera": "opera",
            }
            _exe = _exe_names.get((browser_name or "").lower(), browser_name)
            _ps_cmd = (
                ["pgrep", "-c", browser_name]
                if platform.system() != "Windows"
                else ["tasklist", "/fi", f"imagename eq {_exe}.exe"]
            )
            _browser_running = False
            try:
                _running = subprocess.run(
                    _ps_cmd, capture_output=True, text=True, timeout=3
                )
                if platform.system() != "Windows":
                    _browser_running = (
                        _running.returncode == 0
                        and _running.stdout.strip().isdigit()
                        and int(_running.stdout.strip()) > 0
                    )
                else:
                    _browser_running = _exe.lower() in _running.stdout.lower()
            except Exception:
                pass

            if _browser_running and not getattr(args, "cdp_launch", False):
                print(
                    f"   [WARN] {browser_name} is already running. Profile is locked."
                )
                print(f"   Close all {browser_name} windows first, then retry.")
                print(
                    f"   Or start {browser_name} with: {browser_name} --remote-debugging-port={cdp_port}"
                )
                print(
                    "   Or pass --cdp-launch to quit it and relaunch with remote "
                    "debugging automatically."
                )
                return

            if _browser_running:
                print(
                    f"\n[CDP] --cdp-launch: quitting residual {browser_name} processes..."
                )
                _quit_cmd = (
                    ["pkill", "-x", _exe]
                    if platform.system() != "Windows"
                    else ["taskkill", "/F", "/IM", f"{_exe}.exe"]
                )
                try:
                    subprocess.run(_quit_cmd, capture_output=True, timeout=15)
                except Exception as exc:
                    print(f"   [WARN] Could not quit {browser_name}: {exc}")
                import time as _quit_wait

                for _ in range(15):
                    try:
                        _check = subprocess.run(
                            _ps_cmd, capture_output=True, text=True, timeout=3
                        )
                        if platform.system() != "Windows":
                            _gone = not (
                                _check.returncode == 0
                                and _check.stdout.strip().isdigit()
                                and int(_check.stdout.strip()) > 0
                            )
                        else:
                            _gone = _exe.lower() not in _check.stdout.lower()
                        if _gone:
                            break
                    except Exception:
                        break
                    _quit_wait.sleep(1)
                print(f"   [OK] {browser_name} quit; relaunching with remote debugging.")
                # Back up AFTER quit (files are unlocked now) and BEFORE any
                # automation launch: if a relaunch ever mutates the donor,
                # Cookies/Local State are restorable.
                try:
                    from tokenade.core.importer.browser_discovery import (
                        BrowserProfileDiscovery as _BPD2,
                    )

                    _pre2 = _BPD2().discover_browser(browser_name)
                    if _pre2:
                        _backup_donor_profile(str(_pre2[0].path), browser_name)
                except Exception as exc:
                    logger.warning(f"Donor backup skipped: {exc}")

            print(f"\n[...] Launching {browser_name} with CDP on port {cdp_port}...")
            from tokenade.core.browser.undetectable import SystemBrowserLauncher

            launcher = SystemBrowserLauncher()
            try:
                real_profile = launcher._get_default_profile_dir(browser_name)
                try:
                    from tokenade.core.importer.browser_discovery import (
                        BrowserProfileDiscovery as _BPD3,
                    )

                    _found = _BPD3().discover_browser(
                        browser_name
                    )
                    if _found:
                        real_profile = str(_found[0].path)
                except Exception:
                    pass
                from pathlib import Path as _Path

                _profile_path = _Path(str(real_profile)) if real_profile else None
                _is_chromium = (browser_name or "").lower() in (
                    "chrome", "chromium", "edge", "msedge",
                    "brave", "vivaldi", "opera", "arc",
                )
                _launch_kwargs = {
                    "browser": browser_name,
                    "visible": True,
                    "port": cdp_port,
                    "profile_dir": real_profile,
                }
                if (
                    _is_chromium
                    and _profile_path is not None
                    and (
                        _profile_path.name == "Default"
                        or _profile_path.name.startswith("Profile ")
                    )
                ):
                    # Launch a SNAPSHOT, not the live profile: Edge refuses
                    # --remote-debugging-port on its default data directory
                    # ("requires a non-default data directory"), and automation
                    # must never mutate the user's real profile. Cookies,
                    # storage, and prefs are copied; caches are skipped.
                    # The user may reopen their browser as soon as the
                    # snapshot below finishes.
                    _snapshot_dir = _snapshot_chromium_profile(_profile_path)
                    print(f"   [DIR] Snapshot ready: {_snapshot_dir}")
                    print("   [OK] You can reopen your browser now.")
                    _launch_kwargs["user_data_dir"] = str(_snapshot_dir / "User Data")
                    _launch_kwargs["extra_args"] = [
                        f"--profile-directory={_profile_path.name}"
                    ]
                    _launch_kwargs["profile_dir"] = str(_snapshot_dir)
                # Hard refusal: automation must never launch against the live
                # user-data tree (cookie pruning / lock fights destroy donor
                # sessions). Snapshot above is the only allowed Chromium path.
                _effective_ud = _launch_kwargs.get(
                    "user_data_dir", _launch_kwargs.get("profile_dir")
                )
                if _is_chromium and _is_live_user_data_dir(
                    _effective_ud, str(_profile_path) if _profile_path else None
                ):
                    print(
                        "[ERROR] Refusing to launch automation against the live "
                        "browser profile (donor safety)."
                    )
                    import shutil as _shutil2

                    try:
                        if _snapshot_dir is not None:
                            _shutil2.rmtree(_snapshot_dir, ignore_errors=True)
                    except Exception:
                        pass
                    return
                try:
                    launched_browser = launcher.launch(**_launch_kwargs)
                except RuntimeError as e:
                    print(f"[ERROR] Failed to launch browser: {e}")
                    import shutil as _shutil3

                    try:
                        if _snapshot_dir is not None:
                            _shutil3.rmtree(_snapshot_dir, ignore_errors=True)
                    except Exception:
                        pass
                    _snapshot_dir = None
                    return
                print(f"   [OK] Browser launched (PID: {launched_browser.pid})")
                import time as _time

                _time.sleep(3)
            except Exception as e:
                print(f"[ERROR] CDP launch preparation failed: {e}")
                import shutil as _shutil4

                try:
                    if _snapshot_dir is not None:
                        _shutil4.rmtree(_snapshot_dir, ignore_errors=True)
                except Exception:
                    pass
                return

        cdp_domains = getattr(args, "domains", None)
        if not cdp_domains and getattr(args, "plugin", None):
            # --plugin without --domains: use the handler's export domains
            # so CDP warms/reads the right origins (and the cookie filter
            # below matches). Without this the store is never warmed and
            # cold launches yield "No cookies extracted via CDP".
            try:
                from tokenade.core.importer.plugin_export import PluginExporter

                _pe = PluginExporter()
                _pe._load_handlers()
                _ph = _pe.get_handler(args.plugin)
                _pd = list((_ph.get_export_domains() or []) if _ph else [])
                if _pd:
                    cdp_domains = ",".join(_pd)
                    print(f"   [HIT] Plugin export domains: {', '.join(_pd)}")
            except Exception as e:
                logger.debug(f"plugin domain pre-resolution failed: {e}")
        if getattr(args, "via_extension", False):
            from tokenade.core.importer.extension_bridge import (
                ExtensionBridgeMissing,
                export_via_bridge_sync,
            )

            _bridge_domains = [d for d in (cdp_domains or "").split(",") if d.strip()]
            if not _bridge_domains:
                print(
                    "[ERROR] --via-extension needs --domains (or --plugin "
                    "with export domains), e.g. --domains discord.com"
                )
                return
            try:
                session_state = export_via_bridge_sync(cdp_port, _bridge_domains)
            except ExtensionBridgeMissing as e:
                print(f"[ERROR] {e}")
                return
            except Exception as e:
                print(f"[ERROR] Extension bridge export failed: {e}")
                return
            print("   [OK] Read via extension bridge (in-page context)")
            cookies = session_state["cookies"]
            local_storage = session_state.get("local_storage", {})
            session_storage = session_state.get("session_storage", {})
            _bridge_storage = session_state.get("storage") or {}
            if _bridge_storage.get("local") or _bridge_storage.get("session"):
                storage = {
                    "local": dict(_bridge_storage.get("local", {})),
                    "session": dict(_bridge_storage.get("session", {})),
                }
        else:
            session_state = _extract_via_cdp(
                cdp_port, domain_filter=cdp_domains
            )
            cookies = session_state["cookies"]
            local_storage = session_state.get("local_storage", {})
            session_storage = session_state.get("session_storage", {})

        if launched_browser:
            try:
                launched_browser.close()
            except Exception:
                pass
            print("   [OK] Relaunched browser closed — reopen it normally.")
        if _snapshot_dir is not None:
            import shutil as _shutil

            try:
                _shutil.rmtree(_snapshot_dir, ignore_errors=True)
            except Exception:
                pass

        _via = "extension bridge" if getattr(args, "via_extension", False) else "CDP"
        if not cookies and not local_storage and not session_storage:
            print(f"[ERROR] No cookies or storage extracted via {_via}")
            return
        if cookies:
            print(f"   [OK] Extracted {len(cookies)} cookies via {_via}")
        if local_storage:
            print(f"   [OK] Extracted {len(local_storage)} localStorage entries")
        if session_storage:
            print(f"   [OK] Extracted {len(session_storage)} sessionStorage entries")
        if getattr(args, "full", False) and not local_storage and not session_storage:
            # Page JS contexts can hide Web Storage from CDP (observed:
            # localStorage undefined in-page on discord.com while the tab
            # is logged in). Stay loud instead of shipping a hollow jar.
            print(
                f"   [WARN] --full requested but no Web Storage captured via {_via} — "
                "the page context may hide storage from automation."
            )
            if not getattr(args, "via_extension", False):
                print(
                    "   [TIP] Retry with --via-extension (in-page context) for "
                    "storage-backed sites (Discord, Telegram)."
                )
    else:
        print(f"\n Extracting cookies from: {browser_path}")
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

    plugin_name = getattr(args, "plugin", None)
    use_plugin = not getattr(args, "no_plugin", False)
    site_handler = None
    site_handler_auto_discovered = False

    if plugin_name or use_plugin:
        from tokenade.core.importer.plugin_export import PluginExporter

        exporter = PluginExporter()
        exporter._load_handlers()

        if plugin_name:
            site_handler = exporter.get_handler(plugin_name)
            if site_handler:
                print(
                    f"   [CDP] Using plugin: {plugin_name} (overrides default export worker)"
                )
                if hasattr(site_handler, "get_site_config"):
                    try:
                        sc = site_handler.get_site_config() or {}
                        if sc.get("domains"):
                            print(
                                f"   [FILE] site_config.json: {sc.get('name', '?')} ({len(sc.get('domains') or [])} domains)"
                            )
                    except Exception:
                        pass
            else:
                print(
                    f"   [WARN] Plugin not found: {plugin_name} - falling back to default extraction"
                )
                print(f"   ->  Install: tokenade plugin install {plugin_name}")
        elif domain_filter:
            site_handler = exporter.find_handler(domain_filter)
            if site_handler:
                site_handler_auto_discovered = True
                print(
                    f"   [CDP] Auto-discovered handler: {getattr(site_handler, 'name', '?')} (overrides default)"
                )
            else:
                print("   [i] No handler found for domains, using default extraction")
                # Consult the unified recommend() engine for a smarter hint.
                try:
                    from tokenade.core.recommend import recommend

                    rec = recommend(domains=domain_filter)
                    if rec.plugin:
                        print(f"   [TIP] Suggestion: --plugin {rec.plugin}")
                except Exception:
                    pass
        else:
            print(
                "   [i] No --domains / --plugin: exporting unfiltered cookies from the profile."
            )
            print("   [TIP] Prefer a site plugin (domains from site_config.json):")
            print("      tokenade export --list-handlers")
            print(
                "      tokenade recommend --url https://your-site.com   # then --plugin <suggested>"
            )

        if (
            site_handler
            and not domain_filter
            and hasattr(site_handler, "get_export_domains")
        ):
            try:
                plugin_domains = site_handler.get_export_domains() or []
                if plugin_domains:
                    domain_filter = list(plugin_domains)
                    print(f"   [HIT] Plugin export domains: {', '.join(domain_filter)}")
            except Exception as e:
                logger.debug(f"get_export_domains failed: {e}")

    site_config = None
    if args.site_config:
        with open(args.site_config) as f:
            site_config = json.load(f)

    def _progress(current, total, stage):
        if stage == "copying_database":
            print("   [LIST] Copying cookie database...")
        elif stage == "extracting_cookies":
            if total > 0:
                pct = int((current / total) * 100)
                print(
                    f"\r   [WAIT] Extracting cookies... {current}/{total} ({pct}%)",
                    end="",
                    flush=True,
                )
        elif stage == "complete":
            print(
                "\r   [OK] Cookie extraction complete                    ", flush=True
            )

    if (
        not cdp_port
        and not args.file_path
        and browser_name
        and browser_name != "unknown"
    ):
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
                _r = _sp.run(
                    ["pgrep", "-x", _pat], capture_output=True, text=True, timeout=3
                )
                if _r.returncode != 0 and _pat == "brave":
                    _r = _sp.run(
                        ["pgrep", "-x", "brave-browser"],
                        capture_output=True,
                        text=True,
                        timeout=3,
                    )
                if _r.returncode == 0 and (_r.stdout or "").strip():
                    print(
                        f"   [WARN] {browser_name} appears to be running - cookie DB may be locked."
                    )
                    print(
                        f"   ->  Fully quit {browser_name} (check system tray / process list), then re-run export."
                    )
            else:
                _r = _sp.run(
                    ["tasklist", "/fi", f"imagename eq {browser_name}.exe"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if browser_name.lower() in (_r.stdout or "").lower():
                    print(
                        f"   [WARN] {browser_name} appears to be running - cookie DB may be locked."
                    )
                    print(
                        f"   ->  Fully quit {browser_name} (Task Manager), then re-run export."
                    )
        except Exception:
            pass

    try:
        if cdp_port:
            pass
        elif args.file_path:
            cookies = extractor.extract_from_file(
                args.file_path, args.format or "netscape"
            )
        else:
            cookies = extractor.extract(site_filter=None, progress_callback=_progress)
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)
        err = str(e).lower()
        print("[ERROR] Extraction failed")
        if "locked" in err or "busy" in err or "sqlite" in err:
            print(
                "   Cookie database is locked (browser still open or crashed with lock held)."
            )
            print(
                f"   ->  Fully quit {browser_name}, wait a few seconds, then retry export."
            )
            print("   ->  On Linux/macOS: ensure no leftover browser processes remain.")
        else:
            print(
                "   Check browser profile is accessible and you have read permission."
            )
            print(f"   Detail: {e}")
        raise SystemExit(1) from e

    print(f"   [STATS] Total cookies: {len(cookies)}")

    if cookies and not any(c.get("value") for c in cookies):
        # Names without values: Chromium's DPAPI key would not decrypt.
        # On Windows this is almost always app-bound encryption (Chrome 127+).
        app_bound = False
        try:
            import json as _json

            local_state = Path(str(browser_path)).parent / "Local State"
            if local_state.is_file():
                app_bound = "app_bound_encrypted_key" in _json.loads(
                    local_state.read_text(encoding="utf-8")
                ).get("os_crypt", {})
        except Exception:
            pass
        print("   [WARN] All cookie values are EMPTY — names only, no session material.")
        if app_bound:
            print(
                "   [WARN] Donor uses app-bound encryption (Chrome 127+ on Windows): "
                "third-party SQLite reads cannot decrypt values."
            )
        else:
            print(
                "   [WARN] Cookie values would not decrypt (wrong profile key or "
                "locked/rotated DPAPI state)."
            )
        print("   [TIP] Use the browser extension (live cookie API, no decryption needed)")
        print("         or --cdp-port export from a running browser, or a Firefox donor.")

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
        print(
            f"   [HIT] Filtered to {len(cookies)} cookies for domains: {', '.join(domain_filter)}"
        )

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
            print(
                f"   [HIT] Filtered to {len(cookies)} cookies for domains: {', '.join(domains)}"
            )

    # Live extraction (CDP / extension bridge) already produced values
    # above; file-based extraction below must merge into them, never
    # replace them (it previously reset these to {} and silently dropped
    # everything CDP had captured).
    live_local_storage = dict(local_storage or {})
    live_session_storage = dict(session_storage or {})
    live_storage = {
        "local": dict((storage or {}).get("local", {})),
        "session": dict((storage or {}).get("session", {})),
    }
    local_storage = {}
    session_storage = {}
    storage = {"local": {}, "session": {}}
    handler_has_storage = bool(
        site_handler
        and hasattr(site_handler, "get_storage_origins")
        and site_handler.get_storage_origins()
    )
    do_extract_storage = (
        args.extract_local_storage
        or getattr(args, "full", False)
        or handler_has_storage
    )

    if do_extract_storage and browser_path:
        print(f"\n[SAVE] Extracting localStorage from: {browser_path}")
        ls_extractor = LocalStorageExtractor(browser_path, browser=browser_name)

        try:
            handler_origins = []
            if site_handler and hasattr(site_handler, "get_storage_origins"):
                handler_origins = list(site_handler.get_storage_origins() or [])

            if handler_origins:
                for origin in handler_origins:
                    origin_data = ls_extractor.extract(origin_filter=origin)
                    if origin_data:
                        storage["local"][origin] = origin_data
                local_storage = {
                    key: value
                    for entries in storage["local"].values()
                    for key, value in entries.items()
                }
                print(
                    f"   [STATS] Extracted {len(local_storage)} localStorage entries for plugin origins"
                )
                if not local_storage:
                    print(
                        "   [WARN] Handler declares storage origins but none were captured — "
                        "the donor profile may be logged out of those origins."
                    )
            elif args.local_storage_origin:
                local_storage = ls_extractor.extract(
                    origin_filter=args.local_storage_origin
                )
                storage["local"][args.local_storage_origin] = local_storage
                print(
                    f"   [STATS] localStorage entries for {args.local_storage_origin}: {len(local_storage)}"
                )
            else:
                origins = ls_extractor.list_origins()
                if origins:
                    print(f"   [LIST] Found {len(origins)} origin(s) with localStorage")
                    for origin in origins:
                        try:
                            origin_data = ls_extractor.extract(origin_filter=origin)
                            local_storage.update(origin_data)
                            storage["local"][origin] = origin_data
                        except Exception:
                            pass
                    print(
                        f"   [STATS] Extracted {len(local_storage)} localStorage entries total"
                    )
                else:
                    print("   [WARN] No localStorage data found")
        except Exception as e:
            logger.warning(f"localStorage extraction failed: {e}", exc_info=True)
            print("   [WARN] localStorage extraction skipped - browser may be running")
    else:
        try:
            ls_extractor = LocalStorageExtractor(browser_path, browser=browser_name)
            origins = ls_extractor.list_origins()
            if origins and cookies:
                cookie_domains = {c.get("domain", "").lstrip(".") for c in cookies}
                matching_origins = [
                    o for o in origins if any(d in o for d in cookie_domains)
                ]
                if matching_origins:
                    print(
                        f"\n[SAVE] Found localStorage for {len(matching_origins)} cookie domain(s): {', '.join(matching_origins)}"
                    )
                    print("   [TIP] Re-run with --extract-local-storage to include it")
        except Exception:
            pass

    # Merge back live-extracted values (CDP / extension bridge take
    # precedence: they are fresher than profile files on disk).
    _merge_live_storage(
        local_storage, session_storage, storage,
        live_local_storage, live_session_storage, live_storage,
    )
    if live_local_storage or live_session_storage:
        print(
            f"   [OK] Kept {len(live_local_storage)} local + "
            f"{len(live_session_storage)} session live entries"
        )

    profile_data = {}
    if site_handler and hasattr(site_handler, "export_profile_data") and browser_path:
        print("\n[SAVE] Exporting site-specific browser storage...")
        profile_result = site_handler.export_profile_data(
            str(browser_path), browser_name
        )
        if not profile_result.success:
            print(
                f"[ERROR] Site-specific storage export failed: {profile_result.error}"
            )
            raise SystemExit(1)
        profile_data = profile_result.data or {}
        if profile_data:
            artifact_count = profile_data.get("file_count", 0)
            artifact_bytes = profile_data.get("uncompressed_size", 0)
            print(
                f"   [OK] Included {artifact_count} profile files ({artifact_bytes} bytes)"
            )
        for warning in profile_result.warnings:
            print(f"   [WARN] {warning}")

    if (
        not cookies
        and not local_storage
        and not session_storage
        and not storage["local"]
        and not profile_data
    ):
        print(
            "[ERROR] No cookies, Web Storage, or site-specific browser storage to export"
        )
        return

    packager = SessionPackager()

    export_metadata = {}
    if site_handler:
        export_metadata.update(
            {
                "extraction_method": "site_handler",
                "site_handler": _site_handler_metadata(
                    site_handler,
                    explicit_plugin=plugin_name,
                    auto_discovered=site_handler_auto_discovered,
                ),
            }
        )

    if getattr(args, "stamp_network", False):
        from tokenade.core.network.source_context import (
            SourceNetworkError,
            capture_source_network,
        )

        try:
            export_metadata["source_network"] = capture_source_network(
                include_source_ip=bool(getattr(args, "include_source_ip", False))
            )
            print("   [NET] Source network stamp captured")
        except SourceNetworkError as e:
            print(f"[ERROR] Source network stamp failed: {e}")
            raise SystemExit(1) from e

    proxy_plugin = getattr(args, "proxy_plugin", None)
    if proxy_plugin:
        export_metadata["proxy_provider_request"] = {
            "plugin_name": proxy_plugin,
            "export_traffic_routed": False,
            "note": "Provider metadata only; export traffic is not routed through this proxy plugin.",
        }
        print(
            f"   [CDP] Proxy provider metadata recorded: {proxy_plugin} (export traffic not routed)"
        )

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
        storage=storage if storage["local"] or storage["session"] else None,
        extra_cookies=extra_cookies if extra_cookies else None,
        metadata=export_metadata or None,
    )

    if profile_data:
        from tokenade import __version__
        from tokenade.core.artifacts import ProfileArtifactManager

        package.setdefault("profile_artifacts", []).append(
            ProfileArtifactManager.package_plugin_payload(
                site_handler.name,
                getattr(site_handler, "version", None) or "0",
                profile_data,
                tokenade_requirement=f">={__version__}",
            )
        )
        package.setdefault("metadata", {}).setdefault("required_plugins", []).append(
            {
                "name": site_handler.name,
                "min_version": getattr(site_handler, "version", None) or "0",
                "reason": "site-specific browser storage",
                "required_at": "launch",
                **(
                    {"access_mode": profile_data["access_mode"]}
                    if profile_data.get("access_mode")
                    else {}
                ),
            }
        )

    if site_handler and package.get("site_name") == "unknown":
        handler_site_name = None
        if hasattr(site_handler, "get_site_config"):
            try:
                handler_site_name = (site_handler.get_site_config() or {}).get("name")
            except Exception:
                handler_site_name = None
        if not handler_site_name:
            handler_site_name = getattr(site_handler, "site_name", None)
        if not handler_site_name:
            handler_site_name = (getattr(site_handler, "name", "") or "").removesuffix(
                "-handler"
            )
        if handler_site_name:
            package["site_name"] = handler_site_name

    site_name = package.get("site_name", "session")
    output = args.output or f"{site_name}_session"

    encrypt_password = getattr(args, "encrypt_password", None)
    if encrypt_password:
        saved_path = packager.save(package, output, encrypt=True)
        from tokenade.core.crypto.encryptor import SessionEncryptor

        encryptor = SessionEncryptor()
        encryptor.encrypt_file(saved_path, saved_path + ".enc", encrypt_password)
        os.rename(saved_path + ".enc", saved_path)
        print(f"\n[LOCK] Encrypted and exported: {saved_path}")
    else:
        saved_path = packager.save(package, output)
        print(f"\n[SAVE] Exported: {saved_path}")

    print(f"   Site: {package['site_name']}")
    print(f"   Auth: {package['auth_status']}")
    print(f"   Cookies: {package['metadata']['cookie_count']}")
    print(f"   Critical: {package['metadata']['critical_cookie_count']}")
    if package["metadata"].get("local_storage_count", 0) > 0:
        print(f"   localStorage: {package['metadata']['local_storage_count']} entries")
    if package["metadata"].get("session_storage_count", 0) > 0:
        print(
            f"   sessionStorage: {package['metadata']['session_storage_count']} entries"
        )

    print("\n" + packager.get_summary(package))
