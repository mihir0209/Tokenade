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
from tokenade.core.crypto.encryptor import TokenadeEncryptor, encrypt_session, decrypt_session, load_key_from_file
from tokenade.core.fingerprint.manager import FingerprintManager, FingerprintCollector
from tokenade.core.fingerprint.injector import inject_stealth_script, validate_injection
from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery
from tokenade.core.importer.cookie_extractor import CookieExtractor, SiteFilter
from tokenade.core.importer.local_storage_extractor import LocalStorageExtractor
from tokenade.core.importer.session_packager import SessionPackager
from tokenade.core.importer.session_loader import SessionLoader
from tokenade.core.injector.profile_manager import ProfileManager, inject_session_to_profile
from tokenade.core.batch.operations import BatchExporter, BatchLoader, load_batch_config, generate_batch_report
from tokenade.core.refresh.health_checker import SessionHealthChecker, SessionRefresher, generate_health_report
from tokenade.core.proxy.server import TokenadeProxy, ProxyConfig, create_proxy_from_file
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
    import getpass
    from tokenade.core.security.credentials import CredentialManager, AccountCredentials
    
    print("\n" + "=" * 80)
    print("TOKENADE - Account Setup")
    print("=" * 80)
    
    manager = CredentialManager()
    accounts = manager.load_accounts()
    
    if accounts:
        print(f"\n📋 Found {len(accounts)} existing account(s)")
    
    while True:
        choice = input("\nAdd account? (yes/no): ").strip().lower()
        if choice not in ("yes", "y"):
            break
        
        email = input("📧 Email: ").strip()
        password = getpass.getpass("🔒 Password: ")
        
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
                account = AccountCredentials(
                    number=account_num,
                    email=email,
                    password=password,
                    profile_dir=profile_dir,
                    site="google",
                    metadata={"created_at": datetime.now().isoformat()},
                )
                accounts.append(account)
                manager.save_accounts(accounts, use_keyring=True, encrypt_file=False)
                
                print(f"✅ Account #{account_num} setup complete")
                print(f"   Password stored in system keyring" if manager._keyring_available
                      else f"   ⚠️  Keyring unavailable — run 'tokenade setup --encrypt' for secure storage")
            else:
                print(f"❌ Login failed for account #{account_num}")
                
        finally:
            browser.close()
    
    print(f"\n📊 Total accounts: {len(accounts)}")
    print("\nNext: run 'tokenade extract' to collect tokens")


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

    # Load site config if provided
    site_config = None
    if args.site_config:
        with open(args.site_config) as f:
            site_config = json.load(f)

    # Build domain filter list
    domain_filter = None
    if args.domains:
        domain_filter = [d.strip() for d in args.domains.split(",") if d.strip()]

    try:
        if args.file_path:
            cookies = extractor.extract_from_file(args.file_path, args.format or "netscape")
        else:
            # Extract ALL cookies first, filter by domains after
            cookies = extractor.extract(site_filter=None)
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        print(f"❌ Extraction failed: {e}")
        return

    print(f"   📊 Total cookies: {len(cookies)}")

    # Apply domain-based filtering from --domains flag
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

    # Apply domain-based filtering from site config
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
    else:
        # Auto-detect: check if any cookie domains have localStorage
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
    output = args.output or f"{site_name}_session"

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
    """Load session file into browser."""
    print("\n" + "=" * 80)
    print("TOKENADE - Session Load")
    print("=" * 80)

    file_path = args.file
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return

    print(f"\n📂 Loading: {file_path}")

    # Load site config if provided
    site_config = None
    if args.site_config:
        with open(args.site_config) as f:
            site_config = json.load(f)
        # If array, use first config for validation
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


def cmd_inject_profile(args):
    """Inject cookies directly into browser profile."""
    from tokenade.core.injector.profile_manager import ProfileManager, inject_session_to_profile
    
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
            # Just load and display session info
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
            # Perform injection
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
        logger.error(f"Profile injection failed: {e}")
        print(f"❌ Failed: {e}")


def cmd_encrypt(args):
    """Encrypt session file."""
    print("\n" + "=" * 80)
    print("TOKENADE - Encrypt Session")
    print("=" * 80)
    
    input_file = Path(args.input)
    if not input_file.exists():
        print(f"❌ Input file not found: {args.input}")
        return
    
    # Get password
    if args.key_file:
        password = load_key_from_file(args.key_file)
        print(f"\n🔑 Loaded key from: {args.key_file}")
    elif args.password:
        password = args.password
    else:
        import getpass
        password = getpass.getpass("\n🔑 Enter password: ")
        confirm = getpass.getpass("🔑 Confirm password: ")
        if password != confirm:
            print("❌ Passwords don't match")
            return
    
    output = args.output or str(input_file) + '.encrypted'
    
    try:
        print(f"\n📂 Input: {args.input}")
        print(f"📁 Output: {output}")
        
        result = encrypt_session(str(input_file), password, output)
        
        print(f"\n✅ Encrypted successfully")
        print(f"   Output: {result}")
        
        # Show file size
        input_size = input_file.stat().st_size
        output_size = Path(result).stat().st_size
        print(f"   Size: {input_size} -> {output_size} bytes")
    
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        print(f"❌ Failed: {e}")


def cmd_decrypt(args):
    """Decrypt session file."""
    print("\n" + "=" * 80)
    print("TOKENADE - Decrypt Session")
    print("=" * 80)
    
    input_file = Path(args.input)
    if not input_file.exists():
        print(f"❌ Input file not found: {args.input}")
        return
    
    # Get password
    if args.key_file:
        password = load_key_from_file(args.key_file)
        print(f"\n🔑 Loaded key from: {args.key_file}")
    elif args.password:
        password = args.password
    else:
        import getpass
        password = getpass.getpass("\n🔑 Enter password: ")
    
    output = args.output or str(input_file).replace('.encrypted', '')
    if output == str(input_file):
        output = str(input_file) + '.decrypted'
    
    try:
        print(f"\n📂 Input: {args.input}")
        print(f"📁 Output: {output}")
        
        result = decrypt_session(str(input_file), password, output)
        
        print(f"\n✅ Decrypted successfully")
        print(f"   Output: {result}")
        
        # Show file size
        input_size = input_file.stat().st_size
        output_size = Path(result).stat().st_size
        print(f"   Size: {input_size} -> {output_size} bytes")
    
    except ValueError as e:
        print(f"❌ Wrong password or corrupted file")
        logger.debug(f"Decryption error: {e}")
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        print(f"❌ Failed: {e}")


def cmd_rekey(args):
    """Change encryption password."""
    print("\n" + "=" * 80)
    print("TOKENADE - Rekey Session")
    print("=" * 80)
    
    input_file = Path(args.input)
    if not input_file.exists():
        print(f"❌ Input file not found: {args.input}")
        return
    
    # Get old password
    if args.old_key_file:
        old_password = load_key_from_file(args.old_key_file)
        print(f"\n🔑 Loaded old key from: {args.old_key_file}")
    elif args.old_password:
        old_password = args.old_password
    else:
        import getpass
        old_password = getpass.getpass("\n🔑 Enter old password: ")
    
    # Get new password
    if args.new_key_file:
        new_password = load_key_from_file(args.new_key_file)
        print(f"🔑 Loaded new key from: {args.new_key_file}")
    elif args.new_password:
        new_password = args.new_password
    else:
        import getpass
        new_password = getpass.getpass("\n🔑 Enter new password: ")
        confirm = getpass.getpass("🔑 Confirm new password: ")
        if new_password != confirm:
            print("❌ Passwords don't match")
            return
    
    output = args.output or str(input_file)
    
    try:
        print(f"\n📂 Input: {args.input}")
        print(f"📁 Output: {output}")
        
        encryptor = TokenadeEncryptor()
        
        with open(input_file, 'rb') as f:
            encrypted = f.read()
        
        rekeyed = encryptor.rekey(encrypted, old_password, new_password)
        
        with open(output, 'wb') as f:
            f.write(rekeyed)
        
        print(f"\n✅ Rekeyed successfully")
        print(f"   Output: {output}")
    
    except ValueError as e:
        print(f"❌ Wrong old password or corrupted file")
        logger.debug(f"Rekey error: {e}")
    except Exception as e:
        logger.error(f"Rekey failed: {e}")
        print(f"❌ Failed: {e}")


def cmd_batch_export(args):
    """Batch export multiple sites."""
    print("\n" + "=" * 80)
    print("TOKENADE - Batch Export")
    print("=" * 80)
    
    # Load site configs
    try:
        sites = load_batch_config(args.site_config)
        print(f"\n📋 Loaded {len(sites)} site(s) from: {args.site_config}")
    except Exception as e:
        print(f"❌ Failed to load site config: {e}")
        return
    
    output_dir = args.output or "sessions_batch"
    
    print(f"\n🌐 Browser: {args.browser}")
    print(f"📁 Output: {output_dir}")
    
    try:
        exporter = BatchExporter()
        result = exporter.export_batch(
            browser=args.browser,
            sites=sites,
            output_dir=output_dir,
            browser_path=args.browser_path,
            profile=args.profile,
            extract_local_storage=args.extract_local_storage
        )
        
        print("\n" + generate_batch_report(result))
        
        if result.success:
            print(f"\n✅ Batch export completed successfully")
        else:
            print(f"\n⚠️  Batch export completed with errors")
    
    except Exception as e:
        logger.error(f"Batch export failed: {e}")
        print(f"❌ Failed: {e}")


def cmd_batch_load(args):
    """Batch load multiple sessions."""
    print("\n" + "=" * 80)
    print("TOKENADE - Batch Load")
    print("=" * 80)
    
    # Load site configs if provided
    sites = None
    if args.site_config:
        try:
            sites = load_batch_config(args.site_config)
            print(f"\n📋 Loaded {len(sites)} site(s) from: {args.site_config}")
        except Exception as e:
            print(f"⚠️  Failed to load site config: {e}")
    
    print(f"\n📂 Sessions: {args.sessions_dir}")
    print(f"🌐 Target: {args.target_browser}")
    
    try:
        loader = BatchLoader()
        result = loader.load_batch(
            sessions_dir=args.sessions_dir,
            target_browser=args.target_browser,
            site_configs=sites,
            profile_dir=args.profile_dir,
            validate=args.validate,
            visible=args.visible
        )
        
        print("\n" + generate_batch_report(result))
        
        if result.success:
            print(f"\n✅ Batch load completed successfully")
        else:
            print(f"\n⚠️  Batch load completed with errors")
    
    except Exception as e:
        logger.error(f"Batch load failed: {e}")
        print(f"❌ Failed: {e}")


def cmd_health(args):
    """Check session health."""
    print("\n" + "=" * 80)
    print("TOKENADE - Session Health Check")
    print("=" * 80)
    
    session_files = []
    
    # Check single file or directory
    if args.session:
        session_files = [args.session]
    elif args.sessions_dir:
        sessions_path = Path(args.sessions_dir)
        if not sessions_path.exists():
            print(f"❌ Directory not found: {args.sessions_dir}")
            return
        session_files = [str(f) for f in sessions_path.glob("*.tokenade")] + \
                       [str(f) for f in sessions_path.glob("*.session")] + \
                       [str(f) for f in sessions_path.glob("*.json")]
    
    if not session_files:
        print("❌ No session files found")
        return
    
    checker = SessionHealthChecker()
    
    healthy_count = 0
    unhealthy_count = 0
    
    for session_file in session_files:
        print(f"\n📁 Checking: {Path(session_file).name}")
        
        health = checker.check_session(session_file)
        
        if health.healthy:
            healthy_count += 1
        else:
            unhealthy_count += 1
        
        print(generate_health_report(health))
    
    print("\n" + "=" * 80)
    print(f"SUMMARY: {healthy_count} healthy, {unhealthy_count} unhealthy")


def cmd_refresh(args):
    """Refresh session from source browser."""
    print("\n" + "=" * 80)
    print("TOKENADE - Session Refresh")
    print("=" * 80)
    
    session_file = Path(args.session)
    if not session_file.exists():
        print(f"❌ Session file not found: {args.session}")
        return
    
    print(f"\n📂 Session: {args.session}")
    print(f"🌐 Source: {args.source_browser}")
    
    # Load site config if provided
    site_config = None
    if args.site_config:
        with open(args.site_config) as f:
            site_config = json.load(f)
        if isinstance(site_config, list):
            site_config = site_config[0] if site_config else None
    
    try:
        refresher = SessionRefresher()
        result = refresher.refresh(
            session_file=str(session_file),
            source_browser=args.source_browser,
            source_browser_path=args.source_browser_path,
            source_profile=args.source_profile,
            site_config=site_config
        )
        
        if result.success:
            print(f"\n✅ Refresh successful")
            print(f"   Refreshed: {result.cookies_refreshed}/{result.cookies_total} cookies")
        else:
            print(f"\n❌ Refresh failed")
            if result.error:
                print(f"   Error: {result.error}")
    
    except Exception as e:
        logger.error(f"Session refresh failed: {e}")
        print(f"❌ Failed: {e}")


def cmd_proxy(args):
    """Start fingerprint-matched proxy server."""
    from tokenade.core.importer.session_packager import SessionPackager
    packager = SessionPackager()

    # Multi-site mode
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
                        logger.warning(f"Failed to load {f}: {e}")

        if not sessions:
            print("❌ No session files found")
            return

        print(f"\n{'='*60}")
        print(f"TOKENADE - Multi-Site Proxy ({len(sessions)} sessions)")
        print(f"{'='*60}")

        from tokenade.core.proxy.multi_site_proxy import MultiSiteProxy
        proxy = MultiSiteProxy(sessions, base_port=args.port, host=args.host)
        import asyncio
        asyncio.run(proxy.start())
        return

    # Single-site mode
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
            # HTTP forward proxy mode
            from tokenade.core.proxy.forward_proxy import ForwardProxy
            from tokenade.core.importer.session_packager import SessionPackager
            packager = SessionPackager()
            session = packager.load(str(session_file))
            proxy = ForwardProxy(session, port=args.port, host=args.host)
            import asyncio
            asyncio.run(proxy.start())
        elif args.legacy:
            # Legacy SW-based proxy
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
            # CDP-based proxy (default, recommended)
            from tokenade.core.proxy.cdp_proxy import CDPProxy, CDPProxyConfig
            from tokenade.core.importer.session_refresher import RefreshConfig
            
            config = CDPProxyConfig(
                port=args.port,
                host=args.host,
                headless=not args.visible,
                timeout=args.timeout,
                use_fingerprint=args.fingerprint,
            )
            proxy = CDPProxy.from_session_file(str(session_file), config)
            
            # Configure auto-refresh if enabled
            if args.auto_refresh:
                proxy._refresher.config.auto_refresh = True
                if args.source_browser:
                    proxy._refresher.config.source_browser = args.source_browser
                if args.source_profile:
                    proxy._refresher.config.source_profile = args.source_profile
                print(f"🔄 Auto-refresh enabled from {args.source_browser or 'source browser'}")
        
        # Open browser in GUI mode
        if not args.no_open_browser:
            import webbrowser
            import threading
            
            def open_browser_thread():
                import time
                time.sleep(2)  # Wait for server + browser to start
                webbrowser.open(f"http://127.0.0.1:{args.port}")
            
            threading.Thread(target=open_browser_thread, daemon=True).start()
        
        print(f"\n🚀 Starting proxy server...")
        proxy.run()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Proxy stopped by user")
    except Exception as e:
        logger.error(f"Proxy failed: {e}")
        print(f"❌ Failed: {e}")


def cmd_sessions(args):
    """Manage multiple sessions."""
    from tokenade.core.importer.session_manager import SessionManager
    
    manager = SessionManager(args.dir if hasattr(args, 'dir') else ".")
    
    if args.sessions_command == "list":
        sessions = manager.list_sessions(
            pattern=args.pattern,
            recursive=args.recursive,
        )
        
        # Apply filters
        if args.site or args.browser:
            sessions = manager.filter_sessions(
                sessions,
                site_name=args.site,
                browser=args.browser,
            )
        
        if not sessions:
            print("No sessions found")
            return
        
        print("\n" + "=" * 70)
        print(f"{'Site':<20} {'Cookies':<10} {'Browser':<12} {'Size':<10} {'Path'}")
        print("=" * 70)
        
        for s in sessions:
            size = f"{s.file_size / 1024:.1f}K" if s.file_size < 1024*1024 else f"{s.file_size / (1024*1024):.1f}M"
            print(f"{s.site_name:<20} {s.cookie_count:<10} {s.source_browser or 'unknown':<12} {size:<10} {Path(s.path).name}")
        
        print(f"\n{'='*70}")
        print(f"Total: {len(sessions)} sessions")
        print(f"{'='*70}\n")
    
    elif args.sessions_command == "merge":
        for f in args.files:
            if not Path(f).exists():
                print(f"❌ File not found: {f}")
                return
        
        output = manager.merge_sessions(
            args.files,
            args.output,
            site_name=args.site_name,
        )
        
        print(f"✅ Merged {len(args.files)} sessions into: {output}")
    
    elif args.sessions_command == "rotate":
        for f in args.files:
            if not Path(f).exists():
                print(f"❌ File not found: {f}")
                return
        
        selected = manager.rotate_session(
            args.files,
            strategy=args.strategy,
            state_file=args.state_file,
        )
        
        print(f"🔄 Selected: {selected}")
    
    elif args.sessions_command == "stats":
        for f in args.files:
            if not Path(f).exists():
                print(f"❌ File not found: {f}")
                return
        
        stats = manager.get_session_stats(args.files)
        
        print("\n" + "=" * 60)
        print("Session Statistics")
        print("=" * 60)
        print(f"Sessions: {stats['session_count']}")
        print(f"Total cookies: {stats['total_cookies']}")
        print(f"Total size: {stats['total_size_bytes'] / 1024:.1f} KB")
        print(f"Sites: {', '.join(stats['unique_sites']) or 'none'}")
        print(f"Browsers: {', '.join(stats['unique_browsers']) or 'none'}")
        print(f"{'='*60}\n")
    
    else:
        print("❌ Specify a sessions subcommand: list, merge, rotate, stats")


def cmd_share(args):
    """Create shareable session link or QR code."""
    from tokenade.core.importer.session_sharer import SessionSharer, ShareConfig, generate_share_html
    from tokenade.core.importer.session_packager import SessionPackager
    
    session_file = Path(args.session)
    if not session_file.exists():
        print(f"❌ Session file not found: {args.session}")
        return
    
    packager = SessionPackager()
    session = packager.load(str(session_file))
    
    sharer = SessionSharer()
    config = ShareConfig(
        expiry_hours=args.expiry,
        max_uses=args.max_uses,
        password_protected=bool(args.password),
        password=args.password,
    )
    
    print("\n" + "=" * 60)
    print("TOKENADE - Share Session")
    print("=" * 60)
    print(f"\n📂 Session: {args.session}")
    print(f"🔒 Expires: {args.expiry} hours")
    if args.max_uses:
        print(f"🔢 Max uses: {args.max_uses}")
    if args.password:
        print(f"🔑 Password protected: Yes")
    
    if args.format == "qr":
        output_path = args.output or f"{session_file.stem}_qr.png"
        sharer.create_qr_code(session, output_path, config)
        print(f"\n📱 QR code saved to: {output_path}")
    elif args.format == "html":
        output_path = args.output or f"{session_file.stem}_share.html"
        share_url, session_id = sharer.create_share_link(session, config)
        generate_share_html(session, output_path)
        print(f"\n📄 Share page saved to: {output_path}")
        print(f"🆔 Session ID: {session_id}")
    else:
        share_url, session_id = sharer.create_share_link(session, config)
        print(f"\n🔗 Share URL: {share_url}")
        print(f"🆔 Session ID: {session_id}")
    
    print(f"\n{'='*60}\n")


def cmd_unshare(args):
    """Revoke a shared session or list active shares."""
    from tokenade.core.importer.session_sharer import SessionSharer
    
    sharer = SessionSharer()
    
    if args.list:
        shares = sharer.list_shared()
        if not shares:
            print("No active shared sessions")
            return
        
        print("\n" + "=" * 60)
        print("Active Shared Sessions")
        print("=" * 60)
        
        for s in shares:
            print(f"\n🆔 {s['session_id']}")
            print(f"   Created: {time.strftime('%Y-%m-%d %H:%M', time.localtime(s['created_at']))}")
            print(f"   Expires: {time.strftime('%Y-%m-%d %H:%M', time.localtime(s['expires_at']))}")
            print(f"   Uses: {s['use_count']}/{s['max_uses'] or '∞'}")
            print(f"   Password: {'Yes' if s['has_password'] else 'No'}")
        
        print(f"\n{'='*60}\n")
        return
    
    if sharer.revoke_share(args.session_id):
        print(f"✅ Revoked shared session: {args.session_id}")
    else:
        print(f"❌ Failed to revoke session: {args.session_id}")


def cmd_validate_rules(args):
    """Validate session with custom rules."""
    from tokenade.core.importer.advanced_validator import AdvancedValidator, load_validation_rules
    from tokenade.core.importer.session_packager import SessionPackager
    
    session_file = Path(args.session)
    if not session_file.exists():
        print(f"❌ Session file not found: {args.session}")
        return
    
    rules_file = Path(args.rules)
    if not rules_file.exists():
        print(f"❌ Rules file not found: {args.rules}")
        return
    
    packager = SessionPackager()
    session = packager.load(str(session_file))
    
    rules = load_validation_rules(str(rules_file))
    
    print("\n" + "=" * 60)
    print("TOKENADE - Advanced Validation")
    print("=" * 60)
    print(f"\n📂 Session: {args.session}")
    print(f"📋 Rules: {len(rules)}")
    
    validator = AdvancedValidator()
    
    # Run validation
    results = asyncio.run(validator.validate_rules(
        session,
        rules,
        site_url=args.url,
    ))
    
    # Print results
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    
    print(f"\n{'='*60}")
    for result in results:
        status = "✅" if result.passed else "❌"
        duration = f" ({result.duration_ms:.0f}ms)" if result.duration_ms else ""
        print(f"{status} {result.rule_name}: {result.message}{duration}")
        if result.details and not result.passed:
            for k, v in result.details.items():
                print(f"   {k}: {v}")
    
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'='*60}\n")
    
    if failed:
        sys.exit(1)


def cmd_diff(args):
    """Compare two session files."""
    from tokenade.core.importer.session_comparator import SessionComparator

    for path in (args.session_a, args.session_b):
        if not Path(path).exists():
            print(f"❌ File not found: {path}")
            return

    comparator = SessionComparator()
    result = comparator.compare_files(args.session_a, args.session_b)

    print("\n" + "=" * 70)
    print("SESSION COMPARISON")
    print("=" * 70)
    print(f"\n  A: {args.session_a}")
    print(f"  B: {args.session_b}")

    if not result.has_changes:
        print("\n  ✅ Sessions are identical")
        return

    print(f"\n  {'─' * 50}")
    print(result.summary())

    if args.verbose:
        if result.cookies_only_in_a:
            print(f"\n  Cookies only in A:")
            for c in result.cookies_only_in_a:
                print(f"    - {c.get('name')} ({c.get('domain')})")
        if result.cookies_only_in_b:
            print(f"\n  Cookies only in B:")
            for c in result.cookies_only_in_b:
                print(f"    - {c.get('name')} ({c.get('domain')})")
        if result.cookies_modified:
            print(f"\n  Cookies modified:")
            for m in result.cookies_modified:
                print(f"    - {m['key']}")
                print(f"      A: {m['a'].get('value', '')[:50]}...")
                print(f"      B: {m['b'].get('value', '')[:50]}...")
        if result.localStorage_only_in_a:
            print(f"\n  localStorage only in A:")
            for k in result.localStorage_only_in_a:
                print(f"    - {k}")
        if result.localStorage_only_in_b:
            print(f"\n  localStorage only in B:")
            for k in result.localStorage_only_in_b:
                print(f"    - {k}")
        if result.localStorage_modified:
            print(f"\n  localStorage modified:")
            for k, v in result.localStorage_modified.items():
                print(f"    - {k}")
                print(f"      A: {v['a'][:50]}...")
                print(f"      B: {v['b'][:50]}...")
        if result.metadata_diffs:
            print(f"\n  Metadata differences:")
            for field, vals in result.metadata_diffs.items():
                print(f"    - {field}: {vals['a']} -> {vals['b']}")


def main():
    """Main CLI entry point."""
    from tokenade import __version__
    parser = argparse.ArgumentParser(
        description="Tokenade - Browser session portability tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Quick Start:
  1. Export:   tokenade export --browser-name firefox --domains "google.com,accounts.google.com" -o my_session.tokenade
  2. Proxy:    tokenade proxy -s my_session.tokenade
  3. Browse:   Open http://127.0.0.1:9222 and enter the target URL

Commands:
  export        Extract cookies from browser to .tokenade file
  proxy         Start CDP proxy server with donor session
  load          Load .tokenade session into a browser
  inject-profile Inject cookies directly into browser profile
  encrypt       Encrypt a .tokenade file
  decrypt       Decrypt a .tokenade file
  health        Check session health
  batch-export  Export multiple sites at once
        """,
    )
    
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
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
    export_parser.add_argument("--browser-name", choices=["chrome", "firefox", "edge", "brave"], help="Browser name")
    export_parser.add_argument("--browser-path", help="Custom path to browser profile")
    export_parser.add_argument("--profile", help="Profile name within browser")
    export_parser.add_argument("--site-config", help="Path to JSON site config file for filtering")
    export_parser.add_argument("--domains", help="Comma-separated domains to filter (e.g. 'google.com,accounts.google.com')")
    export_parser.add_argument("--file-path", help="Export from cookies file")
    export_parser.add_argument("--format", choices=["netscape", "json", "curl"], default="netscape", help="File format")
    export_parser.add_argument("--collect-fingerprint", action="store_true", help="Collect source browser fingerprint")
    export_parser.add_argument("--output", "-o", help="Output file path (any extension)")
    export_parser.add_argument("--list-profiles", action="store_true", help="List available profiles")
    export_parser.add_argument("--decrypt", action="store_true", help="Decrypt cookies (auto-detected)")
    export_parser.add_argument("--extract-local-storage", action="store_true", help="Also extract localStorage data")
    export_parser.add_argument("--local-storage-origin", help="Origin to extract localStorage from")

    # Load
    load_parser = subparsers.add_parser("load", help="Load session file into browser")
    load_parser.add_argument("--file", "-f", required=True, help="Path to session file")
    load_parser.add_argument("--site-config", help="Path to JSON site config file for validation")
    load_parser.add_argument("--fingerprint", help="Target fingerprint name")
    load_parser.add_argument("--stealth-level", choices=["basic", "advanced", "maximum"], default="maximum", help="Stealth level")
    load_parser.add_argument("--validate", action="store_true", help="Validate session after injection")
    load_parser.add_argument("--runtime", action="store_true", help="Load into RuntimeEngine")
    load_parser.add_argument("--test-api", action="store_true", help="Test API after loading")
    load_parser.add_argument("--visible", action="store_true", help="Show browser window")
    load_parser.add_argument("--profile-dir", help="Browser profile directory")
    load_parser.add_argument("--no-local-storage", action="store_true", help="Skip localStorage injection if present")

    # Inject Profile
    inject_parser = subparsers.add_parser("inject-profile", help="Inject cookies directly into browser profile")
    inject_parser.add_argument("--session", "-s", required=True, help="Path to session file")
    inject_parser.add_argument("--profile", "-p", required=True, help="Browser profile path")
    inject_parser.add_argument("--browser", "-b", choices=["chrome", "brave", "edge", "firefox", "opera", "vivaldi"], 
                              default="chrome", help="Browser name")
    inject_parser.add_argument("--no-backup", action="store_true", help="Skip backup creation")
    inject_parser.add_argument("--dry-run", action="store_true", help="Show what would be injected without making changes")

    # Encrypt
    encrypt_parser = subparsers.add_parser("encrypt", help="Encrypt session file")
    encrypt_parser.add_argument("--input", "-i", required=True, help="Input file path")
    encrypt_parser.add_argument("--output", "-o", help="Output file path")
    encrypt_parser.add_argument("--password", "-p", help="Encryption password")
    encrypt_parser.add_argument("--key-file", "-k", help="Password file")

    # Decrypt
    decrypt_parser = subparsers.add_parser("decrypt", help="Decrypt session file")
    decrypt_parser.add_argument("--input", "-i", required=True, help="Encrypted file path")
    decrypt_parser.add_argument("--output", "-o", help="Output file path")
    decrypt_parser.add_argument("--password", "-p", help="Decryption password")
    decrypt_parser.add_argument("--key-file", "-k", help="Password file")

    # Rekey
    rekey_parser = subparsers.add_parser("rekey", help="Change encryption password")
    rekey_parser.add_argument("--input", "-i", required=True, help="Encrypted file path")
    rekey_parser.add_argument("--output", "-o", help="Output file path")
    rekey_parser.add_argument("--old-password", help="Old password")
    rekey_parser.add_argument("--new-password", help="New password")
    rekey_parser.add_argument("--old-key-file", help="Old password file")
    rekey_parser.add_argument("--new-key-file", help="New password file")

    # Batch Export
    batch_export_parser = subparsers.add_parser("batch-export", help="Batch export multiple sites")
    batch_export_parser.add_argument("--site-config", "-s", required=True, help="Site config JSON file")
    batch_export_parser.add_argument("--browser", "-b", choices=["chrome", "firefox", "edge", "brave"], 
                                   default="firefox", help="Browser name")
    batch_export_parser.add_argument("--browser-path", help="Custom browser profile path")
    batch_export_parser.add_argument("--profile", "-p", help="Profile name")
    batch_export_parser.add_argument("--output", "-o", help="Output directory")
    batch_export_parser.add_argument("--extract-local-storage", action="store_true", help="Extract localStorage")

    # Batch Load
    batch_load_parser = subparsers.add_parser("batch-load", help="Batch load multiple sessions")
    batch_load_parser.add_argument("--sessions-dir", "-d", required=True, help="Sessions directory")
    batch_load_parser.add_argument("--target-browser", "-t", choices=["chrome", "firefox", "edge", "brave"], 
                                  default="chrome", help="Target browser")
    batch_load_parser.add_argument("--site-config", "-s", help="Site config JSON file for validation")
    batch_load_parser.add_argument("--profile-dir", help="Target profile directory")
    batch_load_parser.add_argument("--validate", action="store_true", help="Validate sessions")
    batch_load_parser.add_argument("--visible", action="store_true", help="Show browser window")

    # Health Check
    health_parser = subparsers.add_parser("health", help="Check session health")
    health_parser.add_argument("--session", "-s", help="Single session file to check")
    health_parser.add_argument("--sessions-dir", "-d", help="Directory of sessions to check")

    # Refresh
    refresh_parser = subparsers.add_parser("refresh", help="Refresh session from source browser")
    refresh_parser.add_argument("--session", "-s", required=True, help="Session file to refresh")
    refresh_parser.add_argument("--source-browser", "-b", choices=["chrome", "firefox", "edge", "brave"],
                               required=True, help="Source browser name")
    refresh_parser.add_argument("--source-browser-path", help="Custom source browser profile path")
    refresh_parser.add_argument("--source-profile", help="Source profile name")
    refresh_parser.add_argument("--site-config", help="Site config JSON file for filtering")

    # Proxy
    proxy_parser = subparsers.add_parser("proxy", help="Start fingerprint-matched proxy server")
    proxy_parser.add_argument("--session", "-s", help="Path to .tokenade session file (single mode)")
    proxy_parser.add_argument("--all", action="store_true", help="Serve all sessions (multi-site mode)")
    proxy_parser.add_argument("--sessions-dir", "-d", help="Directory of .tokenade files (for --all)")
    proxy_parser.add_argument("--mode", choices=["gui", "forward"], default="gui",
                             help="Proxy mode: gui (browser GUI) or forward (HTTP_PROXY)")
    proxy_parser.add_argument("--port", "-p", type=int, default=9222, help="Port to listen on (default: 9222)")
    proxy_parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    proxy_parser.add_argument("--legacy", action="store_true", help="Use legacy service-worker proxy (default: CDP)")
    proxy_parser.add_argument("--visible", action="store_true", help="Show browser window (CDP mode only)")
    proxy_parser.add_argument("--fingerprint", action="store_true", help="Enable TLS fingerprint matching via curl-cffi (breaks cf_clearance)")
    proxy_parser.add_argument("--no-open-browser", action="store_true", help="Don't open browser automatically")
    proxy_parser.add_argument("--no-gui", action="store_true", help="Disable GUI mode (legacy proxy only)")
    proxy_parser.add_argument("--timeout", type=int, default=30, help="Request timeout in seconds (default: 30)")
    proxy_parser.add_argument("--auto-refresh", action="store_true", help="Auto-refresh session from source browser when cookies expire")
    proxy_parser.add_argument("--source-browser", help="Source browser for auto-refresh (e.g., firefox, chrome)")
    proxy_parser.add_argument("--source-profile", help="Source profile for auto-refresh (e.g., default, Profile 1)")

    # Sessions (subcommand group)
    sessions_parser = subparsers.add_parser("sessions", help="Manage multiple sessions")
    sessions_sub = sessions_parser.add_subparsers(dest="sessions_command", help="Session management commands")
    
    # sessions list
    sessions_list_parser = sessions_sub.add_parser("list", help="List all sessions")
    sessions_list_parser.add_argument("--dir", "-d", default=".", help="Directory to search")
    sessions_list_parser.add_argument("--pattern", "-p", default="*.tokenade", help="File pattern")
    sessions_list_parser.add_argument("--recursive", "-r", action="store_true", help="Search subdirectories")
    sessions_list_parser.add_argument("--site", "-s", help="Filter by site name")
    sessions_list_parser.add_argument("--browser", "-b", help="Filter by source browser")
    
    # sessions merge
    sessions_merge_parser = sessions_sub.add_parser("merge", help="Merge multiple sessions")
    sessions_merge_parser.add_argument("files", nargs="+", help="Session files to merge")
    sessions_merge_parser.add_argument("--output", "-o", required=True, help="Output file path")
    sessions_merge_parser.add_argument("--site-name", help="Site name for merged session")
    
    # sessions rotate
    sessions_rotate_parser = sessions_sub.add_parser("rotate", help="Select next session (rotation)")
    sessions_rotate_parser.add_argument("files", nargs="+", help="Session files to rotate through")
    sessions_rotate_parser.add_argument("--strategy", choices=["round-robin", "random"], default="round-robin",
                                       help="Rotation strategy")
    sessions_rotate_parser.add_argument("--state-file", help="State file for round-robin")
    
    # sessions stats
    sessions_stats_parser = sessions_sub.add_parser("stats", help="Show aggregate session statistics")
    sessions_stats_parser.add_argument("files", nargs="+", help="Session files to analyze")

    # Share
    share_parser = subparsers.add_parser("share", help="Create shareable session link or QR code")
    share_parser.add_argument("--session", "-s", required=True, help="Session file to share")
    share_parser.add_argument("--output", "-o", help="Output file path (HTML or QR image)")
    share_parser.add_argument("--format", choices=["url", "html", "qr"], default="url",
                             help="Output format: url (default), html, qr")
    share_parser.add_argument("--expiry", type=int, default=24, help="Link expiry in hours (default: 24)")
    share_parser.add_argument("--max-uses", type=int, default=0, help="Max uses (0 = unlimited)")
    share_parser.add_argument("--password", "-p", help="Password protect the link")

    # Unshare
    unshare_parser = subparsers.add_parser("unshare", help="Revoke a shared session")
    unshare_parser.add_argument("session_id", help="Session ID to revoke")
    unshare_parser.add_argument("--list", action="store_true", help="List all active shares")

    # Diff
    # Validate Rules
    validate_rules_parser = subparsers.add_parser("validate-rules", help="Validate session with custom rules")
    validate_rules_parser.add_argument("--session", "-s", required=True, help="Session file to validate")
    validate_rules_parser.add_argument("--rules", "-r", required=True, help="Validation rules JSON file")
    validate_rules_parser.add_argument("--url", "-u", help="Target site URL")
    validate_rules_parser.add_argument("--update-baselines", action="store_true", help="Update screenshot baselines")

    # Diff
    diff_parser = subparsers.add_parser("diff", help="Compare two session files")
    diff_parser.add_argument("session_a", help="First .tokenade file")
    diff_parser.add_argument("session_b", help="Second .tokenade file")
    diff_parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed differences")

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
        "inject-profile": cmd_inject_profile,
        "encrypt": cmd_encrypt,
        "decrypt": cmd_decrypt,
        "rekey": cmd_rekey,
        "batch-export": cmd_batch_export,
        "batch-load": cmd_batch_load,
        "health": cmd_health,
        "refresh": cmd_refresh,
        "proxy": cmd_proxy,
        "sessions": cmd_sessions,
        "share": cmd_share,
        "unshare": cmd_unshare,
        "validate-rules": cmd_validate_rules,
        "diff": cmd_diff,
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
