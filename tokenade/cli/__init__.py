"""Tokenade CLI - Main entry point and argument parser."""
import argparse
import logging
import sys

from tokenade.cli.session import cmd_extract, cmd_export, cmd_load, cmd_transfer, cmd_inject_profile
from tokenade.cli.security import cmd_encrypt, cmd_decrypt, cmd_rekey
from tokenade.cli.proxy import cmd_proxy
from tokenade.cli.management import cmd_sessions, cmd_health, cmd_refresh, cmd_share, cmd_unshare, cmd_sync, cmd_monitor, cmd_analytics
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
    commands="setup config extract transfer test fingerprint validate export load inject-profile encrypt decrypt rekey batch-export batch-load health refresh proxy sessions share unshare sync validate-rules diff plugin completion"

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
            print("\n🌐 Available plugins from registry:")
            plugins = registry.search()
            if not plugins:
                print("   No plugins found in registry")
            for p in plugins:
                print(f"   • {p['name']} v{p.get('version', '?')} — {p.get('description', '')}")
        else:
            print("\n📦 Installed plugins:")
            installed = loader.discover()
            if not installed:
                print("   No plugins installed. Use 'tokenade plugin install <name>' to install.")
            for p in installed:
                print(f"   • {p['name']} v{p.get('version', '?')} ({p.get('type', '?')}) — {p.get('description', '')}")

    elif args.plugin_command == "install":
        print(f"\n📥 Installing plugin: {args.name}")
        if registry.install(args.name):
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
            print(f"❌ Plugin not found: {args.name}")
            return
        print(f"\n📋 Plugin: {plugin['name']}")
        print(f"   Version: {plugin.get('version', '?')}")
        print(f"   Type: {plugin.get('type', '?')}")
        print(f"   Author: {plugin.get('author', '?')}")
        print(f"   Description: {plugin.get('description', '')}")
        if plugin.get("dependencies"):
            print(f"   Dependencies: {', '.join(plugin['dependencies'])}")

    else:
        print("Usage: tokenade plugin {list|install|uninstall|info}")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("tokenade")


def setup_logging(verbose: bool = False):
    """Configure logging level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.getLogger("tokenade").setLevel(level)


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

    # Unshare
    unshare_parser = subparsers.add_parser("unshare", help="Revoke a shared session")
    unshare_parser.add_argument("session_id", help="Session ID to revoke")
    unshare_parser.add_argument("--list", action="store_true", help="List all active shares")

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

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

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
        "refresh": cmd_refresh,
        "proxy": cmd_proxy,
        "sessions": cmd_sessions,
        "share": cmd_share,
        "unshare": cmd_unshare,
        "sync": cmd_sync,
        "monitor": cmd_monitor,
        "analytics": cmd_analytics,
        "validate-rules": cmd_validate_rules,
        "diff": cmd_diff,
        "plugin": cmd_plugin,
        "completion": cmd_completion,
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
