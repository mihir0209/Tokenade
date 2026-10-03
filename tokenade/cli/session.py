"""Session-related CLI commands."""
import json
import logging
import os
import time
from pathlib import Path

from tokenade.core.browser.manager import BrowserFactory, BrowserConfig
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
        print(f"[ERROR] Cannot connect to CDP on port {port}: {e}")
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

        # 1. Get all cookies. The cookie store populates lazily after
        # browser launch (empty at first, fills in over ~10s on real
        # profiles), so poll instead of trusting the first response.
        cdp_cookies = []
        for _ in range(12):
            result = await cmd("Storage.getCookies")
            cdp_cookies = result.get("cookies", [])
            if cdp_cookies:
                break
            await asyncio.sleep(5)
        if cdp_cookies:
            print(f"   [OK] CDP cookie store ready ({len(cdp_cookies)} cookies)")

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
                    print(f"   [PKG] {domain}: {len(entries)} localStorage entries")
                except (json.JSONDecodeError, TypeError):
                    print(f"   [WARN] {domain}: localStorage parse failed")

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
                    print(f"   [PKG] {domain}: {len(entries)} sessionStorage entries")
                except (json.JSONDecodeError, TypeError):
                    print(f"   [WARN] {domain}: sessionStorage parse failed")

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
        print(f"[ERROR] CDP extraction failed: {e}")
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
        print("[ERROR] Accounts file is encrypted. Run with --master-password to decrypt.")
        return

    if not accounts:
        print("[ERROR] No accounts configured. Run 'tokenade setup' first.")
        return

    output_dir = Path("sessions")
    output_dir.mkdir(exist_ok=True)

    results = []

    for account in accounts:
        account_num = account.number
        email = account.email
        profile_dir = account.profile_dir or f"browser_data/{account_num}"

        print(f"\n[LIST] Account #{account_num}: {email}")

        if not Path(profile_dir).exists():
            print(f"   [ERROR] Profile not found: {profile_dir}")
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
                # Consult recommend() if site_name missing; fall back to "google"
                # only as a final legacy default (per ADR-0003).
                try:
                    from tokenade.core.recommend import recommend_site
                    rec_site = recommend_site(session=session)
                    site = rec_site or "google"
                except Exception:
                    site = "google"
            handler_cls = resolve_legacy_handler_class(site)
            if handler_cls is None:
                print(f"   [ERROR] No handler found for '{site}'. Install from tokenade-plugins marketplace.")
                continue
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
                print(f"   [OK] Token saved: {token_path}")

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
                "error": "Extraction failed - check browser is running and profile is accessible",
            })
        finally:
            browser.close()

    print("\n" + "=" * 80)
    print("EXTRACTION COMPLETE")
    print("=" * 80)

    successful = sum(1 for r in results if r.get("status") == "logged_in")
    print(f"\n[OK] Successful: {successful}/{len(accounts)}")
    print(f"[DIR] Sessions saved to: {output_dir}/")
    if successful == 0 and accounts:
        raise SystemExit(1)


def cmd_load(args):
    """Load session file into browser."""
    print("\n" + "=" * 80)
    print("TOKENADE - Session Load")
    print("=" * 80)

    file_path = args.file
    if not os.path.exists(file_path):
        print(f"[ERROR] File not found: {file_path}")
        return

    print(f"\n[DIR] Loading: {file_path}")

    site_config = None
    if args.site_config:
        with open(args.site_config) as f:
            site_config = json.load(f)
        if isinstance(site_config, list):
            site_config = site_config[0] if site_config else None

    loader = SessionLoader()
    keep_open = bool(getattr(args, "visible", False))

    # Origin-egress tunnel: open + verify the circuit BEFORE the browser
    # exists, then hand the plan's proxy/args/scripts to the loader.
    tunnel_state = None
    tunnel_session = None
    tunnel_mode = getattr(args, "tunnel", "off") or "off"
    load_proxy = None
    load_extra_args = None
    load_init_scripts = None
    if str(tunnel_mode).lower() != "off":
        from tokenade.core.importer.session_packager import SessionPackager
        from tokenade.core.session_runtime.plan import RuntimePlanBuilder
        from tokenade.core.tunnel.connect import open_tunnel_for_jar

        preview = SessionPackager().load(file_path)
        tunnel_state = open_tunnel_for_jar(
            preview,
            mode=tunnel_mode,
            relay_url=getattr(args, "tunnel_relay", None),
            echo_url=getattr(args, "tunnel_echo_url", None),
            allow_unpaired=bool(getattr(args, "tunnel_allow_unpaired", False)),
        )
        tunnel_session = tunnel_state.pop("_session")
        plan = RuntimePlanBuilder().build(
            preview,
            tunnel=tunnel_state,
            cli_overrides={"tunnel": tunnel_mode, "stealth_level": args.stealth_level},
        )
        load_proxy = plan.proxy
        load_extra_args = plan.launch_args or None
        load_init_scripts = plan.init_scripts or None
        print(f"\n[TUNNEL] {plan.report.get('egress_check', {}).get('message', '')}")
        print(f"   Proxy: {load_proxy.get('server') if load_proxy else 'none'}")
        print(f"   Oracle: {plan.report.get('oracle_mode')} "
              f"(fingerprint: {plan.report.get('fingerprint_source')})")

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
            acknowledge_exclusive_move=bool(getattr(args, "acknowledge_exclusive_move", False)),
            allow_single_use=bool(getattr(args, "claim_single_use", False)),
            auto_solve_challenges=not bool(getattr(args, "no_auto_solve", False)),
            capture_solved_sessions=bool(getattr(args, "capture_session", False)),
            session_output_dir=getattr(args, "capture_dir", None),
            proxy=load_proxy,
            extra_args=load_extra_args,
            init_scripts=load_init_scripts,
        )

        if result["success"]:
            print("\n[OK] Session loaded successfully")
            print(f"   Site: {result.get('site_name', 'unknown')}")
            if result.get("site_handler"):
                handler = result["site_handler"]
                print(f"   Site Handler: {handler.get('plugin_name') or handler.get('handler_name')}")
            print(f"   Cookies: {result['cookies_injected']}/{result['cookies_total']}")

            if result.get("local_storage_total", 0) > 0:
                print(f"   localStorage: {result['local_storage_injected']}/{result['local_storage_total']}")

            from tokenade.core.importer.session_loader import (
                storage_shortfall_message,
            )

            _shortfall = storage_shortfall_message(result)
            if _shortfall:
                print(f"   [WARN] {_shortfall}")

            if result.get("validation"):
                v = result["validation"]
                print(f"   Auth: {v.get('auth_status', 'unknown')}")
                print(f"   Valid: {v.get('valid', False)}")

            if args.runtime:
                print("\n Loading into RuntimeEngine...")
                print("   [OK] RuntimeEngine ready")

            # Interactive mode: leave Playwright browser open until Ctrl+C
            if keep_open and getattr(loader, "_browser", None):
                print("\n" + "=" * 80)
                print("Browser is running with injected session.")
                print("Press Ctrl+C to close the browser")
                print("=" * 80 + "\n")
                try:
                    while True:
                        time.sleep(1.0)
                        br = loader._browser
                        if br is None:
                            break
                        # Best-effort liveness check
                        try:
                            if hasattr(br, "is_connected") and not br.is_connected():
                                break
                        except Exception:
                            pass
                except KeyboardInterrupt:
                    print("\n[STOP] Closing browser...")
        else:
            print("\n[ERROR] Session load failed")
            if result.get("error"):
                print(f"   Error: {result['error']}")
            raise SystemExit(1)

    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"Load failed: {e}", exc_info=True)
        print("[ERROR] Load failed - verify session file is valid and not corrupted")
        raise SystemExit(1) from e
    finally:
        loader.close()
        if tunnel_session is not None:
            tunnel_session.close()


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
        print(f"[ERROR] Session file not found: {args.session}")
        raise SystemExit(1)

    with open(session_file) as f:
        session_data = json.load(f)

    fp_manager = FingerprintManager()
    fp_name = args.fingerprint or "default"

    print(f"\n[DIR] Session: {args.session}")
    print(f"[HIT] Target fingerprint: {fp_name}")

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
            print("\n[SEARCH] Validating stealth injection...")
            result = validate_injection(browser)
            if result["valid"]:
                print("   [OK] Stealth injection verified")
                print(f"   Webdriver: {result['webdriver_undefined']}")
                print(f"   User Agent: {result['user_agent'][:50]}...")
            else:
                print("   [WARN] Stealth injection may not be fully active")

        site = session_data.get("site_name")
        if not site:
            # Consult recommend if site_name is missing; only fall back to
            # "google" as a final legacy default (per ADR-0003).
            try:
                from tokenade.core.recommend import recommend_site
                site = recommend_site(
                    cookies=session_data.get("cookies"),
                    session=session_data,
                )
            except Exception:
                pass
            site = site or "google"
        handler_cls = resolve_legacy_handler_class(site)
        if handler_cls is None:
            print(f"[ERROR] No handler found for '{site}'. Install from tokenade-plugins marketplace.")
            raise SystemExit(1)
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
            print("[OK] Session transfer successful")
            if args.profile_dir:
                print(f"[SAVE] Profile saved to: {args.profile_dir}")
        else:
            print("[ERROR] Session transfer failed")
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
        print(f"[ERROR] Session file not found: {args.session}")
        return

    print(f"\n[DIR] Session: {args.session}")
    print(f"[NET] Browser: {args.browser}")
    print(f"[DIR] Profile: {args.profile}")

    if args.dry_run:
        print("\n[SEARCH] Dry run mode - no changes will be made")

    try:
        if args.dry_run:
            with open(session_file) as f:
                session = json.load(f)

            cookies = session.get('cookies', [])
            print("\n[STATS] Session info:")
            print(f"   Site: {session.get('site_name', 'unknown')}")
            print(f"   Cookies: {len(cookies)}")
            print(f"   Auth status: {session.get('auth_status', 'unknown')}")

            if cookies:
                print("\n Sample cookies:")
                for cookie in cookies[:5]:
                    print(f"   - {cookie.get('name')}: {cookie.get('domain')}")
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
                print("\n[OK] Injection successful")
                print(f"   Injected: {result.cookies_injected}/{result.cookies_total} cookies")
                if result.backup_path:
                    print(f"   Backup: {result.backup_path}")
            else:
                print("\n[ERROR] Injection failed")
                if result.error:
                    print(f"   Error: {result.error}")
                raise SystemExit(1)

    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"Profile injection failed: {e}", exc_info=True)
        print("[ERROR] Profile injection failed - check browser is not running")
        raise SystemExit(1) from e
