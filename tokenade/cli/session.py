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
from tokenade.handlers.google import GoogleHandler

logger = logging.getLogger("tokenade")


def cmd_extract(args):
    """Extract tokens from saved browser sessions."""
    from datetime import datetime
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

            handler = GoogleHandler(browser)
            session = handler.get_session()

            session_path = output_dir / f"google_{account_num}_{email.replace('@', '_at_')}.json"
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

    browser_path = args.browser_path
    browser_name = args.browser_name or "unknown"
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
            print(f"❌ No profile found for {browser_name}")
            return

    if not browser_path:
        print("❌ No browser path specified. Use --browser-name or --browser-path")
        return

    print(f"\n🍪 Extracting cookies from: {browser_path}")
    extractor = CookieExtractor(browser_path, browser=browser_name)

    site_config = None
    if args.site_config:
        with open(args.site_config) as f:
            site_config = json.load(f)

    domain_filter = None
    if args.domains:
        domain_filter = [d.strip() for d in args.domains.split(",") if d.strip()]

    try:
        if args.file_path:
            cookies = extractor.extract_from_file(args.file_path, args.format or "netscape")
        else:
            cookies = extractor.extract(site_filter=None)
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)
        print(f"❌ Extraction failed — check browser profile is accessible")
        return

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
    if args.extract_local_storage:
        print(f"\n💾 Extracting localStorage from: {browser_path}")
        ls_extractor = LocalStorageExtractor(browser_path, browser=browser_name)

        try:
            if args.local_storage_origin:
                local_storage = ls_extractor.extract(origin_filter=args.local_storage_origin)
                print(f"   📊 localStorage entries for {args.local_storage_origin}: {len(local_storage)}")
            else:
                origins = ls_extractor.list_origins()
                if origins:
                    print(f"   📋 Available origins ({len(origins)}):")
                    for origin in origins[:10]:
                        print(f"      • {origin}")
                    if len(origins) > 10:
                        print(f"      ... and {len(origins) - 10} more")
                    print("\n   💡 Use --local-storage-origin to specify which origin to extract")
                else:
                    print("   ⚠️  No localStorage data found")
        except Exception as e:
            logger.warning(f"localStorage extraction failed: {e}", exc_info=True)
            print(f"   ⚠️  localStorage extraction skipped — browser may be running")
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

    if not cookies and not local_storage:
        print("❌ No cookies or localStorage to export")
        return

    packager = SessionPackager()
    package = packager.package(
        cookies=cookies,
        browser=browser_name,
        profile=args.profile or "unknown",
        local_storage=local_storage if local_storage else None,
    )

    site_name = package.get("site_name", "session")
    output = args.output or f"{site_name}_session"

    saved_path = packager.save(package, output)
    print(f"\n💾 Exported: {saved_path}")
    print(f"   Site: {package['site_name']}")
    print(f"   Auth: {package['auth_status']}")
    print(f"   Cookies: {package['metadata']['cookie_count']}")
    print(f"   Critical: {package['metadata']['critical_cookie_count']}")
    if package['metadata'].get('local_storage_count', 0) > 0:
        print(f"   localStorage: {package['metadata']['local_storage_count']} entries")

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
            print(f"\n✅ Session loaded successfully")
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
            print(f"\n❌ Session load failed")
            if result.get("error"):
                print(f"   Error: {result['error']}")

    except Exception as e:
        logger.error(f"Load failed: {e}", exc_info=True)
        print(f"❌ Load failed — verify session file is valid and not corrupted")
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
        return

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

        handler = GoogleHandler(browser)

        session = SessionData(
            site_name=session_data["site_name"],
            auth_status=AuthStatus(session_data["auth_status"]),
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
            print(f"\n📊 Session info:")
            print(f"   Site: {session.get('site_name', 'unknown')}")
            print(f"   Cookies: {len(cookies)}")
            print(f"   Auth status: {session.get('auth_status', 'unknown')}")

            if cookies:
                print(f"\n🍪 Sample cookies:")
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
                print(f"\n✅ Injection successful")
                print(f"   Injected: {result.cookies_injected}/{result.cookies_total} cookies")
                if result.backup_path:
                    print(f"   Backup: {result.backup_path}")
            else:
                print(f"\n❌ Injection failed")
                if result.error:
                    print(f"   Error: {result.error}")

    except Exception as e:
        logger.error(f"Profile injection failed: {e}", exc_info=True)
        print(f"❌ Profile injection failed — check browser is not running")
