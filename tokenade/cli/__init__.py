"""Tokenade CLI - Main entry point and argument parser."""
import argparse
import asyncio
import logging
import sys
import time

from tokenade.cli.session import cmd_extract, cmd_load, cmd_transfer, cmd_inject_profile
from tokenade.cli.session_export import cmd_export
from tokenade.cli.security import cmd_encrypt, cmd_decrypt, cmd_rekey
from tokenade.cli.proxy import cmd_proxy
from tokenade.cli.management import (
    cmd_sessions, cmd_health, cmd_refresh, cmd_share, cmd_unshare,
    cmd_sync, cmd_monitor, cmd_analytics,
    cmd_refresh_oauth, cmd_oauth_config, cmd_batch_refresh, cmd_cicd, cmd_ci,
    cmd_validate_session, cmd_encrypted_refresh, cmd_launch,
    cmd_refresh_browser, cmd_accounts, cmd_patch_chrome,
    cmd_daemon, cmd_versions, cmd_rollback, cmd_session_diff,
    cmd_logs, cmd_health_report, cmd_mobile_import, cmd_clone_profile, cmd_import,
    cmd_container, cmd_k8s, cmd_fleet, cmd_autopsy, cmd_cloak, cmd_tui,
)
from tokenade.cli.advanced import (
    cmd_batch_export, cmd_batch_load, cmd_validate, cmd_validate_rules,
    cmd_diff, cmd_fingerprint, cmd_test, cmd_setup,
)


def cmd_config(args):
    """Manage configuration (~/.tokenade/config.json)."""
    from tokenade.core.config import load_config, DEFAULTS

    config = load_config()

    if args.config_command == "path":
        print(config.config_path)

    elif args.config_command == "show":
        print(f"\n📋 Tokenade Config ({config.config_path})\n")
        for key in sorted(DEFAULTS.keys()):
            value = config.get(key)
            default = DEFAULTS[key]
            marker = "" if value != default else " (default)"
            print(f"   {key}: {value}{marker}")

    elif args.config_command == "get":
        if not args.key:
            print("❌ Usage: tokenade config get <key>")
            return
        value = config.get(args.key)
        if value is None:
            print(f"❌ Unknown config key: {args.key}")
        else:
            print(value)

    elif args.config_command == "set":
        if not args.key or not args.value:
            print("❌ Usage: tokenade config set <key> <value>")
            return
        # Type coercion for booleans
        value = args.value
        if value.lower() in ("true", "false"):
            value = value.lower() == "true"
        elif value.isdigit():
            value = int(value)
        config.set(args.key, value)
        config.save()
        print(f"✅ Set {args.key} = {value}")


def cmd_completion(args):
    """Generate shell completion scripts."""
    shell = args.shell

    if shell == "bash":
        print('''# Tokenade bash completion
_tokenade() {
    local cur prev commands
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    commands="setup config extract transfer test fingerprint validate export load inject-profile encrypt decrypt rekey batch-export batch-load health refresh proxy sessions share unshare sync validate-rules diff plugin completion launch refresh-browser accounts patch-chrome"

    if [[ ${cur} == -* ]] ; then
        COMPREPLY=( $(compgen -W "--help --version --verbose" -- ${cur}) )
        return 0
    fi

    COMPREPLY=( $(compgen -W "${commands}" -- ${cur}) )
    return 0
}
complete -F _tokenade tokenade
''')
    elif shell == "zsh":
        print('''# Tokenade zsh completion
_tokenade() {
    local commands
    commands=(
        'setup:Setup accounts'
        'config:Manage configuration'
        'extract:Extract tokens'
        'export:Export session from browser'
        'load:Load session file'
        'inject-profile:Inject cookies into profile'
        'proxy:Start proxy server'
        'health:Check session health'
        'refresh:Refresh session'
        'encrypt:Encrypt session file'
        'decrypt:Decrypt session file'
        'sessions:Manage sessions'
        'share:Share session'
        'batch-export:Batch export'
        'batch-load:Batch load'
        'diff:Compare sessions'
        'completion:Generate shell completion'
    )
    _describe 'tokenade' commands
}
compdef _tokenade tokenade
''')
    elif shell == "fish":
        print('''# Tokenade fish completion
complete -c tokenade -f
complete -c tokenade -n "__fish_use_subcommand" -a "setup" -d "Setup accounts"
complete -c tokenade -n "__fish_use_subcommand" -a "config" -d "Manage configuration"
complete -c tokenade -n "__fish_use_subcommand" -a "extract" -d "Extract tokens"
complete -c tokenade -n "__fish_use_subcommand" -a "export" -d "Export session"
complete -c tokenade -n "__fish_use_subcommand" -a "load" -d "Load session"
complete -c tokenade -n "__fish_use_subcommand" -a "proxy" -d "Start proxy"
complete -c tokenade -n "__fish_use_subcommand" -a "health" -d "Check health"
complete -c tokenade -n "__fish_use_subcommand" -a "encrypt" -d "Encrypt session"
complete -c tokenade -n "__fish_use_subcommand" -a "decrypt" -d "Decrypt session"
complete -c tokenade -n "__fish_use_subcommand" -a "sessions" -d "Manage sessions"
complete -c tokenade -n "__fish_use_subcommand" -a "share" -d "Share session"
complete -c tokenade -n "__fish_use_subcommand" -a "completion" -d "Shell completion"
''')
    else:
        print(f"Unsupported shell: {shell}. Use bash, zsh, or fish.")
        sys.exit(1)


def cmd_plugin(args):
    """Manage plugins."""
    from tokenade.core.integration.plugin_registry import PluginRegistry
    from tokenade.core.integration.plugin_loader import PluginLoader

    registry = PluginRegistry()
    loader = PluginLoader()

    if args.plugin_command == "list":
        if args.available:
            installed_names = {p["name"] for p in loader.discover()}
            print("\n🌐 Available plugins from registry:")
            plugins = registry.search()
            if not plugins:
                print("   No plugins found in registry")
            for p in plugins:
                status = " ✓ installed" if p["name"] in installed_names else ""
                print(f"   • {p['name']} v{p.get('version', '?')} — {p.get('description', '')}{status}")
        else:
            print("\n📦 Installed plugins:")
            installed = loader.discover()
            if not installed:
                print("   No plugins installed. Use 'tokenade plugin install <name>' to install.")
            for p in installed:
                enabled = " ✓" if p.get("enabled", True) else " (disabled)"
                print(f"   • {p['name']} v{p.get('version', '?')} ({p.get('type', '?')}){enabled} — {p.get('description', '')}")

    elif args.plugin_command == "install":
        print(f"\n📥 Installing plugin: {args.name}")
        if registry.install(args.name):
            from tokenade.core.integration.plugin_verifier import PluginVerifier
            verifier = PluginVerifier()
            verifier.register_plugin(args.name)
            installed = loader.discover()
            deps_installed = [p["name"] for p in installed if p["name"] != args.name]
            if deps_installed:
                print(f"   📦 Dependencies installed: {', '.join(deps_installed)}")
            print("   ✅ Plugin installed successfully")
        else:
            print("   ❌ Failed to install plugin")

    elif args.plugin_command == "uninstall":
        print(f"\n🗑️  Uninstalling plugin: {args.name}")
        if registry.uninstall(args.name):
            print("   ✅ Plugin uninstalled successfully")
        else:
            print("   ❌ Failed to uninstall plugin (not installed or dependency conflict)")

    elif args.plugin_command == "info":
        installed = loader.discover()
        plugin = None
        for p in installed:
            if p["name"] == args.name:
                plugin = p
                break
        if not plugin:
            registry_details = registry.get_plugin_details(args.name)
            if registry_details:
                print(f"\n📋 Plugin: {args.name} (not installed)")
                print(f"   Version: {registry_details.get('version', '?')}")
                print(f"   Type: {registry_details.get('type', '?')}")
                print(f"   Author: {registry_details.get('author', '?')}")
                print(f"   Description: {registry_details.get('description', '')}")
                if registry_details.get("dependencies"):
                    print(f"   Dependencies: {', '.join(registry_details['dependencies'])}")
                print(f"   Install: tokenade plugin install {args.name}")
            else:
                print(f"❌ Plugin not found: {args.name}")
            return
        installed_ver = plugin.get("version", "?")
        enabled = plugin.get("enabled", True)
        print(f"\n📋 Plugin: {plugin['name']}")
        print(f"   Version: {installed_ver}")
        print(f"   Type: {plugin.get('type', '?')}")
        print(f"   Author: {plugin.get('author', '?')}")
        print(f"   Description: {plugin.get('description', '')}")
        print(f"   Status: {'enabled' if enabled else 'disabled'}")
        if plugin.get("dependencies"):
            print(f"   Dependencies: {', '.join(plugin['dependencies'])}")
        registry_details = registry.get_plugin_details(args.name)
        if registry_details and registry_details.get("version") != installed_ver:
            print(f"   Registry version: {registry_details['version']} (update available)")
        from tokenade.core.integration.plugin_verifier import PluginVerifier
        verifier = PluginVerifier()
        if verifier._local_checksums.get(args.name):
            result = verifier.verify(args.name)
            print(f"   Integrity: {'✓ verified' if result.verified else '✗ tampered'}")
        else:
            print(f"   Integrity: unregistered (run 'tokenade plugin verify' to register)")

    elif args.plugin_command == "enable":
        if loader.enable(args.name):
            print(f"✅ Plugin enabled: {args.name}")
        else:
            print(f"❌ Plugin not found: {args.name}")

    elif args.plugin_command == "disable":
        if loader.disable(args.name):
            print(f"✅ Plugin disabled: {args.name}")
        else:
            print(f"❌ Plugin not found: {args.name}")

    elif args.plugin_command == "update":
        if args.name:
            print(f"\n🔄 Updating {args.name}...")
            if registry.update(args.name):
                print(f"   ✅ Updated: {args.name}")
            else:
                print(f"   ❌ Failed to update: {args.name}")
        else:
            outdated = registry.get_outdated()
            if not outdated:
                print("\n✅ All plugins are up to date.")
            else:
                print(f"\n🔄 Updating {len(outdated)} plugin(s)...")
                results = registry.update()
                updated = sum(1 for v in results.values() if v)
                failed = len(results) - updated
                print(f"   ✅ {updated} updated, ❌ {failed} failed")
                for name, success in results.items():
                    if not success:
                        print(f"      Failed: {name}")

    elif args.plugin_command == "sync":
        print("\n🔄 Syncing plugins from registry...")
        plugins = registry.get_popular(limit=100)
        installed = {p.name for p in loader.list_all()}
        to_install = [p for p in plugins if p.get("name") not in installed]
        
        if not to_install:
            print("✅ All available plugins already installed.")
        else:
            print(f"   Installing {len(to_install)} plugin(s)...")
            for p in to_install:
                name = p.get("name", "")
                success = registry.install(name)
                if success:
                    print(f"   ✅ {name}")
                else:
                    print(f"   ❌ {name}")
            loader.load_all()
            print(f"\n   Done. {len(loader.list_all())} plugins installed.")

    elif args.plugin_command == "reload":
        loaded = loader.reload(args.name)
        if loaded:
            print(f"✅ Plugin reloaded: {args.name} v{loaded.version}")
        else:
            print(f"❌ Failed to reload: {args.name}")

    elif args.plugin_command == "search":
        _plugin_search(registry, args)

    elif args.plugin_command == "categories":
        _plugin_categories(registry)

    elif args.plugin_command == "popular":
        _plugin_popular(registry, args)

    elif args.plugin_command == "recent":
        _plugin_recent(registry, args)

    elif args.plugin_command == "rate":
        _plugin_rate(registry, args)

    elif args.plugin_command == "ratings":
        _plugin_ratings(registry, args)

    elif args.plugin_command == "verify":
        _plugin_verify(args)

    elif args.plugin_command == "outdated":
        _plugin_outdated(registry)

    elif args.plugin_command == "browse":
        _plugin_browse(registry, args)

    elif args.plugin_command == "test":
        _plugin_test(args)

    else:
        print("Usage: tokenade plugin {list|install|uninstall|info|enable|disable|update|reload|search|categories|popular|recent|rate|verify|outdated|browse|test}")


def _plugin_search(registry, args):
    """Search plugins in marketplace."""
    tags = None
    if args.tags:
        tags = [t.strip() for t in args.tags.split(",")]

    results = registry.search(
        query=args.query or "",
        plugin_type=args.plugin_type or "",
        category=args.category or "",
        tags=tags,
        sort_by=args.sort,
    )

    if not results:
        print("No plugins found matching your search.")
        return

    print(f"\n{'=' * 70}")
    print(f"TOKENADE - Plugin Search ({len(results)} results)")
    print(f"{'=' * 70}")

    for p in results:
        stars = f"★ {p.get('rating', 0):.1f}" if p.get('rating') else ""
        verified = " ✓" if p.get('verified') else ""
        downloads = f"↓ {p.get('downloads', 0)}" if p.get('downloads') else ""
        print(f"\n  {p['name']}{verified} v{p.get('version', '?')}")
        print(f"    {p.get('description', '')}")
        meta = " | ".join(filter(None, [stars, downloads, f"by {p.get('author', '')}"]))
        if meta:
            print(f"    {meta}")
        if p.get('tags'):
            print(f"    Tags: {', '.join(p['tags'])}")

    print(f"\n{'=' * 70}\n")


def _plugin_categories(registry):
    """List plugin categories."""
    categories = registry.get_categories()

    print(f"\n{'=' * 60}")
    print("TOKENADE - Plugin Categories")
    print(f"{'=' * 60}")

    for cat in categories:
        print(f"\n  {cat.get('icon', '')} {cat['name']}")
        print(f"    {cat.get('description', '')}")
        print(f"    {cat.get('plugin_count', 0)} plugin(s)")

    print(f"\n{'=' * 60}\n")


def _plugin_popular(registry, args):
    """Show popular plugins."""
    plugins = registry.get_popular(limit=args.limit)

    if not plugins:
        print("No plugins found in registry.")
        return

    print(f"\n{'=' * 60}")
    print(f"TOKENADE - Popular Plugins (top {len(plugins)})")
    print(f"{'=' * 60}")

    for i, p in enumerate(plugins, 1):
        print(f"\n  {i}. {p['name']} v{p.get('version', '?')}")
        print(f"     {p.get('description', '')}")
        dl = p.get("downloads")
        rt = p.get("rating")
        if dl is None and rt is None:
            print("     metrics: n/a (downloads/ratings not tracked yet)")
        else:
            dl_s = f"↓ {dl} downloads" if dl is not None else "↓ n/a"
            rt_s = f"★ {rt:.1f}" if rt is not None else "★ n/a"
            print(f"     {dl_s} | {rt_s}")

    print(f"\n{'=' * 60}\n")


def _plugin_recent(registry, args):
    """Show recent plugins."""
    plugins = registry.get_recent(limit=args.limit)

    if not plugins:
        print("No plugins found in registry.")
        return

    print(f"\n{'=' * 60}")
    print(f"TOKENADE - Recent Plugins ({len(plugins)} newest)")
    print(f"{'=' * 60}")

    for i, p in enumerate(plugins, 1):
        print(f"\n  {i}. {p['name']} v{p.get('version', '?')}")
        print(f"     {p.get('description', '')}")
        print(f"     by {p.get('author', 'unknown')}")

    print(f"\n{'=' * 60}\n")


def _plugin_rate(registry, args):
    """Rate a plugin."""
    if registry.rate_plugin(args.name, args.rating, args.review or ""):
        print(f"✅ Rated {args.name}: {args.rating}/5")
        if args.review:
            print(f"   Review: {args.review}")

        # Sync to GitHub if PAT is set
        from tokenade.core.integration.rating_sync import RatingSync
        sync = RatingSync()
        if sync.has_pat():
            if sync.submit_rating(args.name, args.rating, args.review or ""):
                print("   🌐 Synced to GitHub")
            else:
                print("   ⚠️ GitHub sync failed (local rating saved)")
        else:
            print("   💡 Set github-token to sync globally: tokenade config set github-token <PAT>")
    else:
        print(f"❌ Failed to rate {args.name} (rating must be 1.0-5.0)")


def _plugin_ratings(registry, args):
    """View global ratings from GitHub."""
    from tokenade.core.integration.rating_sync import RatingSync
    sync = RatingSync()

    global_ratings = sync.get_global_ratings()

    if not global_ratings:
        print("\n  No global ratings found.")
        if not sync.has_pat():
            print("  💡 Set github-token to sync ratings: tokenade config set github-token <PAT>")
        return

    name = getattr(args, "name", None)

    if name:
        # Show specific plugin
        if name in global_ratings:
            r = global_ratings[name]
            stars = "★" * int(r.get("rating", 0)) + "☆" * (5 - int(r.get("rating", 0)))
            print(f"\n  {name} — {stars} ({r.get('rating', 0):.1f}/5)")
            print(f"  Reviews: {r.get('review_count', 0)}")
            for rev in r.get("reviews", []):
                print(f"    ⭐ {rev.get('rating', 0)}: {rev.get('review', '')[:80]}")
        else:
            print(f"\n  No global ratings for: {name}")
    else:
        # Show all
        print(f"\n  🌐 Global Ratings ({len(global_ratings)} plugins)\n")
        for name, r in sorted(global_ratings.items()):
            stars = "★" * int(r.get("rating", 0)) + "☆" * (5 - int(r.get("rating", 0)))
            print(f"  {stars} {r.get('rating', 0):.1f}  {name}  ({r.get('review_count', 0)} reviews)")
        if not sync.has_pat():
            print(f"\n  💡 Set github-token to sync: tokenade config set github-token <PAT>")


def _plugin_verify(args):
    """Verify plugin checksums. Auto-registers on first run."""
    from tokenade.core.integration.plugin_verifier import PluginVerifier

    verifier = PluginVerifier()
    plugin_names = [args.name] if args.name else [
        d.name for d in sorted(verifier.plugins_dir.iterdir())
        if d.is_dir() and not d.name.startswith(".") and (d / "plugin.json").exists()
    ]

    if not plugin_names:
        print("No installed plugins to verify.")
        return

    results = []
    registered = []
    for name in plugin_names:
        if not verifier._local_checksums.get(name):
            verifier.register_plugin(name)
            registered.append(name)
            results.append(verifier.verify(name))
        else:
            results.append(verifier.verify(name))

    print(f"\n{'=' * 60}")
    print("TOKENADE - Plugin Verification")
    print(f"{'=' * 60}")

    all_ok = True
    for r in results:
        if r.plugin_name in registered:
            icon = "📝"
            status = f"registered ({r.files_checked} files checksummed)"
        elif r.verified:
            icon = "✅"
            status = r.summary
        else:
            icon = "❌"
            status = r.summary
            all_ok = False
        print(f"\n  {icon} {r.plugin_name}: {status}")
        for err in r.errors:
            print(f"     ⚠️  {err}")

    print(f"\n{'=' * 60}")
    if all_ok:
        print("All plugins verified successfully.")
    else:
        print("Some plugins failed verification!")
    print(f"{'=' * 60}\n")
    print(f"{'=' * 60}\n")


def _plugin_outdated(registry):
    """Show outdated plugins."""
    outdated = registry.get_outdated()

    if not outdated:
        print("All installed plugins are up to date.")
        return

    print(f"\n{'=' * 60}")
    print(f"TOKENADE - Outdated Plugins ({len(outdated)})")
    print(f"{'=' * 60}")

    for p in outdated:
        print(f"\n  {p['name']}")
        print(f"    Installed: {p['installed_version']} → Available: {p['available_version']}")
        if p.get('description'):
            print(f"    {p['description']}")

    print(f"\n  Run 'tokenade plugin update' to update all.")
    print(f"{'=' * 60}\n")


def _plugin_browse(registry, args):
    """Generate static HTML marketplace page."""
    from pathlib import Path
    from tokenade.core.integration.plugin_browser import generate_marketplace_html

    plugins = registry.search()
    categories = registry.get_categories()

    output_path = args.output or str(Path.home() / ".tokenade" / "marketplace.html")

    path = generate_marketplace_html(plugins, categories, output_path)
    print(f"✅ Marketplace page generated: {path}")
    print(f"   Open in browser: file://{path}")


def _plugin_test(args):
    """Run tests on installed plugins."""
    from tokenade.core.integration.plugin_testing import PluginTestRunner

    runner = PluginTestRunner()

    if args.name:
        suites = [runner.test_plugin(args.name)]
    else:
        suites = runner.test_all()

    if not suites:
        print("No plugins found to test.")
        return

    print(f"\n{'=' * 60}")
    print("TOKENADE - Plugin Tests")
    print(f"{'=' * 60}")

    total_passed = 0
    total_failed = 0

    for suite in suites:
        status = "✅" if suite.passed else "❌"
        print(f"\n{status} {suite.summary()}")
        for result in suite.results:
            icon = "  ✓" if result.passed else "  ✗"
            msg = f" — {result.message}" if result.message and not result.passed else ""
            print(f"{icon} {result.test_name}{msg}")
        total_passed += suite.passed_count
        total_failed += suite.failed_count

    print(f"\n{'=' * 60}")
    print(f"Results: {total_passed} passed, {total_failed} failed")
    print(f"{'=' * 60}\n")


def cmd_profile(args):
    """Manage browser profiles."""
    from tokenade.core.browser.profiles import ProfileManager

    manager = ProfileManager()

    if args.profile_command == "create":
        proxy = None
        if args.proxy:
            proxy = {"url": args.proxy}
        tags = [t.strip() for t in args.tags.split(",")] if args.tags else []
        try:
            profile = manager.create_profile(
                name=args.name,
                browser=args.browser,
                os_name=args.os_name,
                proxy=proxy,
                tags=tags,
                notes=args.notes or "",
            )
            print(f"\n✅ Created profile: {profile.name}")
            print(f"   Browser: {profile.browser} | OS: {profile.os}")
            print(f"   ID: {profile.id}")
            if profile.fingerprint.get("navigator"):
                nav = profile.fingerprint["navigator"]
                print(f"   Hardware: {nav.get('hardwareConcurrency', '?')} cores, {nav.get('deviceMemory', '?')} GB RAM")
            if profile.fingerprint.get("webgl"):
                gl = profile.fingerprint["webgl"]
                print(f"   GPU: {gl.get('renderer', '?')}")
            print()
        except ValueError as e:
            print(f"\n❌ {e}\n")

    elif args.profile_command == "list":
        profiles = manager.list_profiles(browser=args.browser, tag=args.tag)
        if not profiles:
            print("\nNo profiles found.\n")
            return
        print(f"\n{'=' * 60}")
        print(f"TOKENADE - Browser Profiles ({len(profiles)} total)")
        print(f"{'=' * 60}")
        for p in profiles:
            last_used = time.strftime("%Y-%m-%d %H:%M", time.localtime(p.last_used)) if p.last_used else "never"
            tags = f" [{', '.join(p.tags)}]" if p.tags else ""
            print(f"\n  {p.name}{tags}")
            print(f"    {p.browser} / {p.os} | ID: {p.id}")
            print(f"    Last used: {last_used}")
            if p.proxy:
                print(f"    Proxy: {p.proxy.get('url', 'configured')}")
        print(f"\n{'=' * 60}\n")

    elif args.profile_command == "get":
        profile = manager.get_profile(args.name)
        if not profile:
            print(f"\n❌ Profile not found: {args.name}\n")
            return
        print(f"\n{'=' * 60}")
        print(f"TOKENADE - Profile: {profile.name}")
        print(f"{'=' * 60}")
        print(f"  ID: {profile.id}")
        print(f"  Browser: {profile.browser}")
        print(f"  OS: {profile.os}")
        print(f"  Created: {time.strftime('%Y-%m-%d %H:%M', time.localtime(profile.created_at))}")
        print(f"  Updated: {time.strftime('%Y-%m-%d %H:%M', time.localtime(profile.updated_at))}")
        last_used = time.strftime('%Y-%m-%d %H:%M', time.localtime(profile.last_used)) if profile.last_used else "never"
        print(f"  Last used: {last_used}")
        if profile.tags:
            print(f"  Tags: {', '.join(profile.tags)}")
        if profile.notes:
            print(f"  Notes: {profile.notes}")
        if profile.proxy:
            print(f"  Proxy: {profile.proxy.get('url', 'configured')}")
        if profile.fingerprint:
            nav = profile.fingerprint.get("navigator", {})
            gl = profile.fingerprint.get("webgl", {})
            scr = profile.fingerprint.get("screen", {})
            print(f"\n  Fingerprint:")
            print(f"    Platform: {nav.get('platform', '?')}")
            print(f"    Language: {nav.get('language', '?')}")
            print(f"    Cores: {nav.get('hardwareConcurrency', '?')} | RAM: {nav.get('deviceMemory', '?')} GB")
            print(f"    Screen: {scr.get('width', '?')}x{scr.get('height', '?')}")
            print(f"    GPU: {gl.get('renderer', '?')}")
        print(f"\n{'=' * 60}\n")

    elif args.profile_command == "delete":
        if manager.delete_profile(args.name):
            print(f"\n✅ Deleted profile: {args.name}\n")
        else:
            print(f"\n❌ Profile not found: {args.name}\n")

    elif args.profile_command == "export":
        try:
            path = manager.export_profile(args.name, args.output or f"{args.name}.zip")
            print(f"\n✅ Exported profile: {path}\n")
        except FileNotFoundError as e:
            print(f"\n❌ {e}\n")

    elif args.profile_command == "import":
        try:
            profile = manager.import_profile(args.archive, name=args.name)
            print(f"\n✅ Imported profile: {profile.name}\n")
        except (FileNotFoundError, ValueError) as e:
            print(f"\n❌ {e}\n")

    elif args.profile_command == "recent":
        profiles = manager.get_recent_profiles(limit=args.limit)
        if not profiles:
            print("\nNo recently used profiles.\n")
            return
        print(f"\nRecently used profiles:")
        for i, p in enumerate(profiles, 1):
            last_used = time.strftime("%Y-%m-%d %H:%M", time.localtime(p.last_used)) if p.last_used else "never"
            print(f"  {i}. {p.name} ({p.browser}/{p.os}) — last used: {last_used}")
        print()

    elif args.profile_command == "stats":
        stats = manager.get_stats()
        print(f"\nProfile Statistics:")
        print(f"  Total: {stats['total']}")
        for browser, count in stats.get("by_browser", {}).items():
            print(f"  {browser}: {count}")
        print()


def cmd_stealth(args):
    """Browser stealth management."""
    from pathlib import Path
    from tokenade.core.browser.stealth import StealthManager
    from tokenade.core.browser.dependencies import DependencyChecker

    if args.stealth_action == "test":
        from tokenade.core.browser.stealth_validation import StealthTestSuite
        from tokenade.core.browser.dashboard import generate_html_report, generate_json_report

        browser = args.browser
        print(f"\n🔍 Running stealth tests ({browser})...")
        suite = StealthTestSuite(browser=browser, headless=True)
        report = asyncio.run(suite.run_all(url=args.url))

        print(f"\n{'=' * 60}")
        print(f"  STEALTH SCORE: {report.overall_score:.0f}/100 ({report._grade()})")
        print(f"{'=' * 60}")
        print(f"  {report.passed} passed, {report.failed} failed, {report.warned} warned")
        print()

        for r in report.results:
            icon = {"pass": "✅", "fail": "❌", "warn": "⚠️", "skip": "○"}[r.verdict.value]
            print(f"  {icon} {r.name} ({r.score:.0f})")

        # Save reports
        html_path = args.output or str(Path.home() / ".tokenade" / "stealth_report.html")
        generate_html_report(report, html_path)
        json_path = html_path.replace(".html", ".json")
        generate_json_report(report, json_path)
        print(f"\n  📄 HTML report: {html_path}")
        print(f"  📄 JSON report: {json_path}")
        print(f"{'=' * 60}\n")

    elif args.stealth_action == "report":
        import json
        from pathlib import Path
        print(f"\n📊 Stealth Report")
        manager = StealthManager()
        config = manager.get_config_dict()
        enabled = [k for k, v in config.items() if v is True and k.startswith("enable_")]
        print(f"   Enabled patches: {len(enabled)}")
        for patch in enabled:
            print(f"     ✓ {patch.replace('enable_', '')}")
        print(f"\n   WebGL vendor: {config['webgl_vendor']}")
        print(f"   WebGL renderer: {config['webgl_renderer']}")
        print(f"   Screen: {config['screen_width']}x{config['screen_height']}")
        output_path = args.output or str(Path.home() / ".tokenade" / "stealth_report.json")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(config, f, indent=2)
        print(f"   Report saved: {output_path}")

    elif args.stealth_action == "deps":
        checker = DependencyChecker()
        report = checker.get_report("chromium")
        print(f"\n📦 System Dependencies ({report['system']})")
        print(f"   Package manager: {report['package_manager'] or 'not found'}")
        print(f"   Installed: {report['installed']}/{report['total']}")
        if report['missing_packages']:
            print(f"   Missing ({len(report['missing_packages'])}):")
            for pkg in report['missing_packages']:
                print(f"     ❌ {pkg}")
        else:
            print(f"   ✅ All dependencies installed")

    elif args.stealth_action == "deps-install":
        print(f"\n📦 Installing missing dependencies...")
        checker = DependencyChecker()
        results = checker.install_playwright_deps()
        installed = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        print(f"   Installed: {installed}, Failed: {failed}")
        for r in results:
            if r.success:
                print(f"   ✅ {r.name}")
            else:
                print(f"   ❌ {r.name}: {r.message}")

    elif args.stealth_action == "battle":
        from tokenade.core.browser.battle import BattleTestSuite, DETECTION_SITES

        browser = args.browser
        sites = args.site if args.site else list(DETECTION_SITES.keys())
        timeout_ms = args.timeout * 1000

        print(f"\n⚔️  Running battle tests ({browser})...")
        print(f"   Sites: {len(sites)}")
        for s in sites:
            cfg = DETECTION_SITES.get(s, {})
            print(f"     • {cfg.get('name', s)}")
        print()

        suite = BattleTestSuite(
            browser=browser,
            headless=True,
            sites=sites,
            timeout_ms=timeout_ms,
        )
        report = suite.run_sync()

        print(report.summary())
        print(f"\n  Duration: {report.duration_ms / 1000:.1f}s")

        if args.output:
            import json as json_mod
            from pathlib import Path
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "overall_score": report.overall_score,
                "grade": report.grade,
                "browser": report.browser,
                "timestamp": report.timestamp,
                "duration_ms": report.duration_ms,
                "passed": report.passed,
                "detected": report.detected,
                "partial": report.partial,
                "errors": report.errors,
                "skipped": report.skipped,
                "sites": [
                    {
                        "name": r.site_name,
                        "url": r.url,
                        "verdict": r.verdict.value,
                        "score": r.score,
                        "details": r.detection_details,
                        "error": r.error,
                        "duration_ms": r.duration_ms,
                    }
                    for r in report.site_results
                ],
            }
            with open(out, "w") as f:
                json_mod.dump(data, f, indent=2)
            print(f"\n  📄 JSON report: {args.output}")

        print(f"\n{'=' * 60}\n")

    else:
        print("Usage: tokenade stealth {test|report|battle|deps|deps-install}")


def cmd_deps(args):
    """System dependency management."""
    from tokenade.core.browser.dependencies import DependencyChecker

    checker = DependencyChecker()

    if args.deps_action == "check":
        browser = getattr(args, "browser", "chromium")
        report = checker.get_report(browser)
        print(f"\n📦 System Dependencies ({report['system']})")
        print(f"   Package manager: {report['package_manager'] or 'not found'}")
        print(f"   Browser: {browser}")
        print(f"   Installed: {report['installed']}/{report['total']}")
        if report['missing_packages']:
            print(f"   Missing packages:")
            for pkg in report['missing_packages']:
                print(f"     ❌ {pkg}")
            print(f"\n   Install: tokenade deps install")
        else:
            print(f"   ✅ All dependencies installed")

    elif args.deps_action == "install":
        browser = getattr(args, "browser", "chromium")
        playwright_only = getattr(args, "playwright", False)

        if playwright_only:
            print(f"\n📦 Installing Playwright dependencies...")
            results = checker.install_playwright_deps()
        else:
            print(f"\n📦 Installing {browser} dependencies...")
            results = checker.install_missing(browser)

        installed = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        print(f"   Installed: {installed}, Failed: {failed}")
        for r in results:
            if r.success:
                print(f"   ✅ {r.name}")
            else:
                print(f"   ❌ {r.name}: {r.message}")

    else:
        print("Usage: tokenade deps {check|install}")


def cmd_serve(args):
    """Start the API server."""
    import asyncio
    from tokenade.core.api.server import TokenadeAPIServer, APIServerConfig

    config = APIServerConfig(
        host=args.host,
        port=args.port,
        api_key=args.api_key,
        sessions_dir=args.sessions_dir or "~/.tokenade/sessions",
        cors_origins=args.cors.split(",") if args.cors else None,
    )

    print(f"\n🚀 Starting Tokenade API server...")
    print(f"   Host: {config.host}")
    print(f"   Port: {config.port}")
    print(f"   Auth: {'API key required' if config.api_key else 'no authentication'}")
    print(f"   Sessions: {config.sessions_dir}")
    print()

    server = TokenadeAPIServer(config)

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n\n🛑 Server stopped")
    except Exception as e:
        print(f"\n❌ Server error: {e}")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("tokenade")


def setup_logging(verbose: bool = False):
    """Configure logging level and structured output."""
    from tokenade.core.logging.structured import LogManager
    level = "DEBUG" if verbose else "INFO"
    json_output = getattr(setup_logging, '_json_output', False)
    LogManager.setup(level=level, json_output=json_output)


def _build_parser():
    """Build and return the CLI argument parser (extracted for testability)."""
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
  monitor       Monitor session health in real-time
  batch-export  Export multiple sites at once
        """,
    )

    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Output in JSON format")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Setup
    subparsers.add_parser("setup", help="Setup accounts")

    # Config
    config_parser = subparsers.add_parser("config", help="Manage configuration")
    config_parser.add_argument("config_command", choices=["show", "set", "get", "path"],
                               help="Config action")
    config_parser.add_argument("key", nargs="?", help="Config key")
    config_parser.add_argument("value", nargs="?", help="Config value")

    # Extract
    extract_parser = subparsers.add_parser("extract", help="Extract tokens")
    extract_parser.add_argument("--visible", action="store_true", help="Show browser window")

    # Transfer
    transfer_parser = subparsers.add_parser("transfer", help="Transfer session")
    transfer_parser.add_argument("-s", "--session", required=True, help="Session file path")
    transfer_parser.add_argument("-", "--fingerprint", help="Target fingerprint name")
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
    export_parser.add_argument("--cdp-port", type=int, help="Extract via CDP from running browser (bypasses SQLite decryption)")
    export_parser.add_argument("--file-path", help="Export from cookies file")
    export_parser.add_argument("--format", choices=["netscape", "json", "curl"], default="netscape", help="File format")
    export_parser.add_argument("--collect-fingerprint", action="store_true", help="Collect source browser fingerprint")
    export_parser.add_argument("--output", "-o", help="Output file path (any extension)")
    export_parser.add_argument("--list-profiles", action="store_true", help="List available profiles")
    export_parser.add_argument("--decrypt", action="store_true", help="Decrypt cookies (auto-detected)")
    export_parser.add_argument("--extract-local-storage", action="store_true", help="Also extract localStorage data")
    export_parser.add_argument("--local-storage-origin", help="Origin to extract localStorage from")
    export_parser.add_argument("--full", action="store_true", help="Extract cookies + localStorage + sessionStorage (v3.0 format)")
    export_parser.add_argument("--no-storage", action="store_true", help="Extract only cookies (backward compat)")
    export_parser.add_argument("--encrypt-password", help="Encrypt .tokenade file with this password at export time")
    export_parser.add_argument("--plugin", help="Force specific site handler plugin (e.g., google-handler)")
    export_parser.add_argument("--no-plugin", action="store_true", help="Skip plugin, use default extraction")
    export_parser.add_argument("--list-handlers", action="store_true", help="List available site handler plugins")

    # Load
    load_parser = subparsers.add_parser("load", help="Load session file into browser")
    load_parser.add_argument("--file", "-", required=True, help="Path to session file")
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

    # Health Report
    health_report_parser = subparsers.add_parser("health-report", help="Batch health report for CI/CD")
    health_report_parser.add_argument("--session", "-s", help="Single session file to check")
    health_report_parser.add_argument("--sessions-dir", "-d", help="Directory of sessions to check")
    health_report_parser.add_argument("--json", dest="json_output", action="store_true", help="Output as JSON")
    health_report_parser.add_argument("--min-health", type=float, default=0.5, help="Minimum health score (default: 0.5)")
    health_report_parser.add_argument("--max-expired", type=int, default=0, help="Max allowed expired cookies (default: 0)")
    health_report_parser.add_argument("--webhook", help="Send report to webhook URL")

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
    proxy_parser.add_argument("--decrypt-password", help="Decrypt .tokenade file with this password")
    proxy_parser.add_argument("--mode", choices=["gui", "forward"], default="gui",
                              help="Proxy mode: gui (browser GUI) or forward (HTTP_PROXY)")
    proxy_parser.add_argument("--port", "-p", type=int, default=9222, help="Port to listen on (default: 9222)")
    proxy_parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    proxy_parser.add_argument("--legacy", action="store_true", help="Use legacy service-worker proxy (default: CDP)")
    proxy_parser.add_argument("--visible", action="store_true", help="Show browser window (CDP mode only)")
    proxy_parser.add_argument("--fingerprint", action="store_true", help="Enable TLS fingerprint matching via curl-cffi (breaks cf_clearance)")
    proxy_parser.add_argument("--impersonate", help="Browser to impersonate (e.g., chrome120, chrome131, firefox128, safari17_0)")
    proxy_parser.add_argument("--no-open-browser", action="store_true", help="Don't open browser automatically")
    proxy_parser.add_argument("--no-gui", action="store_true", help="Disable GUI mode (legacy proxy only)")
    proxy_parser.add_argument("--timeout", type=int, default=30, help="Request timeout in seconds (default: 30)")
    proxy_parser.add_argument("--auto-refresh", action="store_true", help="Auto-refresh session from source browser when cookies expire")
    proxy_parser.add_argument("--source-browser", help="Source browser for auto-refresh (e.g., firefox, chrome)")
    proxy_parser.add_argument("--source-profile", help="Source profile for auto-refresh (e.g., default, Profile 1)")
    proxy_parser.add_argument("--auto-navigate", action="store_true", help="Auto-navigate to site URL when proxy starts")
    proxy_parser.add_argument("--target-url", help="Override default navigation URL")
    proxy_parser.add_argument("--rotate", action="store_true", help="Enable session rotation across multiple sessions")
    proxy_parser.add_argument("--rotate-strategy", choices=["health-weighted", "round-robin", "random", "least-recently-used"],
                              default="health-weighted", help="Rotation strategy (default: health-weighted)")
    proxy_parser.add_argument("--rotate-interval", type=int, default=300, help="Rotation interval in seconds (default: 300)")

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
    share_parser.add_argument("--email-to", help="Comma-separated email recipients")
    share_parser.add_argument("--smtp-host", help="SMTP server host")
    share_parser.add_argument("--smtp-port", type=int, default=587, help="SMTP server port")
    share_parser.add_argument("--smtp-user", help="SMTP username")
    share_parser.add_argument("--smtp-password", help="SMTP password")
    share_parser.add_argument("--webhook-url", help="Webhook URL to notify")

    # Unshare
    unshare_parser = subparsers.add_parser("unshare", help="Revoke a shared session")
    unshare_parser.add_argument("session_id", help="Session ID to revoke")
    unshare_parser.add_argument("--list", action="store_true", help="List all active shares")

    # Import shared session
    import_parser = subparsers.add_parser("import", help="Import a shared session from URL")
    import_parser.add_argument("url", help="tokenade://share/ URL")
    import_parser.add_argument("--password", "-p", help="Decryption password")
    import_parser.add_argument("--output", "-o", help="Output file path")

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

    # Plugin
    plugin_parser = subparsers.add_parser("plugin", help="Manage plugins")
    plugin_sub = plugin_parser.add_subparsers(dest="plugin_command", help="Plugin commands")

    plugin_list_parser = plugin_sub.add_parser("list", help="List installed plugins")
    plugin_list_parser.add_argument("--available", action="store_true", help="Show available plugins from registry")

    plugin_install_parser = plugin_sub.add_parser("install", help="Install a plugin")
    plugin_install_parser.add_argument("name", help="Plugin name to install")

    plugin_uninstall_parser = plugin_sub.add_parser("uninstall", help="Uninstall a plugin")
    plugin_uninstall_parser.add_argument("name", help="Plugin name to uninstall")

    plugin_info_parser = plugin_sub.add_parser("info", help="Show plugin details")
    plugin_info_parser.add_argument("name", help="Plugin name")

    plugin_enable_parser = plugin_sub.add_parser("enable", help="Enable a disabled plugin")
    plugin_enable_parser.add_argument("name", help="Plugin name to enable")

    plugin_disable_parser = plugin_sub.add_parser("disable", help="Disable a plugin without uninstalling")
    plugin_disable_parser.add_argument("name", help="Plugin name to disable")

    plugin_update_parser = plugin_sub.add_parser("update", help="Update plugins from registry")
    plugin_update_parser.add_argument("name", nargs="?", default=None, help="Plugin name to update (all if omitted)")

    plugin_sync_parser = plugin_sub.add_parser("sync", help="Install all available plugins from registry")
    plugin_sync_parser.add_argument("--force", action="store_true", help="Reinstall even if already installed")

    plugin_reload_parser = plugin_sub.add_parser("reload", help="Reload a plugin")
    plugin_reload_parser.add_argument("name", help="Plugin name to reload")

    # plugin search
    plugin_search_parser = plugin_sub.add_parser("search", help="Search plugins in marketplace")
    plugin_search_parser.add_argument("query", nargs="?", default="", help="Search query")
    plugin_search_parser.add_argument("--type", dest="plugin_type", help="Filter by plugin type")
    plugin_search_parser.add_argument("--category", help="Filter by category")
    plugin_search_parser.add_argument("--tags", help="Comma-separated tags to filter")
    plugin_search_parser.add_argument(
        "--sort",
        choices=["rating", "downloads", "name", "recent", "trending"],
        default="name",
        help="Sort order (default: name — registry has no fake download/rating metrics)",
    )

    # plugin categories
    plugin_sub.add_parser("categories", help="List plugin categories")

    # plugin popular
    plugin_popular_parser = plugin_sub.add_parser("popular", help="Show most popular plugins")
    plugin_popular_parser.add_argument("--limit", "-n", type=int, default=10, help="Number of plugins to show")

    # plugin recent
    plugin_recent_parser = plugin_sub.add_parser("recent", help="Show newest plugins")
    plugin_recent_parser.add_argument("--limit", "-n", type=int, default=10, help="Number of plugins to show")

    # plugin rate
    plugin_rate_parser = plugin_sub.add_parser("rate", help="Rate a plugin (1-5 stars)")
    plugin_rate_parser.add_argument("name", help="Plugin name")
    plugin_rate_parser.add_argument("rating", type=float, help="Rating (1.0-5.0)")
    plugin_rate_parser.add_argument("--review", help="Written review")

    # plugin ratings
    plugin_ratings_parser = plugin_sub.add_parser("ratings", help="View global ratings from GitHub")
    plugin_ratings_parser.add_argument("name", nargs="?", help="Plugin name (all if omitted)")

    # plugin verify
    plugin_verify_parser = plugin_sub.add_parser("verify", help="Verify plugin integrity via checksums")
    plugin_verify_parser.add_argument("name", nargs="?", help="Plugin name (all if omitted)")

    # plugin outdated
    plugin_sub.add_parser("outdated", help="Show plugins with available updates")

    # plugin browse
    plugin_browse_parser = plugin_sub.add_parser("browse", help="Generate static HTML marketplace page")
    plugin_browse_parser.add_argument("--output", "-o", help="Output HTML file path")

    # plugin test
    plugin_test_parser = plugin_sub.add_parser("test", help="Run tests on installed plugins")
    plugin_test_parser.add_argument("name", nargs="?", help="Plugin name (all if omitted)")

    # Sync
    sync_parser = subparsers.add_parser("sync", help="Sync sessions from browser cookies")
    sync_sub = sync_parser.add_subparsers(dest="sync_command", help="Sync commands")

    sync_add_parser = sync_sub.add_parser("add", help="Add a sync target")
    sync_add_parser.add_argument("--name", "-n", required=True, help="Target name (e.g., gmail)")
    sync_add_parser.add_argument("--domains", "-d", required=True, help="Comma-separated domains")
    sync_add_parser.add_argument("--browser", "-b", default="firefox", help="Browser (default: firefox)")
    sync_add_parser.add_argument("--profile", "-p", help="Browser profile name")
    sync_add_parser.add_argument("--output-dir", "-o", help="Output directory (default: ~/.tokenade/synced)")

    sync_remove_parser = sync_sub.add_parser("remove", help="Remove a sync target")
    sync_remove_parser.add_argument("--name", "-n", required=True, help="Target name")

    sync_sub.add_parser("list", help="List sync targets")
    sync_sub.add_parser("once", help="Run one-time sync")

    sync_start_parser = sync_sub.add_parser("start", help="Start sync daemon")
    sync_start_parser.add_argument("--interval", "-i", type=int, default=60, help="Check interval in seconds")

    # Monitor
    monitor_parser = subparsers.add_parser("monitor", help="Monitor session health in real-time")
    monitor_sub = monitor_parser.add_subparsers(dest="monitor_command", help="Monitor commands")

    monitor_status_parser = monitor_sub.add_parser("status", help="Show monitoring status")
    monitor_status_parser.add_argument("--sessions-dir", "-d", help="Directory of sessions to check")
    monitor_status_parser.add_argument("--session", "-s", help="Single session file to check")

    monitor_start_parser = monitor_sub.add_parser("start", help="Start background monitoring")
    monitor_start_parser.add_argument("--sessions-dir", "-d", help="Directory of sessions to monitor")
    monitor_start_parser.add_argument("--session", "-s", help="Single session file to monitor")
    monitor_start_parser.add_argument("--interval", "-i", type=int, default=60, help="Check interval in seconds")
    monitor_start_parser.add_argument("--auto-refresh", action="store_true", help="Auto-refresh expiring sessions")

    monitor_stop_parser = monitor_sub.add_parser("stop", help="Stop background monitoring")

    monitor_history_parser = monitor_sub.add_parser("history", help="Show monitor event history")
    monitor_history_parser.add_argument("--sessions-dir", "-d", help="Sessions directory")
    monitor_history_parser.add_argument("--limit", "-l", type=int, default=50, help="Max events to show")

    monitor_predict_parser = monitor_sub.add_parser("predict", help="Predict session expiry")
    monitor_predict_parser.add_argument("--sessions-dir", "-d", help="Sessions directory")
    monitor_predict_parser.add_argument("--session", "-s", help="Single session file")

    # Analytics
    analytics_parser = subparsers.add_parser("analytics", help="Session usage analytics")
    analytics_sub = analytics_parser.add_subparsers(dest="analytics_command", help="Analytics commands")

    analytics_report_parser = analytics_sub.add_parser("report", help="Show usage report")
    analytics_report_parser.add_argument("--days", "-d", type=int, default=30, help="Report period in days")
    analytics_report_parser.add_argument("--json", dest="json_output", action="store_true", help="Output as JSON")

    analytics_session_parser = analytics_sub.add_parser("session", help="Show analytics for a session")
    analytics_session_parser.add_argument("session_id", help="Session ID to analyze")

    analytics_cleanup_parser = analytics_sub.add_parser("cleanup", help="Remove old analytics data")
    analytics_cleanup_parser.add_argument("--max-age", type=int, default=90, help="Max age in days")

    # Shell Completion
    completion_parser = subparsers.add_parser("completion", help="Generate shell completion scripts")
    completion_parser.add_argument("shell", choices=["bash", "zsh", "fish"], help="Shell type")

    # OAuth Refresh
    refresh_oauth_parser = subparsers.add_parser("refresh-oauth", help="Refresh OAuth tokens using stored refresh token")
    refresh_oauth_parser.add_argument("--session", "-s", required=True, help="Session file to refresh")

    # OAuth Config
    oauth_config_parser = subparsers.add_parser("oauth-config", help="Configure OAuth settings for a session")
    oauth_config_parser.add_argument("--session", "-s", required=True, help="Session file to configure")
    oauth_config_parser.add_argument("--client-id", help="OAuth client ID")
    oauth_config_parser.add_argument("--client-secret", help="OAuth client secret")
    oauth_config_parser.add_argument("--token-endpoint", help="OAuth token endpoint URL")
    oauth_config_parser.add_argument("--scopes", help="Comma-separated OAuth scopes")
    oauth_config_parser.add_argument("--show", action="store_true", help="Show current OAuth config")

    # Batch Refresh
    batch_refresh_parser = subparsers.add_parser("batch-refresh", help="Refresh multiple sessions with rate limiting")
    batch_refresh_parser.add_argument("--sessions-dir", "-d", default="sessions", help="Sessions directory")
    batch_refresh_parser.add_argument("--max-workers", "-w", type=int, default=3, help="Max parallel workers")
    batch_refresh_parser.add_argument("--delay", type=float, default=1.0, help="Delay between refreshes (seconds)")
    batch_refresh_parser.add_argument("--source-browser", "-b", default="firefox", help="Source browser for cookie refresh")
    batch_refresh_parser.add_argument("--source-profile", "-p", help="Source profile name")
    batch_refresh_parser.add_argument("--force", action="store_true", help="Force refresh even if not expired")
    batch_refresh_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")

    # CI/CD
    cicd_parser = subparsers.add_parser("cicd", help="Generate CI/CD workflow files")
    cicd_parser.add_argument("--generate-all", action="store_true", help="Generate all workflow files")
    cicd_parser.add_argument("--workflow-type", choices=["github", "gitlab", "cron"], default="github", help="Workflow type")
    cicd_parser.add_argument("--sessions-dir", default="sessions", help="Sessions directory")
    cicd_parser.add_argument("--interval-hours", type=int, default=6, help="Refresh interval in hours")
    cicd_parser.add_argument("--source-browser", default="firefox", help="Source browser for cookie refresh")
    cicd_parser.add_argument("--output", "-o", help="Output file path")
    cicd_parser.add_argument("--output-dir", default=".tokenade/ci", help="Output directory for --generate-all")

    # CI Runner
    ci_parser = subparsers.add_parser("ci", help="Session CI runner")
    ci_sub = ci_parser.add_subparsers(dest="ci_action")

    ci_run = ci_sub.add_parser("run", help="Run CI pipeline from tokenade.yml")
    ci_run.add_argument("--config", default="tokenade.yml", help="Config file path")
    ci_run.add_argument("--format", choices=["text", "json", "junit"], help="Override output format")

    ci_init = ci_sub.add_parser("init", help="Create a starter tokenade.yml")
    ci_init.add_argument("--config", default="tokenade.yml", help="Config file path")

    ci_validate = ci_sub.add_parser("validate", help="Validate tokenade.yml schema")
    ci_validate.add_argument("--config", default="tokenade.yml", help="Config file path")

    ci_lint = ci_sub.add_parser("lint", help="Lint tokenade.yml for common issues")
    ci_lint.add_argument("--config", default="tokenade.yml", help="Config file path")

    # Fleet Management
    fleet_parser = subparsers.add_parser("fleet", help="Fleet status across containers/pods")
    fleet_sub = fleet_parser.add_subparsers(dest="fleet_action")

    fleet_status = fleet_sub.add_parser("status", help="Show all sessions across containers")
    fleet_status.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    fleet_health = fleet_sub.add_parser("health", help="Run health checks across the fleet")
    fleet_health.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    fleet_sub.add_parser("refresh", help="Trigger refresh in all running containers")

    fleet_logs = fleet_sub.add_parser("logs", help="Get logs from a container")
    fleet_logs.add_argument("container", nargs="?", help="Container name")
    fleet_logs.add_argument("--lines", "-n", type=int, default=50, help="Number of log lines")

    # Autopsy (Forensics)
    autopsy_parser = subparsers.add_parser("autopsy", help="Analyze why a session died")
    autopsy_parser.add_argument("--session", "-s", required=True, help="Session file to analyze")
    autopsy_parser.add_argument("--compare", "-c", help="Compare with another session file")
    autopsy_parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    # TUI
    tui_parser = subparsers.add_parser("tui", help="Launch interactive terminal UI")
    tui_parser.add_argument("tui_mode", nargs="?", default="full",
                            choices=["full", "marketplace", "sessions"],
                            help="TUI mode")

    # Validate Session
    validate_session_parser = subparsers.add_parser("validate-session", help="Validate session files for CI/CD")
    validate_session_parser.add_argument("--session", "-s", help="Single session file to validate")
    validate_session_parser.add_argument("--sessions-dir", "-d", help="Directory of sessions to validate")
    validate_session_parser.add_argument("--min-health", type=float, default=0.5, help="Minimum health score (0.0-1.0)")
    validate_session_parser.add_argument("--max-expired", type=int, default=0, help="Max allowed expired cookies")
    validate_session_parser.add_argument("--require-oauth", action="store_true", help="Require OAuth config")
    validate_session_parser.add_argument("--max-age-hours", type=float, help="Max session age in hours")
    validate_session_parser.add_argument("--json", dest="json_output", action="store_true", help="Output as JSON")

    # Encrypted Refresh
    encrypted_refresh_parser = subparsers.add_parser("encrypted-refresh", help="Refresh encrypted session files")
    encrypted_refresh_parser.add_argument("--session", "-s", help="Single session file to refresh")
    encrypted_refresh_parser.add_argument("--sessions-dir", "-d", help="Directory of sessions to refresh")
    encrypted_refresh_parser.add_argument("--password", "-p", help="Decryption password")
    encrypted_refresh_parser.add_argument("--key-file", "-k", help="Key file path")
    encrypted_refresh_parser.add_argument("--source-browser", "-b", default="firefox", help="Source browser for cookie refresh")
    encrypted_refresh_parser.add_argument("--force", action="store_true", help="Force refresh even if not expired")

    # CloakBrowser
    cloak_parser = subparsers.add_parser("cloak", help="CloakBrowser stealth browser management")
    cloak_sub = cloak_parser.add_subparsers(dest="cloak_action")

    cloak_info = cloak_sub.add_parser("info", help="Show CloakBrowser status and binary info")
    cloak_info.add_argument("--json", dest="json_output", action="store_true", help="Output as JSON")
    cloak_sub.add_parser("install", help="Download/update CloakBrowser binary")

    cloak_serve = cloak_sub.add_parser("serve", help="Start CDP server (cloakserve)")
    cloak_serve.add_argument("--port", "-p", type=int, default=9222, help="Port to listen on")
    cloak_serve.add_argument("--proxy", help="Upstream proxy URL")
    cloak_serve.add_argument("--headless", action="store_true", default=True, help="Run headless")
    cloak_serve.add_argument("--visible", action="store_true", help="Run headed")
    cloak_serve.add_argument("--idle-timeout", type=int, help="Idle timeout in seconds")

    # Launch Undetectable Browser
    launch_parser = subparsers.add_parser("launch", help="Launch undetectable system browser with CDP")
    launch_parser.add_argument("--browser", "-b", default="chrome", help="Browser to launch (chrome, firefox, brave, edge)")
    launch_parser.add_argument("--session", "-s", help="Session file to inject cookies from")
    launch_parser.add_argument("--url", "-u", help="URL to navigate to after injection")
    launch_parser.add_argument("--port", "-p", type=int, default=9222, help="CDP debugging port")
    launch_parser.add_argument("--profile-dir", help="Custom profile directory")
    launch_parser.add_argument("--visible", action="store_true", help="Show browser window (default unless --headless)")
    launch_parser.add_argument("--headless", action="store_true", help="Run headless (no window)")
    launch_parser.add_argument("--extra-args", help="Extra browser args (comma-separated)")
    launch_parser.add_argument("--browser-path", help="Path to browser executable")
    launch_parser.add_argument("--proxy", help="Upstream proxy URL (e.g. socks5://user:pass@host:port)")
    launch_parser.add_argument("--proxy-file", help="Proxy list file for rotation (one proxy per line)")
    launch_parser.add_argument("--proxy-rotate", action="store_true", help="Enable proxy rotation")
    launch_parser.add_argument(
        "--proxy-strategy", choices=["round-robin", "random", "health-weighted", "sticky"],
        default="health-weighted", help="Rotation strategy (default: health-weighted)"
    )
    launch_parser.add_argument("--humanize", action="store_true", help="Human-like mouse/keyboard/scroll (CloakBrowser)")
    launch_parser.add_argument("--geoip", action="store_true", help="Auto-detect timezone/locale from proxy IP (CloakBrowser)")
    launch_parser.add_argument("--no-cloak", action="store_true", help="Force Playwright + JS patches (skip CloakBrowser)")
    launch_parser.add_argument("--profile", help="Persistent profile directory (CloakBrowser)")
    launch_parser.add_argument("--decrypt-password", help="Decrypt .tokenade file with this password")
    launch_parser.add_argument(
        "--plugin",
        help="Force site handler plugin for launch (e.g. google-handler); auto-discovers when omitted",
    )

    # Refresh Browser (cookie-based session refresh)
    refresh_browser_parser = subparsers.add_parser("refresh-browser", help="Refresh session via undetectable browser (no OAuth needed)")
    refresh_browser_parser.add_argument("--session", "-s", required=True, help="Session file to refresh")
    refresh_browser_parser.add_argument("--browser", "-b", default="chrome", help="Browser to use (chrome, firefox, brave, edge)")
    refresh_browser_parser.add_argument("--url", "-u", help="Target URL (auto-detected from cookies if not specified)")
    refresh_browser_parser.add_argument("--port", "-p", type=int, default=9222, help="CDP debugging port")
    refresh_browser_parser.add_argument("--headless", action="store_true", help="Run headless (no window)")
    refresh_browser_parser.add_argument("--wait", "-w", type=int, default=8, help="Seconds to wait for session refresh (default: 8)")
    refresh_browser_parser.add_argument("--output", "-o", help="Output file (default: overwrite original)")
    refresh_browser_parser.add_argument("--plugin", help="Plugin to use for refresh (e.g., oauth2)")
    refresh_browser_parser.add_argument(
        "--plugin-arg", action="append", default=[], nargs=2, metavar=("KEY", "VALUE"),
        help="Plugin credential (repeatable): --plugin-arg client_id XXX"
    )
    refresh_browser_parser.add_argument("--proxy", help="Upstream proxy URL (e.g. socks5://user:pass@host:port)")
    refresh_browser_parser.add_argument("--proxy-file", help="Proxy list file for rotation (one proxy per line)")
    refresh_browser_parser.add_argument("--proxy-rotate", action="store_true", help="Enable proxy rotation")
    refresh_browser_parser.add_argument(
        "--proxy-strategy", choices=["round-robin", "random", "health-weighted", "sticky"],
        default="health-weighted", help="Rotation strategy (default: health-weighted)"
    )

    # Multi-Account Orchestration
    accounts_parser = subparsers.add_parser("accounts", help="Multi-account orchestration (list/status/refresh)")
    accounts_subparsers = accounts_parser.add_subparsers(dest="accounts_action")

    # accounts list
    accounts_list = accounts_subparsers.add_parser("list", help="List all sessions")
    accounts_list.add_argument("--sessions-dir", "-d", default=".", help="Directory to scan (default: current)")
    accounts_list.add_argument("--site", "-s", help="Filter by site name")
    accounts_list.add_argument("--browser", "-b", help="Filter by browser")

    # accounts status
    accounts_status = accounts_subparsers.add_parser("status", help="Show health/status of all sessions")
    accounts_status.add_argument("--sessions-dir", "-d", default=".", help="Directory to scan (default: current)")
    accounts_status.add_argument("--site", "-s", help="Filter by site name")

    # accounts refresh
    accounts_refresh = accounts_subparsers.add_parser("refresh", help="Refresh all/specific sessions")
    accounts_refresh.add_argument("--sessions-dir", "-d", default=".", help="Directory to scan (default: current)")
    accounts_refresh.add_argument("--site", "-s", help="Filter by site name")
    accounts_refresh.add_argument("--browser", "-b", default="chrome", help="Browser to use for refresh")
    accounts_refresh.add_argument("--files", nargs="*", help="Specific session files to refresh")
    accounts_refresh.add_argument("--port", "-p", type=int, default=9222, help="Starting CDP port")
    accounts_refresh.add_argument("--visible", action="store_true", help="Show browser window")
    accounts_refresh.add_argument("--headless", action="store_true", default=True, help="Run headless (default)")
    accounts_refresh.add_argument("--wait", "-w", type=int, default=8, help="Seconds to wait per session")
    accounts_refresh.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    accounts_refresh.add_argument("--plugin", help="Plugin to use for refresh (e.g., oauth2)")
    accounts_refresh.add_argument("--plugin-arg", action="append", default=[], nargs=2, metavar=("KEY", "VALUE"),
                                  help="Plugin credential (repeatable): --plugin-arg client_id XXX")
    accounts_refresh.add_argument("--proxy", help="Upstream proxy URL (e.g. socks5://user:pass@host:port)")
    accounts_refresh.add_argument("--proxy-file", help="Proxy list file for rotation (one proxy per line)")
    accounts_refresh.add_argument("--proxy-rotate", action="store_true", help="Enable proxy rotation")
    accounts_refresh.add_argument("--proxy-strategy", choices=["round-robin", "random", "health-weighted", "sticky"],
                                  default="health-weighted", help="Rotation strategy (default: health-weighted)")

    # Patch Chrome Binary (remove cdc_ artifacts)
    patch_parser = subparsers.add_parser("patch-chrome", help="Patch Chrome/Chromium binary to remove cdc_ artifacts")
    patch_subparsers = patch_parser.add_subparsers(dest="patch_action")

    # patch-chrome scan
    patch_scan = patch_subparsers.add_parser("scan", help="Scan binary for cdc_ artifacts")
    patch_scan.add_argument("--browser", "-b", default="chrome", help="Browser to scan (chrome, chromium, brave, edge)")
    patch_scan.add_argument("--binary", help="Path to browser binary (auto-detected if omitted)")

    # patch-chrome patch
    patch_do = patch_subparsers.add_parser("patch", help="Patch binary to remove cdc_ artifacts")
    patch_do.add_argument("--browser", "-b", default="chrome", help="Browser to patch")
    patch_do.add_argument("--binary", help="Path to browser binary")
    patch_do.add_argument("--output", "-o", help="Output path for patched binary (default: <binary>.patched)")

    # patch-chrome restore
    patch_restore = patch_subparsers.add_parser("restore", help="Restore binary from backup")
    patch_restore.add_argument("--browser", "-b", default="chrome", help="Browser to restore")
    patch_restore.add_argument("--binary", help="Path to browser binary")

    # patch-chrome verify
    patch_verify = patch_subparsers.add_parser("verify", help="Verify binary patch status")
    patch_verify.add_argument("--browser", "-b", default="chrome", help="Browser to verify")
    patch_verify.add_argument("--binary", help="Path to browser binary")

    # ── Mobile Import ────────────────────────────────────────────
    mobile_import_parser = subparsers.add_parser("mobile-import", help="Import sessions from mobile devices (Android/iOS)")
    mobile_import_parser.add_argument("--auto", action="store_true", help="Auto-detect device and browser")
    mobile_import_parser.add_argument("--list-devices", action="store_true", help="List connected mobile devices")
    mobile_import_parser.add_argument("--device", "-d", help="Device serial number")
    mobile_import_parser.add_argument("--browser", "-b", default="auto", help="Browser to extract from (chrome/firefox/samsung/brave/edge/safari, default: auto)")
    mobile_import_parser.add_argument("--domains", help="Comma-separated domains to filter")
    mobile_import_parser.add_argument("--output", "-o", help="Output .tokenade file path")
    mobile_import_parser.add_argument("--site-name", help="Site name override")
    mobile_import_parser.add_argument("--ios", action="store_true", help="Target iOS device (macOS only)")

    # ── Daemon ──────────────────────────────────────────────────
    daemon_parser = subparsers.add_parser("daemon", help="Auto-refresh daemon (background session refresh)")
    daemon_subparsers = daemon_parser.add_subparsers(dest="daemon_action")

    # daemon start
    daemon_start = daemon_subparsers.add_parser("start", help="Start daemon in background")
    daemon_start.add_argument("--interval", type=float, help="Check interval in minutes (default: 30)")
    daemon_start.add_argument("--webhook", help="Webhook URL for notifications")

    # daemon stop
    daemon_subparsers.add_parser("stop", help="Stop the daemon")

    # daemon status
    daemon_subparsers.add_parser("status", help="Show daemon status")

    # daemon run-once
    daemon_subparsers.add_parser("run-once", help="Run single refresh cycle (foreground)")

    # daemon add
    daemon_add = daemon_subparsers.add_parser("add", help="Add session to watch list")
    daemon_add.add_argument("session", help="Session file to watch")
    daemon_add.add_argument("--browser", "-b", default="chrome", help="Browser for refresh")
    daemon_add.add_argument(
        "--refresh-before", type=float, default=2.0,
        help="Refresh this many hours before expiry (default: 2.0)"
    )
    daemon_add.add_argument("--url", "-u", help="Target URL (auto-detected if not set)")
    daemon_add.add_argument("--site-name", help="Site name (auto-detected from filename)")

    # daemon remove
    daemon_remove = daemon_subparsers.add_parser("remove", help="Remove session from watch list")
    daemon_remove.add_argument("session", help="Session file to remove")

    # daemon list
    daemon_subparsers.add_parser("list", help="List all watched sessions")

    # daemon logs
    daemon_logs = daemon_subparsers.add_parser("logs", help="View daemon logs")
    daemon_logs.add_argument("--lines", "-n", type=int, default=50, help="Number of lines to show")
    daemon_logs.add_argument("--follow", "-f", action="store_true", help="Follow log output (like tail -f)")

    # ── Versions ────────────────────────────────────────────────
    versions_parser = subparsers.add_parser("versions", help="Session versioning (list/create/delete)")
    versions_subparsers = versions_parser.add_subparsers(dest="version_action")

    versions_list = versions_subparsers.add_parser("list", help="List versions for a session")
    versions_list.add_argument("session", help="Session file")

    versions_create = versions_subparsers.add_parser("create", help="Create a new version")
    versions_create.add_argument("session", help="Session file")
    versions_create.add_argument("--description", "-d", help="Version description")

    versions_delete = versions_subparsers.add_parser("delete", help="Delete a version")
    versions_delete.add_argument("session", help="Session file")
    versions_delete.add_argument("version", type=int, help="Version number to delete")

    # ── Rollback ────────────────────────────────────────────────
    rollback_parser = subparsers.add_parser("rollback", help="Rollback session to a specific version")
    rollback_parser.add_argument("session", help="Session file")
    rollback_parser.add_argument("version", type=int, help="Version number to restore")

    # ── Session Diff (version comparison) ───────────────────────
    session_diff_parser = subparsers.add_parser("session-diff", help="Compare two session versions")
    session_diff_parser.add_argument("session", help="Session file")
    session_diff_parser.add_argument("version_a", type=int, help="First version number")
    session_diff_parser.add_argument("version_b", type=int, help="Second version number")

    # ── Logs ────────────────────────────────────────────────────
    logs_parser = subparsers.add_parser("logs", help="View structured logs")
    logs_parser.add_argument("--lines", "-n", type=int, default=50, help="Number of recent lines to show (default: 50)")
    logs_parser.add_argument("--follow", "-f", action="store_true", help="Follow log output (like tail -f)")
    logs_parser.add_argument("--search", "-s", help="Search for text in logs")
    logs_parser.add_argument("--json", dest="json_output", action="store_true", help="Output in JSON format")
    logs_parser.add_argument("--log-file", help="Path to specific log file (default: ~/.tokenade/logs/tokenade.log)")
    logs_parser.add_argument("--list-files", action="store_true", help="List all log files")
    logs_parser.add_argument("--cleanup", type=int, metavar="DAYS", help="Remove log files older than N days")

    # ── Clone Profile ──────────────────────────────────────────
    clone_parser = subparsers.add_parser("clone-profile", help="Clone browser profile with optional session injection")
    clone_parser.add_argument("source", nargs="?", help="Source profile directory (omit to use system default)")
    clone_parser.add_argument("--dest", "-d", required=True, help="Destination directory for the clone")
    clone_parser.add_argument("--browser", "-b", default="chrome", help="Browser name (chrome, firefox, brave, edge)")
    clone_parser.add_argument("--session", "-s", help="Session file to inject into the clone")
    clone_parser.add_argument("--profile", "-p", help="Profile name to clone (default: system default)")
    clone_parser.add_argument("--list-profiles", action="store_true", help="List available browser profiles")

    # Container management
    container_parser = subparsers.add_parser("container", help="Docker container management")
    container_sub = container_parser.add_subparsers(dest="container_action")

    container_start = container_sub.add_parser("start", help="Start proxy/API containers")
    container_start.add_argument("--sessions-dir", "-d", default=".", help="Directory with session files")
    container_start.add_argument("--proxy-port", type=int, default=9222, help="Starting proxy port")
    container_start.add_argument("--api-port", type=int, default=9224, help="API server port")
    container_start.add_argument("--no-api", action="store_true", help="Don't start API server")
    container_start.add_argument("--restart", default="unless-stopped", help="Restart policy (default: unless-stopped)")

    container_stop = container_sub.add_parser("stop", help="Stop containers")
    container_stop.add_argument("--name", help="Container name to stop (default: all tokenade)")

    container_sub.add_parser("restart", help="Restart containers")
    container_sub.add_parser("status", help="Show container status")

    container_logs = container_sub.add_parser("logs", help="Tail container logs")
    container_logs.add_argument("name", help="Container name")
    container_logs.add_argument("--tail", "-n", type=int, default=100, help="Number of lines to tail")
    container_logs.add_argument("--follow", "-f", action="store_true", help="Follow log output")

    container_refresh = container_sub.add_parser("refresh", help="Refresh sessions inside containers")
    container_refresh.add_argument("name", help="Container name")
    container_refresh.add_argument("--sessions-dir", default="/app/sessions", help="Sessions dir in container")

    container_scale = container_sub.add_parser("scale", help="Scale proxy containers")
    container_scale.add_argument("replicas", type=int, help="Number of replicas")
    container_scale.add_argument("--sessions-dir", "-d", default=".", help="Directory with session files")

    container_sub.add_parser("cleanup", help="Stop and remove all tokenade containers")

    container_health = container_sub.add_parser("health", help="Check container health")
    container_health.add_argument("--watch", action="store_true", help="Continuous health monitoring")
    container_health.add_argument("--interval", type=int, default=60, help="Check interval in seconds")
    container_health.add_argument("--max-restarts", type=int, default=3, help="Max restarts before giving up")

    container_gen = container_sub.add_parser("generate", help="Generate docker-compose override")
    container_gen.add_argument("--sessions-dir", "-d", default=".", help="Directory with session files")
    container_gen.add_argument("--output", "-o", help="Output file (default: stdout)")
    container_gen.add_argument("--base-port", type=int, default=9222, help="Starting port")

    # Kubernetes management
    k8s_parser = subparsers.add_parser("k8s", help="Kubernetes deployment management")
    k8s_sub = k8s_parser.add_subparsers(dest="k8s_action")

    k8s_deploy = k8s_sub.add_parser("deploy", help="Generate and apply K8s manifests")
    k8s_deploy.add_argument("--namespace", "-n", default="default", help="Kubernetes namespace")
    k8s_deploy.add_argument("--replicas", "-r", type=int, default=1, help="Number of replicas")
    k8s_deploy.add_argument("--image", default="tokenade:latest", help="Container image")
    k8s_deploy.add_argument("--port", type=int, default=9222, help="Proxy port")
    k8s_deploy.add_argument("--dry-run", action="store_true", help="Only generate YAML, don't apply")
    k8s_deploy.add_argument("--output", "-o", help="Output file for generated YAML")

    k8s_status = k8s_sub.add_parser("status", help="Show deployment status")
    k8s_status.add_argument("--namespace", "-n", default="default", help="Kubernetes namespace")

    k8s_scale = k8s_sub.add_parser("scale", help="Scale deployment")
    k8s_scale.add_argument("replicas", type=int, help="Number of replicas")
    k8s_scale.add_argument("--namespace", "-n", default="default", help="Kubernetes namespace")

    k8s_logs = k8s_sub.add_parser("logs", help="Tail pod logs")
    k8s_logs.add_argument("--namespace", "-n", default="default", help="Kubernetes namespace")
    k8s_logs.add_argument("--tail", type=int, default=100, help="Number of lines to tail")

    k8s_delete = k8s_sub.add_parser("delete", help="Delete deployment and service")
    k8s_delete.add_argument("--namespace", "-n", default="default", help="Kubernetes namespace")

    k8s_sub.add_parser("pods", help="List pods")

    profile_parser = subparsers.add_parser("profile", help="Manage browser profiles")
    profile_sub = profile_parser.add_subparsers(dest="profile_command", help="Profile commands")

    profile_create = profile_sub.add_parser("create", help="Create a new profile")
    profile_create.add_argument("name", help="Profile name")
    profile_create.add_argument("--browser", "-b", default="chromium", help="Browser type (default: chromium)")
    profile_create.add_argument("--os", dest="os_name", default="windows", choices=["windows", "macos", "linux"], help="Target OS")
    profile_create.add_argument("--proxy", help="Proxy URL (e.g., socks5://user:pass@host:port)")
    profile_create.add_argument("--tags", help="Comma-separated tags")
    profile_create.add_argument("--notes", help="Profile notes")

    profile_list = profile_sub.add_parser("list", help="List all profiles")
    profile_list.add_argument("--browser", "-b", help="Filter by browser type")
    profile_list.add_argument("--tag", "-t", help="Filter by tag")

    profile_get = profile_sub.add_parser("get", help="Show profile details")
    profile_get.add_argument("name", help="Profile name")

    profile_delete = profile_sub.add_parser("delete", help="Delete a profile")
    profile_delete.add_argument("name", help="Profile name")

    profile_export = profile_sub.add_parser("export", help="Export profile to zip")
    profile_export.add_argument("name", help="Profile name")
    profile_export.add_argument("--output", "-o", help="Output file path")

    profile_import = profile_sub.add_parser("import", help="Import profile from zip")
    profile_import.add_argument("archive", help="Archive file path")
    profile_import.add_argument("--name", "-n", help="Override profile name")

    profile_recent = profile_sub.add_parser("recent", help="Show recently used profiles")
    profile_recent.add_argument("--limit", "-n", type=int, default=5, help="Number of profiles")

    profile_sub.add_parser("stats", help="Show profile statistics")

    stealth_parser = subparsers.add_parser("stealth", help="Browser stealth management")
    stealth_sub = stealth_parser.add_subparsers(dest="stealth_action")

    stealth_test = stealth_sub.add_parser("test", help="Test stealth against detection sites")
    stealth_test.add_argument("--url", "-u", help="Custom test URL")
    stealth_test.add_argument("--browser", "-b", choices=["chrome", "firefox"], default="chrome")

    stealth_report = stealth_sub.add_parser("report", help="Generate stealth report")
    stealth_report.add_argument("--output", "-o", help="Output file for report")
    stealth_report.add_argument("--browser", "-b", choices=["chrome", "firefox"], default="chrome")

    stealth_battle = stealth_sub.add_parser("battle", help="Battle test against real detection sites")
    stealth_battle.add_argument("--browser", "-b", choices=["chromium", "firefox"], default="chromium")
    stealth_battle.add_argument("--site", "-s", action="append", help="Specific site(s) to test (default: all)")
    stealth_battle.add_argument("--timeout", "-t", type=int, default=30, help="Per-site timeout in seconds")
    stealth_battle.add_argument("--output", "-o", help="Output file for JSON report")

    stealth_sub.add_parser("deps", help="Check stealth system dependencies")
    stealth_sub.add_parser("deps-install", help="Install missing stealth dependencies")

    deps_parser = subparsers.add_parser("deps", help="System dependency management")
    deps_sub = deps_parser.add_subparsers(dest="deps_action")

    deps_sub.add_parser("check", help="Check system dependencies")
    deps_install = deps_sub.add_parser("install", help="Install missing dependencies")
    deps_install.add_argument("--browser", "-b", choices=["chrome", "firefox"], default="chrome")
    deps_install.add_argument("--playwright", action="store_true", help="Install Playwright dependencies")

    serve_parser = subparsers.add_parser("serve", help="Start API server")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    serve_parser.add_argument("--port", "-p", type=int, default=9224, help="Port to listen on (default: 9224)")
    serve_parser.add_argument("--api-key", help="API key for authentication")
    serve_parser.add_argument("--sessions-dir", "-d", help="Sessions directory")
    serve_parser.add_argument("--cors", help="Allowed CORS origins (comma-separated)")

    return parser


def main():
    """Main CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    setup_logging._json_output = getattr(args, 'json_output', False)
    setup_logging(args.verbose)

    commands = {
        "setup": cmd_setup,
        "config": cmd_config,
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
        "health-report": cmd_health_report,
        "refresh": cmd_refresh,
        "refresh-oauth": cmd_refresh_oauth,
        "oauth-config": cmd_oauth_config,
        "batch-refresh": cmd_batch_refresh,
        "encrypted-refresh": cmd_encrypted_refresh,
        "validate-session": cmd_validate_session,
        "cicd": cmd_cicd,
        "ci": cmd_ci,
        "launch": cmd_launch,
        "refresh-browser": cmd_refresh_browser,
        "accounts": cmd_accounts,
        "patch-chrome": cmd_patch_chrome,
        "mobile-import": cmd_mobile_import,
        "clone-profile": cmd_clone_profile,
        "daemon": cmd_daemon,
        "versions": cmd_versions,
        "rollback": cmd_rollback,
        "session-diff": cmd_session_diff,
        "logs": cmd_logs,
        "proxy": cmd_proxy,
        "sessions": cmd_sessions,
        "share": cmd_share,
        "unshare": cmd_unshare,
        "import": cmd_import,
        "sync": cmd_sync,
        "monitor": cmd_monitor,
        "analytics": cmd_analytics,
        "validate-rules": cmd_validate_rules,
        "diff": cmd_diff,
        "plugin": cmd_plugin,
        "completion": cmd_completion,
        "container": cmd_container,
        "k8s": cmd_k8s,
        "fleet": cmd_fleet,
        "cloak": cmd_cloak,
        "autopsy": cmd_autopsy,
        "tui": cmd_tui,
        "stealth": cmd_stealth,
        "deps": cmd_deps,
        "profile": cmd_profile,
        "serve": cmd_serve,
    }

    try:
        commands[args.command](args)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        from tokenade.core.errors import TokenadeError
        logger.exception("Command failed")
        if isinstance(e, TokenadeError):
            print(f"\n❌ {e}")
        else:
            print(f"\n❌ Unexpected error: {e}")
            print("   Run with --verbose for full traceback")
            print("   Logs: ~/.tokenade/logs/")
        sys.exit(1)
