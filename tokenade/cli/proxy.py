"""Proxy CLI commands."""
import asyncio
import json
import logging
import time
import webbrowser
import threading
from pathlib import Path

logger = logging.getLogger("tokenade")


def cmd_proxy(args):
    """Resolve upstream proxy provider requests or run hidden legacy proxy."""
    if getattr(args, "proxy_action", None) == "resolve":
        return cmd_proxy_resolve(args)
    if getattr(args, "proxy_action", None) == "legacy":
        return cmd_proxy_legacy(args)

    if not hasattr(args, "proxy_action"):
        return cmd_proxy_legacy(args)

    if any(getattr(args, name, None) for name in ("session", "all", "sessions_dir", "decrypt_password")):
        return cmd_proxy_legacy(args)

    print("Usage: tokenade proxy {resolve}")
    return


def cmd_proxy_resolve(args):
    """Resolve upstream proxy provider plugins from request.json."""
    from tokenade.core.proxy.provider import ProxyProviderError, ProxyProviderResolver
    from tokenade.core.request_config import RequestConfigError, load_request_config

    try:
        request = load_request_config(args.request)
        providers = request.plugins_for_role("proxy_provider")
        if not providers:
            raise ProxyProviderError("request.plugins must include at least one plugin with roles.proxy_provider")

        source_network = {}
        raw_source = request.raw.get("source_network")
        if isinstance(raw_source, dict):
            source_network = raw_source

        session_metadata = {}
        raw_sessions = request.raw.get("sessions")
        if isinstance(raw_sessions, dict):
            session_metadata["sessions"] = {k: v for k, v in raw_sessions.items() if k in ("dir", "pattern")}

        resolver = ProxyProviderResolver()
        results = []
        for plugin in providers:
            try:
                proxy = resolver.resolve(plugin, session_metadata=session_metadata, source_network=source_network)
                results.append({
                    "success": True,
                    "plugin_name": plugin.name,
                    "proxy": proxy.to_dict(show_secrets=bool(args.show_secrets)),
                    "error": None,
                })
            except ProxyProviderError as exc:
                if plugin.required:
                    raise
                results.append({
                    "success": True,
                    "plugin_name": plugin.name,
                    "proxy": None,
                    "error": {"message": str(exc), "skipped": True},
                })

        envelope = {
            "success": all(result["success"] for result in results),
            "operation": "proxy.resolve",
            "results": results,
        }
        print(json.dumps(envelope, ensure_ascii=False, indent=2 if args.pretty else None))
    except (ProxyProviderError, RequestConfigError) as exc:
        envelope = {
            "success": False,
            "operation": "proxy.resolve",
            "results": [],
            "error": {"message": str(exc)},
        }
        print(json.dumps(envelope, ensure_ascii=False, indent=2 if getattr(args, "pretty", False) else None))
        raise SystemExit(2)


def cmd_proxy_legacy(args):
    """Hidden legacy local/CDP proxy behavior."""
    from tokenade.core.importer.session_packager import SessionPackager
    from tokenade.core.errors import DependencyError, TokenadeError

    # Fail closed before launching browser if TLS matching requested without curl-cffi
    if getattr(args, "fingerprint", False) and getattr(args, "mode", "cdp") != "forward":
        try:
            from tokenade.core.runtime.tls_matcher import require_curl_cffi
            require_curl_cffi()
        except DependencyError as e:
            print(f"[ERROR] {e}")
            raise SystemExit(2) from e

    packager = SessionPackager()

    if args.all:
        sessions = []
        search_dirs = [args.sessions_dir] if args.sessions_dir else ["."]
        for d in search_dirs:
            p = Path(d)
            for ext in ("*.tokenade", "*.session"):
                for f in p.glob(ext):
                    try:
                        session = packager.load(str(f))
                        sessions.append(session)
                        print(f"  Loaded: {f.name} ({session.get('site_name', 'unknown')})")
                    except Exception as e:
                        logger.warning(f"Failed to load {f}: {e}", exc_info=True)

        if not sessions:
            print("[ERROR] No session files found")
            return

        # Session rotation mode
        if args.rotate:
            from tokenade.core.refresh.rotator import SessionRotator

            print(f"\n{'=' * 60}")
            print(f"TOKENADE - Session Rotation ({len(sessions)} sessions)")
            print(f"{'=' * 60}")
            print(f"  Strategy: {args.rotate_strategy}")
            print(f"  Interval: {args.rotate_interval}s")

            rotator = SessionRotator(
                sessions_dir=args.sessions_dir or ".",
                strategy=args.rotate_strategy,
                cooldown_seconds=args.rotate_interval,
            )
            rotator.load_sessions()

            status = rotator.get_status()
            print(f"  Available: {status['available_sessions']} sessions")
            print(f"  Average health: {status['metrics']['average_health']}%")
            print(f"\n{'=' * 60}")

            # Start rotation loop
            def run_rotation():
                while True:
                    session_path = rotator.next()
                    if not session_path:
                        print("[ERROR] No available sessions")
                        break
                    try:
                        session = packager.load(session_path)
                        print(f"\n[SYNC] Rotating to: {Path(session_path).name} "
                              f"({session.get('site_name', 'unknown')})")
                    except Exception as e:
                        logger.warning(f"Failed to load {session_path}: {e}")
                        rotator.record_failure(rotator._entries.get(
                            Path(session_path).stem, None
                        ) and Path(session_path).stem or "")
                    time.sleep(args.rotate_interval)

            print("\n[SYNC] Starting rotation loop...")
            print("   Press Ctrl+C to stop\n")
            try:
                run_rotation()
            except KeyboardInterrupt:
                print("\n\n[WARN] Rotation stopped by user")
            return

        print(f"\n{'=' * 60}")
        print(f"TOKENADE - Multi-Site Proxy ({len(sessions)} sessions)")
        print(f"{'=' * 60}")

        from tokenade.core.proxy.multi_site_proxy import MultiSiteProxy
        proxy = MultiSiteProxy(sessions, base_port=args.port, host=args.host)
        try:
            asyncio.run(proxy.start())
        except RuntimeError as exc:
            print(f"\n[ERROR] {exc}")
        return

    if not args.session:
        print("[ERROR] --session required (or use --all for multi-site mode)")
        return

    session_file = Path(args.session)
    if not session_file.exists():
        print(f"[ERROR] Session file not found: {args.session}")
        return

    # Decrypt if password provided
    decrypt_password = getattr(args, 'decrypt_password', None)
    if decrypt_password:
        import tempfile
        try:
            from tokenade.core.crypto.at_rest import load_encrypted
            session_data = load_encrypted(str(session_file), password=decrypt_password)
            temp_path = Path(tempfile.mktemp(suffix='.tokenade'))
            with open(temp_path, 'w') as f:
                json.dump(session_data, f)
            session_file = temp_path
            print(" Decrypted session with password")
        except Exception as e:
            print(f"[ERROR] Decryption failed: {e}")
            return

    print("\n" + "=" * 80)
    print("TOKENADE - Fingerprint Proxy Server")
    print("=" * 80)
    print(f"\n[DIR] Session: {args.session}")
    print(f"[CDP] Port: {args.port}")
    print(f" Mode: {args.mode}")
    print(f"[NET] Host: {args.host}")

    if args.host == "0.0.0.0":
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            external_ip = s.getsockname()[0]
            s.close()
        except Exception:
            external_ip = "<your-ip>"
        print("\n    MULTI-DEVICE ACCESS:")
        print("   Other devices can access this proxy at:")
        print(f"   -> http://{external_ip}:{args.port}")
        print("\n   [WARN] All traffic routes through THIS machine's IP.")
        print("   Sessions stay valid because cookies never leave this device.")

    if args.mode == "forward":
        print(f"   Configure browser: HTTP_PROXY=http://{args.host}:{args.port}")

    if args.mode != "forward":
        print(f" Engine: {'CDP (Playwright)' if not args.legacy else 'Legacy (SW)'}")
        if not args.legacy:
            print(f"[KEY] Fingerprint: {'curl-cffi TLS matching' if args.fingerprint else 'Native browser (cookies only)'}")

    try:
        if args.mode == "forward":
            from tokenade.core.proxy.forward_proxy import ForwardProxy
            session = packager.load(str(session_file))
            proxy = ForwardProxy(session, port=args.port, host=args.host)
            if not args.no_open_browser:
                def open_browser_thread():
                    time.sleep(2)
                    webbrowser.open(f"http://{args.host if args.host != '0.0.0.0' else '127.0.0.1'}:{args.port}")
                threading.Thread(target=open_browser_thread, daemon=True).start()
            print("\n[...] Starting proxy server...")
            # ForwardProxy.start() blocks until cancelled; do not call proxy.run()
            asyncio.run(proxy.start())
            return

        if args.legacy:
            from tokenade.core.proxy.server import TokenadeProxy, ProxyConfig
            gui_mode = not args.no_gui
            config = ProxyConfig(
                port=args.port,
                host=args.host,
                gui_mode=gui_mode,
                verbose=args.verbose
            )
            proxy = TokenadeProxy.from_session_file(str(session_file), config)
        else:
            from tokenade.core.proxy.cdp_proxy import CDPProxy, CDPProxyConfig

            config = CDPProxyConfig(
                port=args.port,
                host=args.host,
                headless=not args.visible,
                timeout=args.timeout,
                use_fingerprint=args.fingerprint,
            )
            proxy = CDPProxy.from_session_file(str(session_file), config)

            # Set impersonate target for TLS matching
            if args.impersonate:
                proxy._auto_refresh_config["impersonate"] = args.impersonate
                print(f"[LOCK] TLS Impersonation: {args.impersonate}")

            if args.auto_refresh:
                proxy._auto_refresh_config["auto_refresh"] = True
                if args.source_browser:
                    proxy._auto_refresh_config["source_browser"] = args.source_browser
                if args.source_profile:
                    proxy._auto_refresh_config["source_profile"] = args.source_profile
                print(f"[SYNC] Auto-refresh enabled from {args.source_browser or 'source browser'}")

            # Set auto-navigate URL
            if args.auto_navigate or args.target_url:
                target = args.target_url or proxy._get_site_url()
                proxy._auto_refresh_config["target_url"] = target
                print(f"[NET] Auto-navigate: {target}")

        if not args.no_open_browser:
            def open_browser_thread():
                import time as _time
                _time.sleep(2)
                if args.host == "0.0.0.0":
                    import socket
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        s.connect(("8.8.8.8", 80))
                        bind_ip = s.getsockname()[0]
                        s.close()
                    except Exception:
                        bind_ip = "127.0.0.1"
                else:
                    bind_ip = args.host
                url = f"http://{bind_ip}:{args.port}"
                if args.auto_navigate or args.target_url:
                    target = getattr(proxy, '_auto_refresh_config', {}).get('target_url')
                    if target:
                        url = f"http://{bind_ip}:{args.port}/browse?url={target}"
                webbrowser.open(url)

            threading.Thread(target=open_browser_thread, daemon=True).start()

        print("\n[...] Starting proxy server...")
        if hasattr(proxy, "run"):
            proxy.run()
        elif hasattr(proxy, "start"):
            # TokenadeProxy / other start APIs
            maybe = proxy.start()
            if asyncio.iscoroutine(maybe):
                asyncio.run(maybe)
            else:
                # blocking start
                pass
        else:
            raise RuntimeError(f"Proxy type {type(proxy).__name__} has no run/start method")

    except KeyboardInterrupt:
        print("\n\n[WARN] Proxy stopped by user")
    except Exception as e:
        from tokenade.core.errors import DependencyError, ProxyError, TokenadeError
        logger.error("Proxy failed: %s", e, exc_info=True)
        error_str = str(e).lower()
        if isinstance(e, DependencyError):
            print(f"[ERROR] {e}")
        elif "address already in use" in error_str or "eaddrinuse" in error_str:
            print(f"[ERROR] Port {args.port} is already in use.")
            print(f"   Try: tokenade proxy -s {args.session} --port {args.port + 1}")
            print(f"   Or kill the existing process: lsof -ti:{args.port} | xargs kill")
        elif "session" in error_str and ("not found" in error_str or "no such file" in error_str):
            print(f"[ERROR] Session file not found: {args.session}")
            print("   Export one first: tokenade export --browser-name firefox --domains 'example.com' -o session.tokenade")
        elif "playwright" in error_str or "chromium" in error_str or "executable" in error_str:
            print("[ERROR] Chromium browser not found.")
            print("   Install: playwright install chromium")
        elif "permission" in error_str or "access" in error_str:
            print("[ERROR] Permission denied - check file and directory permissions")
        elif isinstance(e, (ProxyError, TokenadeError)):
            print(f"[ERROR] {e}")
        else:
            print(f"[ERROR] Proxy failed: {e}")
            print("   Check logs for details: ~/.tokenade/logs/")
        raise SystemExit(1) from e
