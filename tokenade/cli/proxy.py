"""Proxy CLI commands."""
import asyncio
import logging
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

        print(f"\n{'='*60}")
        print(f"TOKENADE - Multi-Site Proxy ({len(sessions)} sessions)")
        print(f"{'='*60}")

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

            if args.auto_refresh:
                proxy._refresher.config.auto_refresh = True
                if args.source_browser:
                    proxy._refresher.config.source_browser = args.source_browser
                if args.source_profile:
                    proxy._refresher.config.source_profile = args.source_profile
                print(f"🔄 Auto-refresh enabled from {args.source_browser or 'source browser'}")

        if not args.no_open_browser:
            def open_browser_thread():
                import time
                time.sleep(2)
                webbrowser.open(f"http://127.0.0.1:{args.port}")

            threading.Thread(target=open_browser_thread, daemon=True).start()

        print(f"\n🚀 Starting proxy server...")
        proxy.run()

    except KeyboardInterrupt:
        print("\n\n⚠️  Proxy stopped by user")
    except Exception as e:
        logger.error(f"Proxy failed: {e}", exc_info=True)
        print(f"❌ Proxy failed — check port is available and session file is valid")
