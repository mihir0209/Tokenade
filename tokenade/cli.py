"""
Tokenade CLI - Main entry point for the token shifting tool.

Usage:
    tokenade setup          # Setup accounts and initial login
    tokenade extract        # Extract tokens from saved sessions
    tokenade transfer       # Transfer session to another device
    tokenade test           # Test session portability
    tokenade fingerprint    # Manage browser fingerprints
    tokenade validate       # Validate stored sessions
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from tokenade.core.browser.manager import BrowserFactory, BrowserConfig
from tokenade.core.crypto.cookie_crypto import CookieCryptoFactory
from tokenade.core.fingerprint.manager import FingerprintManager, FingerprintCollector
from tokenade.core.fingerprint.injector import inject_stealth_script, validate_injection
from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery
from tokenade.core.importer.cookie_extractor import CookieExtractor, SiteFilter
from tokenade.core.importer.local_storage_extractor import LocalStorageExtractor
from tokenade.core.importer.session_packager import SessionPackager
from tokenade.core.importer.session_loader import SessionLoader
from tokenade.handlers.base import HandlerRegistry
from tokenade.handlers.google import GoogleHandler
from tokenade.tests.portability import PortabilityTester

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("tokenade")


def setup_logging(verbose: bool = False):
    """Configure logging level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.getLogger("tokenade").setLevel(level)


def cmd_setup(args):
    """Setup accounts with initial login."""
    from datetime import datetime
    
    print("\n" + "=" * 80)
    print("TOKENADE - Account Setup")
    print("=" * 80)
    
    accounts_file = Path("accounts.json")
    accounts = []
    
    if accounts_file.exists():
        with open(accounts_file) as f:
            accounts = json.load(f)
        print(f"\n📋 Found {len(accounts)} existing account(s)")
    
    while True:
        choice = input("\nAdd account? (yes/no): ").strip().lower()
        if choice not in ("yes", "y"):
            break
        
        email = input("📧 Email: ").strip()
        password = input("🔒 Password: ").strip()
        
        if not email or not password:
            print("❌ Email and password required")
            continue
        
        account_num = len(accounts) + 1
        profile_dir = f"browser_data/{account_num}"
        
        print(f"\n🚀 Setting up account #{account_num}...")
        
        # Launch visible browser for manual login
        config = BrowserConfig(
            headless=False,
            user_data_dir=profile_dir,
        )
        
        browser = BrowserFactory.create(**config.__dict__)
        page = browser.launch()
        
        try:
            handler = GoogleHandler(browser)
            status = handler.login(email, password, headless=False)
            
            if status.value == "logged_in":
                accounts.append({
                    "number": account_num,
                    "email": email,
                    "password": password,
                    "profile_dir": profile_dir,
                    "created_at": datetime.now().isoformat(),
                })
                
                with open(accounts_file, "w") as f:
                    json.dump(accounts, f, indent=2)
                
                print(f"✅ Account #{account_num} setup complete")
            else:
                print(f"❌ Login failed for account #{account_num}")
                
        finally:
            browser.close()
    
    print(f"\n📊 Total accounts: {len(accounts)}")
    print("\nNext: run 'tokenade extract' to collect tokens")


def cmd_extract(args):
    """Extract tokens from saved browser sessions."""
    from datetime import datetime
    
    print("\n" + "=" * 80)
    print("TOKENADE - Token Extraction")
    print("=" * 80)
    
    accounts_file = Path("accounts.json")
    if not accounts_file.exists():
        print("❌ No accounts configured. Run 'tokenade setup' first.")
        return
    
    with open(accounts_file) as f:
        accounts = json.load(f)
    
    output_dir = Path("sessions")
    output_dir.mkdir(exist_ok=True)
    
    results = []
    
    for account in accounts:
        account_num = account["number"]
        email = account["email"]
        profile_dir = account.get("profile_dir", f"browser_data/{account_num}")
        
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
            
            # Save session
            session_path = output_dir / f"google_{account_num}_{email.replace('@', '_at_')}.json"
            handler.save_session(str(session_path))
            
            # Also save tokens separately
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
            logger.error(f"Extraction failed for account {account_num}: {e}")
            results.append({
                "account": account_num,
                "email": email,
                "status": "error",
                "error": str(e),
            })
        finally:
            browser.close()
    
    # Summary
    print("\n" + "=" * 80)
    print("EXTRACTION COMPLETE")
    print("=" * 80)
    
    successful = sum(1 for r in results if r.get("status") == "logged_in")
    print(f"\n✅ Successful: {successful}/{len(accounts)}")
    print(f"📁 Sessions saved to: {output_dir}/")


def cmd_transfer(args):
    """Transfer session to target device/browser with fingerprint spoofing."""
    print("\n" + "=" * 80)
    print("TOKENADE - Session Transfer")
    print("=" * 80)
    
    session_file = Path(args.session)
    if not session_file.exists():
        print(f"❌ Session file not found: {args.session}")
        return
    
    with open(session_file) as f:
        session_data = json.load(f)
    
    # Load fingerprint if specified
    fp_manager = FingerprintManager()
    fp_name = args.fingerprint or "default"
    
    print(f"\n📁 Session: {args.session}")
    print(f"🎯 Target fingerprint: {fp_name}")
    
    # Load fingerprint for spoofing
    fp = fp_manager.load(fp_name)
    if fp:
        print(f"   User Agent: {fp.user_agent[:60]}...")
        print(f"   Screen: {fp.screen_width}x{fp.screen_height}")
        print(f"   Platform: {fp.platform}")
    
    # Launch browser with target fingerprint and stealth
    config = BrowserConfig(
        headless=not args.visible,
        user_data_dir=args.profile_dir,
        fingerprint=fp.to_dict() if fp else None,
        stealth_level=args.stealth_level,
    )
    
    browser = BrowserFactory.create(**config.__dict__)
    
    try:
        browser.launch()
        
        # Validate stealth injection
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
        
        from tokenade.handlers.base import SessionData, AuthStatus
        session = SessionData(
            site_name=session_data["site_name"],
            auth_status=AuthStatus(session_data["auth_status"]),
            tokens=[],
            cookies=session_data.get("cookies", []),
        )
        
        success = handler.inject_session(session)
        
        if success:
            print("✅ Session transfer successful")
            
            # Save the new profile
            if args.profile_dir:
                print(f"💾 Profile saved to: {args.profile_dir}")
        else:
            print("❌ Session transfer failed")
            
    finally:
        browser.close()


def cmd_test(args):
    """Run portability tests with fingerprint spoofing."""
    print("\n" + "=" * 80)
    print("TOKENADE - Portability Test")
    print("=" * 80)
    
    session_file = Path(args.session)
    if not session_file.exists():
        print(f"❌ Session file not found: {args.session}")
        return
    
    with open(session_file) as f:
        session_data = json.load(f)
    
    fp_manager = FingerprintManager()
    tester = PortabilityTester(BrowserFactory, fp_manager)
    
    print(f"\n🛡️  Stealth level: {args.stealth_level}")
    
    if args.variations:
        print("\n🧪 Testing fingerprint variations...")
        results = tester.test_fingerprint_variations(
            session_data=session_data,
            base_fp_name=args.source_fp or "default",
            handler_class=GoogleHandler,
        )
    else:
        print(f"\n🧪 Testing transfer to: {args.target_fp}")
        
        # Load target fingerprint for spoofing
        fp = fp_manager.load(args.target_fp)
        if fp:
            print(f"   User Agent: {fp.user_agent[:60]}...")
            print(f"   Screen: {fp.screen_width}x{fp.screen_height}")
        
        result = tester.test_session_transfer(
            session_data=session_data,
            source_fp_name=args.source_fp or "default",
            target_fp_name=args.target_fp,
            handler_class=GoogleHandler,
            test_api=args.test_api,
        )
        results = [result]
        
        # Validate stealth if requested
        if args.validate_stealth and fp:
            print("\n🔍 Validating stealth injection...")
            config = BrowserConfig(
                headless=True,
                fingerprint=fp.to_dict(),
                stealth_level=args.stealth_level,
            )
            browser = BrowserFactory.create(**config.__dict__)
            try:
                browser.launch()
                result = validate_injection(browser)
                if result["valid"]:
                    print("   ✅ Stealth injection verified")
                else:
                    print("   ⚠️  Stealth injection may not be fully active")
            finally:
                browser.close()
    
    # Generate report
    report = tester.generate_report(args.output)
    print(report)


def cmd_fingerprint(args):
    """Manage browser fingerprints."""
    fp_manager = FingerprintManager()
    
    if args.action == "list":
        print("\n📋 Stored fingerprints:")
        for name in fp_manager.list():
            print(f"   • {name}")
    
    elif args.action == "collect":
        print("\n🚀 Launching browser to collect fingerprint...")
        
        config = BrowserConfig(
            headless=False,
            user_data_dir=args.profile_dir,
        )
        
        browser = BrowserFactory.create(**config.__dict__)
        
        try:
            browser.launch()
            fp = FingerprintCollector.collect_from_browser(browser)
            path = fp_manager.save(args.name, fp)
            print(f"✅ Fingerprint saved: {path}")
            print(f"\n   User Agent: {fp.user_agent[:80]}...")
            print(f"   Screen: {fp.screen_width}x{fp.screen_height}")
            print(f"   Platform: {fp.platform}")
        finally:
            browser.close()
    
    elif args.action == "show":
        fp = fp_manager.load(args.name)
        if fp:
            print(f"\n🔍 Fingerprint: {args.name}")
            print(f"   User Agent: {fp.user_agent}")
            print(f"   Screen: {fp.screen_width}x{fp.screen_height}")
            print(f"   Viewport: {fp.viewport_width}x{fp.viewport_height}")
            print(f"   Platform: {fp.platform}")
            print(f"   Language: {fp.language}")
            print(f"   Timezone: {fp.timezone}")
            print(f"   Hardware: {fp.hardware_concurrency} cores, {fp.device_memory}GB RAM")
        else:
            print(f"❌ Fingerprint not found: {args.name}")
    
    elif args.action == "delete":
        if fp_manager.delete(args.name):
            print(f"✅ Deleted: {args.name}")
        else:
            print(f"❌ Not found: {args.name}")


def cmd_export(args):
    """Export session from existing browser to .tokenade file."""
    print("\n" + "=" * 80)
    print("TOKENADE - Session Export")
    print("=" * 80)

    # List profiles mode
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

    # Determine browser path
    browser_path = args.browser_path
    browser_name = args.browser_name or "unknown"
    if not browser_path and browser_name:
        discovery = BrowserProfileDiscovery()
        profiles = discovery.discover_all()
        # Flatten dict of lists into a single list
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

    # Extract cookies
    print(f"\n🍪 Extracting cookies from: {browser_path}")
    extractor = CookieExtractor(browser_path, browser=browser_name)

    try:
        if args.file_path:
            # Parse from file
            cookies = extractor.extract_from_file(args.file_path, args.format or "netscape")
        else:
            # Extract from browser database
            site_filter = SiteFilter(args.site) if args.site else None
            cookies = extractor.extract(site_filter)
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        print(f"❌ Extraction failed: {e}")
        return

    print(f"   📊 Total cookies: {len(cookies)}")

    # Filter by site
    if args.site and not args.file_path:
        site_filter = SiteFilter(args.site)
        cookies = site_filter.filter_cookies(cookies)
        print(f"   🎯 Filtered to {len(cookies)} cookies for site(s): {', '.join(args.site)}")

    # Extract localStorage if requested
    local_storage = {}
    if args.extract_local_storage:
        print(f"\n💾 Extracting localStorage from: {browser_path}")
        ls_extractor = LocalStorageExtractor(browser_path, browser=browser_name)

        try:
            if args.local_storage_origin:
                local_storage = ls_extractor.extract(origin_filter=args.local_storage_origin)
                print(f"   📊 localStorage entries for {args.local_storage_origin}: {len(local_storage)}")
            else:
                # List available origins
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
            logger.warning(f"localStorage extraction failed: {e}")
            print(f"   ⚠️  localStorage extraction failed: {e}")

    if not cookies and not local_storage:
        print("❌ No cookies or localStorage to export")
        return

    # Package
    packager = SessionPackager()
    package = packager.package(
        cookies=cookies,
        browser=browser_name,
        profile=args.profile or "unknown",
        local_storage=local_storage if local_storage else None,
    )

    # Determine output path
    site_name = package.get("site_name", "session")
    output = args.output or f"{site_name}_session.tokenade"

    # Save
    saved_path = packager.save(package, output)
    print(f"\n💾 Exported: {saved_path}")
    print(f"   Site: {package['site_name']}")
    print(f"   Auth: {package['auth_status']}")
    print(f"   Cookies: {package['metadata']['cookie_count']}")
    print(f"   Critical: {package['metadata']['critical_cookie_count']}")
    if package['metadata'].get('local_storage_count', 0) > 0:
        print(f"   localStorage: {package['metadata']['local_storage_count']} entries")

    # Show summary
    print("\n" + packager.get_summary(package))


def cmd_load(args):
    """Load .tokenade file into browser."""
    print("\n" + "=" * 80)
    print("TOKENADE - Session Load")
    print("=" * 80)

    file_path = args.file
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return

    print(f"\n📂 Loading: {file_path}")

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
                # RuntimeEngine integration would go here
                print("   ✅ RuntimeEngine ready")
        else:
            print(f"\n❌ Session load failed")
            if result.get("error"):
                print(f"   Error: {result['error']}")

    except Exception as e:
        logger.error(f"Load failed: {e}")
        print(f"❌ Load failed: {e}")
    finally:
        loader.close()


def cmd_validate(args):
    """Validate stored sessions."""
    print("\n" + "=" * 80)
    print("TOKENADE - Session Validation")
    print("=" * 80)
    
    sessions_dir = Path(args.sessions_dir)
    if not sessions_dir.exists():
        print(f"❌ Directory not found: {args.sessions_dir}")
        return
    
    valid = 0
    invalid = 0
    
    for session_file in sessions_dir.glob("*.json"):
        print(f"\n📁 Checking: {session_file.name}")
        
        try:
            with open(session_file) as f:
                data = json.load(f)
            
            # Check required fields
            required = ["site_name", "auth_status", "cookies"]
            missing = [f for f in required if f not in data]
            
            if missing:
                print(f"   ❌ Missing fields: {missing}")
                invalid += 1
                continue
            
            # Check cookies
            cookies = data.get("cookies", [])
            if not cookies:
                print(f"   ⚠️  No cookies")
            else:
                print(f"   ✅ {len(cookies)} cookies")
            
            # Check tokens
            tokens = data.get("tokens", [])
            if tokens:
                print(f"   ✅ {len(tokens)} tokens")
            
            # Check auth status
            status = data.get("auth_status", "unknown")
            if status == "logged_in":
                print(f"   ✅ Status: logged_in")
                valid += 1
            else:
                print(f"   ⚠️  Status: {status}")
                invalid += 1
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            invalid += 1
    
    print(f"\n📊 Summary: {valid} valid, {invalid} invalid")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Tokenade - Production-grade token shifting tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  tokenade setup                    # Setup accounts
  tokenade extract                  # Extract tokens (headless)
  tokenade extract --visible        # Extract tokens (visible browser)
  tokenade test -s session.json     # Test session portability
  tokenade fingerprint collect -n my_pc  # Collect fingerprint
        """,
    )
    
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Setup
    setup_parser = subparsers.add_parser("setup", help="Setup accounts")
    
    # Extract
    extract_parser = subparsers.add_parser("extract", help="Extract tokens")
    extract_parser.add_argument("--visible", action="store_true", help="Show browser window")
    
    # Transfer
    transfer_parser = subparsers.add_parser("transfer", help="Transfer session")
    transfer_parser.add_argument("-s", "--session", required=True, help="Session file path")
    transfer_parser.add_argument("-f", "--fingerprint", help="Target fingerprint name")
    transfer_parser.add_argument("-p", "--profile-dir", default="browser_data/transfer", help="Profile directory")
    transfer_parser.add_argument("--visible", action="store_true", help="Show browser window")
    transfer_parser.add_argument("--stealth-level", choices=["basic", "advanced", "maximum"], default="maximum", help="Stealth injection level")
    transfer_parser.add_argument("--validate-stealth", action="store_true", help="Validate stealth injection after launch")
    
    # Test
    test_parser = subparsers.add_parser("test", help="Test portability")
    test_parser.add_argument("-s", "--session", required=True, help="Session file path")
    test_parser.add_argument("--source-fp", default="default", help="Source fingerprint")
    test_parser.add_argument("--target-fp", default="default", help="Target fingerprint")
    test_parser.add_argument("--variations", action="store_true", help="Test fingerprint variations")
    test_parser.add_argument("--test-api", action="store_true", help="Test API calls")
    test_parser.add_argument("--stealth-level", choices=["basic", "advanced", "maximum"], default="maximum", help="Stealth injection level")
    test_parser.add_argument("--validate-stealth", action="store_true", help="Validate stealth injection")
    test_parser.add_argument("-o", "--output", help="Output report path")
    
    # Fingerprint
    fp_parser = subparsers.add_parser("fingerprint", help="Manage fingerprints")
    fp_parser.add_argument("action", choices=["list", "collect", "show", "delete"], help="Action")
    fp_parser.add_argument("-n", "--name", help="Fingerprint name")
    fp_parser.add_argument("-p", "--profile-dir", help="Browser profile directory")
    
    # Validate
    validate_parser = subparsers.add_parser("validate", help="Validate sessions")
    validate_parser.add_argument("-d", "--sessions-dir", default="sessions", help="Sessions directory")

    # Export
    export_parser = subparsers.add_parser("export", help="Export session from existing browser")
    export_parser.add_argument("--browser-name", choices=["chrome", "firefox", "edge"], help="Browser name")
    export_parser.add_argument("--browser-path", help="Custom path to browser profile")
    export_parser.add_argument("--profile", help="Profile name within browser")
    export_parser.add_argument("--site", action="append", help="Filter by site (repeatable)")
    export_parser.add_argument("--file-path", help="Export from cookies file")
    export_parser.add_argument("--format", choices=["netscape", "json", "curl"], default="netscape", help="File format")
    export_parser.add_argument("--collect-fingerprint", action="store_true", help="Collect source browser fingerprint")
    export_parser.add_argument("--output", "-o", help="Output .tokenade file path")
    export_parser.add_argument("--list-profiles", action="store_true", help="List available profiles")
    export_parser.add_argument("--decrypt", action="store_true", help="Decrypt cookies (auto-detected)")
    export_parser.add_argument("--extract-local-storage", action="store_true", help="Also extract localStorage data")
    export_parser.add_argument("--local-storage-origin", help="Origin to extract localStorage from (e.g., https://example.com)")

    # Load
    load_parser = subparsers.add_parser("load", help="Load .tokenade file into browser")
    load_parser.add_argument("--file", "-f", required=True, help="Path to .tokenade file")
    load_parser.add_argument("--fingerprint", help="Target fingerprint name")
    load_parser.add_argument("--stealth-level", choices=["basic", "advanced", "maximum"], default="maximum", help="Stealth level")
    load_parser.add_argument("--validate", action="store_true", help="Validate session after injection")
    load_parser.add_argument("--runtime", action="store_true", help="Load into RuntimeEngine")
    load_parser.add_argument("--test-api", action="store_true", help="Test API after loading")
    load_parser.add_argument("--visible", action="store_true", help="Show browser window")
    load_parser.add_argument("--profile-dir", help="Browser profile directory")
    load_parser.add_argument("--no-local-storage", action="store_true", help="Skip localStorage injection if present")

    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    setup_logging(args.verbose)
    
    commands = {
        "setup": cmd_setup,
        "extract": cmd_extract,
        "transfer": cmd_transfer,
        "test": cmd_test,
        "fingerprint": cmd_fingerprint,
        "validate": cmd_validate,
        "export": cmd_export,
        "load": cmd_load,
    }
    
    try:
        commands[args.command](args)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.exception("Command failed")
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
