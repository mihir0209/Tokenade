"""Advanced CLI commands."""
import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger("tokenade")


def cmd_batch_export(args):
    """Batch export multiple sites."""
    from tokenade.core.batch.operations import BatchExporter, load_batch_config, generate_batch_report

    print("\n" + "=" * 80)
    print("TOKENADE - Batch Export")
    print("=" * 80)

    try:
        sites = load_batch_config(args.site_config)
        print(f"\n📋 Loaded {len(sites)} site(s) from: {args.site_config}")
    except Exception as e:
        logger.error(f"Failed to load site config: {e}", exc_info=True)
        print("❌ Failed to load site config — verify JSON format is valid")
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
            print("\n✅ Batch export completed successfully")
        else:
            print("\n⚠️  Batch export completed with errors")

    except Exception as e:
        logger.error(f"Batch export failed: {e}", exc_info=True)
        print("❌ Batch export failed — check browser profile and output directory")


def cmd_batch_load(args):
    """Batch load multiple sessions."""
    from tokenade.core.batch.operations import BatchLoader, load_batch_config, generate_batch_report

    print("\n" + "=" * 80)
    print("TOKENADE - Batch Load")
    print("=" * 80)

    sites = None
    if args.site_config:
        try:
            sites = load_batch_config(args.site_config)
            print(f"\n📋 Loaded {len(sites)} site(s) from: {args.site_config}")
        except Exception as e:
            logger.error(f"Failed to load site config: {e}", exc_info=True)
            print("⚠️  Failed to load site config — verify JSON format")

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
            print("\n✅ Batch load completed successfully")
        else:
            print("\n⚠️  Batch load completed with errors")

    except Exception as e:
        logger.error(f"Batch load failed: {e}", exc_info=True)
        print("❌ Batch load failed — check sessions directory and target browser")


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

    # Prefer product extension; also accept legacy .json dumps
    session_files = sorted(
        set(sessions_dir.glob("*.tokenade")) | set(sessions_dir.glob("*.json"))
    )
    if not session_files:
        print(f"\n⚠️  No .tokenade or .json sessions in {sessions_dir}")
        print("📊 Summary: 0 valid, 0 invalid")
        return

    for session_file in session_files:
        print(f"\n📁 Checking: {session_file.name}")

        try:
            with open(session_file) as f:
                data = json.load(f)

            # auth_state is historical; auth_status is v3 packager naming
            if "auth_status" not in data and "auth_state" in data:
                data = dict(data)
                data["auth_status"] = data["auth_state"]

            required = ["site_name", "cookies"]
            missing = [f for f in required if f not in data]
            if "auth_status" not in data and "auth_state" not in data:
                missing.append("auth_status|auth_state")

            if missing:
                print(f"   ❌ Missing fields: {missing}")
                invalid += 1
                continue

            cookies = data.get("cookies", [])
            if not cookies:
                print("   ⚠️  No cookies")
            else:
                print(f"   ✅ {len(cookies)} cookies")

            tokens = data.get("tokens", [])
            if tokens:
                print(f"   ✅ {len(tokens)} tokens")

            status = data.get("auth_status") or data.get("auth_state") or "unknown"
            if status == "logged_in":
                print("   ✅ Status: logged_in")
                valid += 1
            else:
                print(f"   ⚠️  Status: {status}")
                invalid += 1

        except Exception as e:
            logger.debug(f"Validation error: {e}", exc_info=True)
            print("   ❌ Validation error — session may be corrupted")
            invalid += 1

    print(f"\n📊 Summary: {valid} valid, {invalid} invalid")


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

    results = asyncio.run(validator.validate_rules(
        session,
        rules,
        site_url=args.url,
    ))

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)

    print(f"\n{'=' * 60}")
    for result in results:
        status = "✅" if result.passed else "❌"
        duration = f" ({result.duration_ms:.0f}ms)" if result.duration_ms else ""
        print(f"{status} {result.rule_name}: {result.message}{duration}")
        if result.details and not result.passed:
            for k, v in result.details.items():
                print(f"   {k}: {v}")

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'=' * 60}\n")

    if failed:
        import sys
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
            print("\n  Cookies only in A:")
            for c in result.cookies_only_in_a:
                print(f"    - {c.get('name')} ({c.get('domain')})")
        if result.cookies_only_in_b:
            print("\n  Cookies only in B:")
            for c in result.cookies_only_in_b:
                print(f"    - {c.get('name')} ({c.get('domain')})")
        if result.cookies_modified:
            print("\n  Cookies modified:")
            for m in result.cookies_modified:
                print(f"    - {m['key']}")
                print(f"      A: {m['a'].get('value', '')[:50]}...")
                print(f"      B: {m['b'].get('value', '')[:50]}...")
        if result.localStorage_only_in_a:
            print("\n  localStorage only in A:")
            for k in result.localStorage_only_in_a:
                print(f"    - {k}")
        if result.localStorage_only_in_b:
            print("\n  localStorage only in B:")
            for k in result.localStorage_only_in_b:
                print(f"    - {k}")
        if result.localStorage_modified:
            print("\n  localStorage modified:")
            for k, v in result.localStorage_modified.items():
                print(f"    - {k}")
                print(f"      A: {v['a'][:50]}...")
                print(f"      B: {v['b'][:50]}...")
        if result.metadata_diffs:
            print("\n  Metadata differences:")
            for field, vals in result.metadata_diffs.items():
                print(f"    - {field}: {vals['a']} -> {vals['b']}")


def cmd_fingerprint(args):
    """Manage browser fingerprints."""
    from tokenade.core.browser.manager import BrowserFactory, BrowserConfig
    from tokenade.core.fingerprint.manager import FingerprintManager, FingerprintCollector

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


def cmd_test(args):
    """Run portability tests with fingerprint spoofing."""
    from tokenade.core.browser.manager import BrowserFactory, BrowserConfig
    from tokenade.core.fingerprint.manager import FingerprintManager
    from tokenade.core.fingerprint.injector import validate_injection
    from tokenade.handlers.resolve import resolve_legacy_handler_class
    from tokenade.tests.portability import PortabilityTester

    print("\n" + "=" * 80)
    print("TOKENADE - Portability Test")
    print("=" * 80)

    session_file = Path(args.session)
    if not session_file.exists():
        print(f"❌ Session file not found: {args.session}")
        raise SystemExit(1)

    with open(session_file) as f:
        session_data = json.load(f)

    handler_class = resolve_legacy_handler_class(session_data.get("site_name"))
    hname = getattr(handler_class, "__name__", str(handler_class))
    print(
        f"\n⚠️  Using legacy handler {hname} "
        f"(prefer site plugins + site_config.json for new work)"
    )

    fp_manager = FingerprintManager()
    tester = PortabilityTester(BrowserFactory, fp_manager)

    print(f"\n🛡️  Stealth level: {args.stealth_level}")

    if args.variations:
        print("\n🧪 Testing fingerprint variations...")
        tester.test_fingerprint_variations(
            session_data=session_data,
            base_fp_name=args.source_fp or "default",
            handler_class=handler_class,
        )
    else:
        print(f"\n🧪 Testing transfer to: {args.target_fp}")

        fp = fp_manager.load(args.target_fp)
        if fp:
            print(f"   User Agent: {fp.user_agent[:60]}...")
            print(f"   Screen: {fp.screen_width}x{fp.screen_height}")

        result = tester.test_session_transfer(
            session_data=session_data,
            source_fp_name=args.source_fp or "default",
            target_fp_name=args.target_fp,
            handler_class=handler_class,
            test_api=args.test_api,
        )
        [result]

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

    report = tester.generate_report(args.output)
    print(report)


def cmd_setup(args):
    """Setup accounts with initial login."""
    from datetime import datetime
    import getpass
    from tokenade.core.browser.manager import BrowserFactory, BrowserConfig
    from tokenade.core.security.credentials import CredentialManager, AccountCredentials
    from tokenade.handlers.resolve import resolve_legacy_handler_class

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
        if not email:
            print("❌ Email and password required")
            continue
        password = getpass.getpass("🔒 Password: ")
        if not password:
            print("❌ Email and password required")
            continue
        site = input("🌐 Site [google]: ").strip() or "google"

        account_num = len(accounts) + 1
        profile_dir = f"browser_data/{account_num}"

        print(f"\n🚀 Setting up account #{account_num}...")

        config = BrowserConfig(
            headless=False,
            user_data_dir=profile_dir,
        )

        browser = BrowserFactory.create(**config.__dict__)
        browser.launch()

        try:
            handler_cls = resolve_legacy_handler_class(site)
            handler = handler_cls(browser)
            hname = getattr(handler_cls, "__name__", str(handler_cls))
            print(f"   Handler: {hname} (legacy; prefer plugins)")
            status = handler.login(email, password, headless=False)

            if status.value == "logged_in":
                account = AccountCredentials(
                    number=account_num,
                    email=email,
                    password=password,
                    profile_dir=profile_dir,
                    site=site,
                    metadata={"created_at": datetime.now().isoformat()},
                )
                accounts.append(account)
                manager.save_accounts(accounts, use_keyring=True, encrypt_file=False)

                print(f"✅ Account #{account_num} setup complete")
                print("   Password stored in system keyring" if manager._keyring_available
                      else "   ⚠️  Keyring unavailable — run 'tokenade setup --encrypt' for secure storage")
            else:
                print(f"❌ Login failed for account #{account_num}")

        finally:
            browser.close()

    print(f"\n📊 Total accounts: {len(accounts)}")
    print("\nNext: run 'tokenade extract' to collect tokens")
