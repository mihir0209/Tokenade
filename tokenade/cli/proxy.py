"""Proxy CLI commands."""
import asyncio
import logging
import time
import webbrowser
import threading
from pathlib import Path

logger = logging.getLogger("tokenade")


def cmd_proxy(args):
    """Start fingerprint-matched proxy server."""
    from tokenade.core.importer.session_packager import SessionPackager
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
            print("❌ No session files found")
            return

        # Session rotation mode
        if args.rotate:
            from tokenade.core.importer.session_rotator import SessionRotator

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
                        print("❌ No available sessions")
                        break
                    try:
                        session = packager.load(session_path)
                        print(f"\n🔄 Rotating to: {Path(session_path).name} "
                              f"({session.get('site_name', 'unknown')})")
                    except Exception as e:
                        logger.warning(f"Failed to load {session_path}: {e}")
                        rotator.record_failure(rotator._entries.get(
                            Path(session_path).stem, None
                        ) and Path(session_path).stem or "")
                    time.sleep(args.rotate_interval)

            print("\n🔄 Starting rotation loop...")
            print("   Press Ctrl+C to stop\n")
            try:
                run_rotation()
            except KeyboardInterrupt:
                print("\n\n⚠️  Rotation stopped by user")
            return

        print(f"\n{'=' * 60}")
        print(f"TOKENADE - Multi-Site Proxy ({len(sessions)} sessions)")
        print(f"{'=' * 60}")

        from tokenade.core.proxy.multi_site_proxy import MultiSiteProxy
        proxy = MultiSiteProxy(sessions, base_port=args.port, host=args.host)
        asyncio.run(proxy.start())
        return

    if not args.session:
        print("❌ --session required (or use --all for multi-site mode)")
        return

    session_file = Path(args.session)
    if not session_file.exists():
        print(f"❌ Session file not found: {args.session}")
        return

    print("\n" + "=" * 80)
    print("TOKENADE - Fingerprint Proxy Server")
    print("=" * 80)
    print(f"\n📂 Session: {args.session}")
    print(f"🔌 Port: {args.port}")
    print(f"🔧 Mode: {args.mode}")

    if args.mode == "forward":
        print(f"   Configure browser: HTTP_PROXY=http://{args.host}:{args.port}")

    if args.mode != "forward":
        print(f"🧠 Engine: {'CDP (Playwright)' if not args.legacy else 'Legacy (SW)'}")
        if not args.legacy:
            print(f"🔐 Fingerprint: {'curl-cffi TLS matching' if args.fingerprint else 'Native browser (cookies only)'}")

    try:
        if args.mode == "forward":
            from tokenade.core.proxy.forward_proxy import ForwardProxy
            session = packager.load(str(session_file))
            proxy = ForwardProxy(session, port=args.port, host=args.host)
            asyncio.run(proxy.start())
        elif args.legacy:
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
                print(f"🔒 TLS Impersonation: {args.impersonate}")

            if args.auto_refresh:
                proxy._auto_refresh_config["auto_refresh"] = True
                if args.source_browser:
                    proxy._auto_refresh_config["source_browser"] = args.source_browser
                if args.source_profile:
                    proxy._auto_refresh_config["source_profile"] = args.source_profile
                print(f"🔄 Auto-refresh enabled from {args.source_browser or 'source browser'}")

            # Set auto-navigate URL
            if args.auto_navigate or args.target_url:
                target = args.target_url or proxy._get_site_url()
                proxy._auto_refresh_config["target_url"] = target
                print(f"🌐 Auto-navigate: {target}")

        if not args.no_open_browser:
            def open_browser_thread():
                import time
                time.sleep(2)
                url = f"http://127.0.0.1:{args.port}"
                if args.auto_navigate or args.target_url:
                    target = getattr(proxy, '_auto_refresh_config', {}).get('target_url')
                    if target:
                        # Navigate directly to the site proxy URL
                        url = f"http://127.0.0.1:{args.port}/browse?url={target}"
                webbrowser.open(url)

            threading.Thread(target=open_browser_thread, daemon=True).start()

        print("\n🚀 Starting proxy server...")
        proxy.run()

    except KeyboardInterrupt:
        print("\n\n⚠️  Proxy stopped by user")
    except Exception as e:
        logger.error(f"Proxy failed: {e}", exc_info=True)
        error_str = str(e).lower()
        if "address already in use" in error_str or "eaddrinuse" in error_str:
            print(f"❌ Port {args.port} is already in use.")
            print(f"   Try: tokenade proxy -s {args.session} --port {args.port + 1}")
            print(f"   Or kill the existing process: lsof -ti:{args.port} | xargs kill")
        elif "session" in error_str and ("not found" in error_str or "no such file" in error_str):
            print(f"❌ Session file not found: {args.session}")
            print("   Export one first: tokenade export --browser-name firefox --domains 'example.com' -o session.tokenade")
        elif "playwright" in error_str or "chromium" in error_str or "executable" in error_str:
            print("❌ Chromium browser not found.")
            print("   Install: playwright install chromium")
        elif "permission" in error_str or "access" in error_str:
            print("❌ Permission denied — check file and directory permissions")
        else:
            print(f"❌ Proxy failed: {e}")
            print("   Check logs for details: ~/.tokenade/logs/")
