"""Tokenade CLI - Main entry point and argument parser."""

import argparse
import asyncio
import json
import logging
import os
import sys
import time

from tokenade.cli.session import cmd_extract, cmd_load, cmd_transfer, cmd_inject_profile
from tokenade.cli.session_export import cmd_export, cmd_convert
from tokenade.cli.handlers.session_ops import cmd_inspect
from tokenade.cli.security import cmd_encrypt, cmd_decrypt, cmd_rekey
from tokenade.cli.proxy import cmd_proxy
from tokenade.cli.management import (
    cmd_sessions,
    cmd_health,
    cmd_refresh,
    cmd_share,
    cmd_unshare,
    cmd_sync,
    cmd_monitor,
    cmd_refresh_oauth,
    cmd_oauth_config,
    cmd_batch_refresh,
    cmd_cicd,
    cmd_ci,
    cmd_validate_session,
    cmd_encrypted_refresh,
    cmd_launch,
    cmd_refresh_browser,
    cmd_accounts,
    cmd_daemon,
    cmd_versions,
    cmd_rollback,
    cmd_session_diff,
    cmd_logs,
    cmd_health_report,
    cmd_mobile_import,
    cmd_clone_profile,
    cmd_import,
    cmd_container,
    cmd_k8s,
    cmd_fleet,
    cmd_autopsy,
    cmd_cloak,
    cmd_tui,
    cmd_vault,
    cmd_dashboard,
    cmd_share_url,
)
from tokenade.cli.sync_remote import cmd_sync_remote
from tokenade.cli.advanced import (
    cmd_batch_export,
    cmd_batch_load,
    cmd_validate,
    cmd_validate_rules,
    cmd_diff,
    cmd_fingerprint,
    cmd_test,
    cmd_setup,
)

VISIBLE_COMMANDS = (
    "config",
    "inspect",
    "run",
    "test",
    "fingerprint",
    "validate",
    "export",
    "convert",
    "load",
    "encrypt",
    "decrypt",
    "rekey",
    "health",
    "sessions",
    "plugin",
    "completion",
    "cloak",
    "launch",
    "refresh-browser",
    "recommend",
    "proxy",
    "gateway",
    "dashboard",
    "vault",
    "sync-remote",
)

SENSITIVE_CONFIG_KEYS = ("password", "secret", "token", "api_key", "client_secret")


def _is_sensitive_config_key(key: str) -> bool:
    lowered = str(key).lower()
    return any(s in lowered for s in SENSITIVE_CONFIG_KEYS) or lowered in (
        "encryption_password", "supabase_anon_key")


def _redact_config(config) -> dict:
    """Deep-copy a config dict with sensitive values replaced by [redacted]."""
    if not isinstance(config, dict):
        return config
    redacted = {}
    for k, v in config.items():
        if _is_sensitive_config_key(k):
            redacted[k] = "[redacted]"
        elif isinstance(v, dict):
            redacted[k] = _redact_config(v)
        else:
            redacted[k] = v
    return redacted


def cmd_run(args):
    """Run executable plugin operations from a nested request.json file."""
    from tokenade.core.request_config import RequestConfigError, load_request_config
    from tokenade.core.integration.plugin_loader import PluginLoader
    from tokenade.core.integration.plugin_runner import PluginRunner
    from tokenade.plugin.api import PluginRunErrorCode

    try:
        request_config = load_request_config(args.request)
    except RequestConfigError as exc:
        envelope = {
            "success": False,
            "operation": "run",
            "results": [],
            "error": {
                "code": PluginRunErrorCode.ARGUMENT_ERROR.value,
                "message": str(exc),
            },
        }
        print(json.dumps(envelope, ensure_ascii=False))
        raise SystemExit(2)

    if request_config.operation != "run":
        envelope = {
            "success": False,
            "operation": request_config.operation,
            "results": [],
            "error": {
                "code": PluginRunErrorCode.ARGUMENT_ERROR.value,
                "message": "request.operation must be 'run' for tokenade run",
            },
        }
        print(json.dumps(envelope, ensure_ascii=False))
        raise SystemExit(2)

    runner = PluginRunner()
    loader = PluginLoader()
    results = []
    exit_code = 0

    for plugin in request_config.plugins_for_role("run"):
        run_role = plugin.role_config("run")
        method = run_role.get("method")
        if not plugin.required and loader.get_manifest(plugin.name) is None:
            results.append(
                {
                    "success": True,
                    "plugin": plugin.name,
                    "method": method or "",
                    "data": {
                        "skipped": True,
                        "reason": "optional plugin not installed",
                    },
                    "error": None,
                }
            )
            continue

        if method is not None and not isinstance(method, str):
            result_data = {
                "success": False,
                "plugin": plugin.name,
                "method": "",
                "data": None,
                "error": {
                    "code": PluginRunErrorCode.ARGUMENT_ERROR.value,
                    "message": f"plugin {plugin.name} roles.run.method must be a string",
                },
            }
            results.append(result_data)
            exit_code = 2
            if request_config.stop_on_error:
                break
            continue
        else:
            result = runner.run(plugin.name, plugin.config, method)
        results.append(result.to_dict())

        if not result.success:
            if result.error and result.error.code == PluginRunErrorCode.PLUGIN_FAILURE:
                exit_code = 1
            else:
                exit_code = 2
            if request_config.stop_on_error:
                break

    if not results:
        envelope = {
            "success": False,
            "operation": "run",
            "results": [],
            "error": {
                "code": PluginRunErrorCode.ARGUMENT_ERROR.value,
                "message": "request.plugins must include at least one plugin with roles.run",
            },
        }
        print(json.dumps(envelope, ensure_ascii=False))
        raise SystemExit(2)

    success = all(result.get("success") for result in results)
    envelope = {
        "success": success,
        "operation": "run",
        "results": results,
        "error": None
        if success
        else next((r.get("error") for r in results if r.get("error")), None),
    }
    print(json.dumps(envelope, ensure_ascii=False))
    if exit_code:
        raise SystemExit(exit_code)


def cmd_gateway(args):
    """Run hidden gateway control plane from a nested request.json file."""
    from tokenade.core.gateway.server import (
        GatewayConfigError,
        create_gateway_control_plane,
    )
    from tokenade.core.request_config import RequestConfigError, load_request_config

    try:
        request_config = load_request_config(args.request)
        control_plane = create_gateway_control_plane(request_config)
    except (GatewayConfigError, RequestConfigError) as exc:
        envelope = {
            "success": False,
            "operation": "gateway",
            "error": {
                "code": "GATEWAY_CONFIG_ERROR",
                "message": str(exc),
            },
        }
        print(json.dumps(envelope, ensure_ascii=False))
        raise SystemExit(2)

    print(json.dumps(control_plane.status(), ensure_ascii=False), flush=True)
    control_plane.serve_forever()


def cmd_config(args):
    """Manage configuration (~/.tokenade/config.json)."""
    from tokenade.core.config import load_config, DEFAULTS

    config = load_config()

    if args.config_command == "path":
        print(config.config_path)

    elif args.config_command == "show":
        print(f"\n[LIST] Tokenade Config ({config.config_path})\n")
        for key in sorted(DEFAULTS.keys()):
            value = config.get(key)
            default = DEFAULTS[key]
            marker = "" if value != default else " (default)"
            if _is_sensitive_config_key(key) and value != default:
                value = "[redacted]"
            print(f"   {key}: {value}{marker}")

    elif args.config_command == "get":
        if not args.key:
            print("[ERROR] Usage: tokenade config get <key>")
            return
        value = config.get(args.key)
        if value is None:
            print(f"[ERROR] Unknown config key: {args.key}")
        elif _is_sensitive_config_key(args.key) and value:
            print("[redacted]")
        else:
            print(value)

    elif args.config_command == "set":
        if not args.key or not args.value:
            print("[ERROR] Usage: tokenade config set <key> <value>")
            return
        # Type coercion for booleans
        value = args.value
        if value.lower() in ("true", "false"):
            value = value.lower() == "true"
        elif value.isdigit():
            value = int(value)
        config.set(args.key, value)
        config.save()
        if _is_sensitive_config_key(args.key) and value:
            print(f"[OK] Set {args.key} = [redacted]")
        else:
            print(f"[OK] Set {args.key} = {value}")


COMMAND_DESCRIPTIONS = {
    "config": "Manage configuration",
    "inspect": "Inspect session metadata and validity",
    "run": "Run an executable installed plugin",
    "test": "Test portability",
    "fingerprint": "Manage fingerprints",
    "validate": "Validate sessions",
    "export": "Export session from browser",
    "convert": "Convert session format",
    "load": "Load session file into browser",
    "encrypt": "Encrypt session file",
    "decrypt": "Decrypt session file",
    "rekey": "Change encryption password",
    "health": "Check session health",
    "sessions": "Manage saved sessions",
    "plugin": "Manage plugins",
    "completion": "Generate shell completion",
    "cloak": "CloakBrowser stealth binary management",
    "launch": "Launch a browser with session",
    "refresh-browser": "Refresh session through a browser-backed flow",
    "recommend": "Recommend site/plugin/browser",
    "proxy": "Proxy management and verification",
    "gateway": "Start local session proxy gateway",
    "dashboard": "Launch web dashboard",
    "vault": "Manage encrypted session vault",
    "sync-remote": "Synchronize sessions with remote storage",
}


def cmd_completion(args):
    """Generate shell completion scripts."""
    shell = args.shell
    commands = " ".join(VISIBLE_COMMANDS)

    if shell == "bash":
        print(
            '''# Tokenade bash completion
_tokenade() {
    local cur prev commands
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    commands="'''
            + commands
            + """"

    if [[ ${cur} == -* ]] ; then
        COMPREPLY=( $(compgen -W "--help --version --verbose" -- ${cur}) )
        return 0
    fi

    COMPREPLY=( $(compgen -W "${commands}" -- ${cur}) )
    return 0
}
complete -F _tokenade tokenade
"""
        )
    elif shell == "zsh":
        zsh_lines = ["# Tokenade zsh completion", "_tokenade() {", "    local commands", "    commands=("]
        for cmd in VISIBLE_COMMANDS:
            desc = COMMAND_DESCRIPTIONS.get(cmd, cmd)
            zsh_lines.append(f"        '{cmd}:{desc}'")
        zsh_lines.extend(["    )", "    _describe 'tokenade' commands", "}", "compdef _tokenade tokenade", ""])
        print("\n".join(zsh_lines))
    elif shell == "fish":
        fish_lines = ["# Tokenade fish completion", "complete -c tokenade -f"]
        for cmd in VISIBLE_COMMANDS:
            desc = COMMAND_DESCRIPTIONS.get(cmd, cmd)
            fish_lines.append(f'complete -c tokenade -n "__fish_use_subcommand" -a "{cmd}" -d "{desc}"')
        fish_lines.append("")
        print("\n".join(fish_lines))
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
            print("\n[NET] Available plugins from registry:")
            plugins = registry.search()
            if not plugins:
                print("   No plugins found in registry")
            for p in plugins:
                status = " [OK] installed" if p["name"] in installed_names else ""
                print(
                    f"   - {p['name']} v{p.get('version', '?')} - {p.get('description', '')}{status}"
                )
                from tokenade.core.integration.plugin_dependencies import (
                    check_runtime_dependencies,
                )

                report = check_runtime_dependencies(p)
                for issue in report.issues:
                    print(
                        f"      missing {issue.kind}: {issue.requirement} ({issue.reason})"
                    )
                extras = []
                if p.get("type"):
                    extras.append(f"type: {p['type']}")
                run_section = p.get("run")
                if isinstance(run_section, dict) and run_section.get("enabled"):
                    methods = run_section.get("methods") or {}
                    default = run_section.get("default_method") or next(
                        iter(methods), ""
                    )
                    extras.append(
                        "run: "
                        + ", ".join(
                            f"{m} (default)" if m == default else m for m in methods
                        )
                    )
                deps = p.get("dependencies") or []
                if deps:
                    extras.append(f"deps: {len(deps)} ({', '.join(deps)})")
                if extras:
                    print("      " + " | ".join(extras))
        else:
            # Load plugins so we can show lifecycle state; graceful if load fails
            try:
                loader.load_all()
            except Exception:
                pass
            print("\n[PKG] Installed plugins:")
            installed = loader.discover()
            if not installed:
                print(
                    "   No plugins installed. Use 'tokenade plugin install <name>' to install."
                )
            for p in installed:
                name = p["name"]
                loaded = loader.get_plugin(name)
                state_str = loaded.state.value if loaded else "not loaded"
                enabled = " [OK]" if p.get("enabled", True) else " (disabled)"
                print(
                    f"   - {p['name']} v{p.get('version', '?')} ({p.get('type', '?')}) [{state_str}]{enabled} - {p.get('description', '')}"
                )
                # Show health from shared context when available
                if loaded:
                    try:
                        from tokenade.core.context import SharedContext

                        ctx = SharedContext()
                        plugin_health = ctx.plugins.get_health(name)
                        if plugin_health is not None:
                            health_str = "healthy" if plugin_health else "unhealthy"
                            print(f"      health: {health_str}")
                    except Exception:
                        pass
                run_info = ""
                try:
                    from tokenade.plugin.api import parse_plugin_run_spec

                    run_spec = parse_plugin_run_spec(p)
                except Exception:
                    run_spec = None
                if run_spec is not None and run_spec.enabled:
                    run_info = "run: " + ", ".join(
                        f"{m} (default)" if m == run_spec.default_method else m
                        for m in run_spec.methods
                    )
                declared_deps = p.get("dependencies") or []
                if declared_deps or run_info:
                    installed_names = {m["name"] for m in installed}
                    parts = [run_info] if run_info else []
                    if declared_deps:
                        annotated = ", ".join(
                            d if d in installed_names else f"{d} [X]"
                            for d in declared_deps
                        )
                        parts.append(f"deps: {len(declared_deps)} ({annotated})")
                    print("      " + " | ".join(parts))
                from tokenade.core.integration.plugin_dependencies import (
                    check_runtime_dependencies,
                )

                report = check_runtime_dependencies(p)
                for issue in report.issues:
                    print(
                        f"      missing {issue.kind}: {issue.requirement} ({issue.reason})"
                    )

    elif args.plugin_command == "install":
        git_source = getattr(args, "git", None)
        if git_source and not isinstance(git_source, (bool, type(None))) and str(git_source).strip() and not str(type(git_source)).startswith("<class 'unittest.mock"):
            print(f"\n[IN] Installing plugin from git: {git_source}")
            branch = getattr(args, "branch", None)
            subdir = getattr(args, "subdir", None)
            if registry.install_from_git(git_source, branch=branch, subdirectory=subdir):
                print("   [OK] Plugin(s) installed successfully from git repository")
            else:
                print("   [ERROR] Failed to install plugin from git")
            return

        reg_name = getattr(args, "registry", None)
        print(f"\n[IN] Installing plugin: {args.name}")
        if reg_name:
            print(f"   Registry: {reg_name}")
        # Detect multi-registry conflicts before install
        plugin_meta, conflicts = registry.find_plugin(args.name, reg_name)
        if plugin_meta is None:
            print(f"   [ERROR] Plugin not found: {args.name}")
            return
        if conflicts and not reg_name:
            print(f"   [WARN] Found in multiple registries:")
            for c in conflicts:
                print(f"      - {c.get('_registry', '?')} (v{c.get('version', '?')})")
            print(f"   Use: tokenade plugin install {args.name} --registry <name>")
            return
        before = {p["name"] for p in loader.discover()}
        if registry.install(args.name, registry_name=reg_name):
            from tokenade.core.integration.plugin_verifier import PluginVerifier

            verifier = PluginVerifier()
            verifier.register_plugin(args.name)
            after = {p["name"] for p in loader.discover()}
            deps_installed = sorted(after - before)
            if deps_installed:
                print(f"   [PKG] Dependencies installed: {', '.join(deps_installed)}")
            print("   [OK] Plugin installed successfully")
            installed_manifest = loader.get_manifest(args.name)
            if installed_manifest:
                from tokenade.core.integration.plugin_dependencies import (
                    check_runtime_dependencies,
                )

                runtime_report = check_runtime_dependencies(installed_manifest)
                if not runtime_report.ready:
                    print("   [WARN] Plugin runtime dependencies are missing:")
                    for issue in runtime_report.issues:
                        print(
                            f"      - {issue.kind}: {issue.requirement} ({issue.reason})"
                        )
                    print(f"   Check: tokenade plugin check-deps {args.name}")
        else:
            print("   [ERROR] Failed to install plugin")

    elif args.plugin_command == "uninstall":
        print(f"\n[DEL] Uninstalling plugin: {args.name}")
        if registry.uninstall(args.name):
            print("   [OK] Plugin uninstalled successfully")
        else:
            print(
                "   [ERROR] Failed to uninstall plugin (not installed or dependency conflict)"
            )

    elif args.plugin_command == "info":
        if getattr(args, "json", False) is True:
            print(json.dumps(_plugin_info_payload(args.name, loader, registry), indent=2))
            return
        installed = loader.discover()
        plugin = None
        for p in installed:
            if p["name"] == args.name:
                plugin = p
                break
        if not plugin:
            registry_details = registry.get_plugin_details(args.name)
            if registry_details:
                print(f"\n[LIST] Plugin: {args.name} (not installed)")
                print(f"   Version: {registry_details.get('version', '?')}")
                print(f"   Type: {registry_details.get('type', '?')}")
                print(f"   Author: {registry_details.get('author', '?')}")
                print(f"   Description: {registry_details.get('description', '')}")
                if registry_details.get("dependencies"):
                    print(
                        f"   Dependencies: {', '.join(registry_details['dependencies'])}"
                    )
                if registry_details.get("api_version"):
                    print(f"   API version: {registry_details['api_version']}")
                if registry_details.get("category"):
                    print(f"   Category: {registry_details['category']}")
                run_section = registry_details.get("run")
                if isinstance(run_section, dict) and run_section.get("enabled"):
                    methods = run_section.get("methods") or {}
                    default = run_section.get("default_method") or next(
                        iter(methods), ""
                    )
                    print(
                        "   Runnable methods: "
                        + ", ".join(
                            f"{m} (default)" if m == default else m for m in methods
                        )
                    )
                from tokenade.core.integration.plugin_dependencies import (
                    check_runtime_dependencies,
                )

                for issue in check_runtime_dependencies(registry_details).issues:
                    print(
                        f"   Missing {issue.kind}: {issue.requirement} ({issue.reason})"
                    )
                print(f"   Install: tokenade plugin install {args.name}")
            else:
                print(f"[ERROR] Plugin not found: {args.name}")
            return
        installed_ver = plugin.get("version", "?")
        enabled = plugin.get("enabled", True)
        print(f"\n[LIST] Plugin: {plugin['name']}")
        print(f"   Version: {installed_ver}")
        print(f"   Type: {plugin.get('type', '?')}")
        print(f"   Author: {plugin.get('author', '?')}")
        print(f"   Description: {plugin.get('description', '')}")
        print(f"   Status: {'enabled' if enabled else 'disabled'}")
        # Lifecycle state, config, and health from the loader / shared context
        try:
            loader.load_all()
        except Exception:
            pass
        loaded = loader.get_plugin(args.name)
        if loaded:
            print(f"   Lifecycle: {loaded.state.value}")
            if loaded.error:
                print(f"   Error: {loaded.error}")
            if loaded.config:
                try:
                    print(f"   Config: {json.dumps(_redact_config(loaded.config))}")
                except (TypeError, ValueError):
                    print(f"   Config: {_redact_config(loaded.config)}")
            try:
                from tokenade.core.context import SharedContext

                ctx = SharedContext()
                plugin_health = ctx.plugins.get_health(args.name)
                if plugin_health is not None:
                    print(f"   Health: {'healthy' if plugin_health else 'unhealthy'}")
            except Exception:
                pass
        if plugin.get("dependencies"):
            manifest_names = {m["name"] for m in installed}
            annotated = [
                f"{d} [OK]" if d in manifest_names else f"{d} [X] missing"
                for d in plugin["dependencies"]
            ]
            print(f"   Dependencies: {', '.join(annotated)}")
        if plugin.get("api_version"):
            print(f"   API version: {plugin['api_version']}")
        else:
            print("   API version: legacy (no api_version declared)")
        if plugin.get("entry_class"):
            print(f"   Entry class: {plugin['entry_class']}")
        if plugin.get("category"):
            print(f"   Category: {plugin['category']}")
        if plugin.get("icon"):
            print(f"   Icon: {plugin['icon']}")
        if plugin.get("tags"):
            print(f"   Tags: {', '.join(plugin['tags'])}")
        try:
            from tokenade.plugin.api import parse_plugin_run_spec

            run_spec = parse_plugin_run_spec(plugin)
        except Exception as e:
            run_spec = None
            print(f"   Run spec: invalid ({e})")
        if run_spec is not None:
            if run_spec.enabled:
                methods = ", ".join(
                    f"{m} (default)" if m == run_spec.default_method else m
                    for m in run_spec.methods
                )
                print(f"   Runnable methods: {methods}")
                print(f"   Run: tokenade run --request request.json")
            else:
                print("   Runnable methods: none (internal only)")
        from tokenade.core.integration.plugin_dependencies import (
            check_runtime_dependencies,
        )

        runtime_report = check_runtime_dependencies(plugin)
        if runtime_report.ready:
            print("   Runtime dependencies: ready")
        else:
            for issue in runtime_report.issues:
                print(f"   Missing {issue.kind}: {issue.requirement} ({issue.reason})")
        registry_details = registry.get_plugin_details(args.name)
        if registry_details and registry_details.get("version") != installed_ver:
            print(
                f"   Registry version: {registry_details['version']} (update available)"
            )
        from tokenade.core.integration.plugin_verifier import PluginVerifier

        verifier = PluginVerifier()
        if verifier._local_checksums.get(args.name):
            result = verifier.verify(args.name)
            print(
                f"   Integrity: {'[OK] verified' if result.verified else '[X] tampered'}"
            )
        else:
            print(
                f"   Integrity: unregistered (run 'tokenade plugin verify' to register)"
            )

    elif args.plugin_command == "enable":
        if loader.enable(args.name):
            print(f"[OK] Plugin enabled: {args.name}")
        else:
            print(f"[ERROR] Plugin not found: {args.name}")

    elif args.plugin_command == "disable":
        if loader.disable(args.name):
            print(f"[OK] Plugin disabled: {args.name}")
        else:
            print(f"[ERROR] Plugin not found: {args.name}")

    elif args.plugin_command == "update":
        force = getattr(args, "force", False)
        dry_run = getattr(args, "dry_run", False)
        name = getattr(args, "name", None)
        if dry_run:
            print("\n[SEARCH] Dry run - no changes will be made")
        if name:
            print(f"\n[SYNC] Updating {name}...")
        else:
            outdated = registry.get_outdated()
            if not outdated and not force:
                print("\n[OK] All plugins are up to date.")
                return
            print(f"\n[SYNC] Updating plugins...")
        results = registry.update(plugin_name=name, force=force, dry_run=dry_run)
        if results["updated"]:
            for item in results["updated"]:
                print(f"   [OK] {item}")
                if not dry_run:
                    from tokenade.core.integration.plugin_verifier import PluginVerifier

                    updated_name = item.split()[0]
                    PluginVerifier().register_plugin(updated_name)
        if results["skipped"] and (name or force):
            for item in results["skipped"]:
                print(f"   [SKIP] Skipped (up to date): {item}")
        if results["failed"]:
            for item in results["failed"]:
                print(f"   [ERROR] Failed: {item}")
        if not any(results.values()):
            print("   Nothing to update.")

    elif args.plugin_command == "sync":
        print("\n[SYNC] Syncing plugins from registry...")
        plugins = registry.get_popular(limit=100)
        installed = {p.name for p in loader.list_all()}
        to_install = [p for p in plugins if p.get("name") not in installed]

        if not to_install:
            print("[OK] All available plugins already installed.")
        else:
            print(f"   Installing {len(to_install)} plugin(s)...")
            for p in to_install:
                name = p.get("name", "")
                success = registry.install(name)
                if success:
                    print(f"   [OK] {name}")
                else:
                    print(f"   [ERROR] {name}")
            loader.load_all()
            print(f"\n   Done. {len(loader.list_all())} plugins installed.")

    elif args.plugin_command == "reload":
        try:
            loader.load_all()
        except Exception:
            pass
        loaded = loader.reload(args.name)
        if loaded:
            print(
                f"[OK] Plugin reloaded: {args.name} v{loaded.version} ({loaded.state.value})"
            )
        else:
            print(f"[ERROR] Failed to reload: {args.name}")

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

    elif args.plugin_command == "deps":
        from tokenade.core.integration.dependency_graph import DependencyGraph

        installed_manifests = loader.discover()
        graph = DependencyGraph()
        for plugin in installed_manifests:
            graph.add_plugin(plugin["name"], plugin.get("dependencies", []))
        if args.name not in graph.get_all_plugins():
            print(f"[ERROR] Plugin not found: {args.name}")
            return
        if getattr(args, "json", False) is True:
            tree = _plugin_dependency_json(installed_manifests, graph, args.name)
            print(json.dumps(tree, indent=2))
            return
        print(f"\n   [PKG] Dependency tree for {args.name}:")
        for line in _plugin_dependency_lines(installed_manifests, graph, args.name):
            print("   " + line)

    elif args.plugin_command == "check-deps":
        if getattr(args, "json", False) is True:
            print(json.dumps(_plugin_check_deps_payload(args, loader), indent=2))
            return
        from tokenade.core.integration.dependency_graph import DependencyGraph
        from tokenade.core.integration.dependency_resolver import DependencyResolver

        graph = DependencyGraph()
        for plugin in loader.discover():
            graph.add_plugin(plugin["name"], plugin.get("dependencies", []))
        resolver = DependencyResolver(graph)
        if args.name:
            if args.name not in graph.get_all_plugins():
                print(f"[ERROR] Plugin not found: {args.name}")
                return
            missing = [
                d
                for d in graph.get_dependencies(args.name)
                if d not in graph.get_all_plugins()
            ]
            if missing:
                print(
                    f"\n   [WARN] Missing dependencies for {args.name}: {', '.join(missing)}"
                )
            else:
                print(f"\n   [OK] No missing dependencies for {args.name}")
            from tokenade.core.integration.plugin_dependencies import (
                check_runtime_dependencies,
            )

            manifest = next(p for p in loader.discover() if p["name"] == args.name)
            runtime_report = check_runtime_dependencies(manifest)
            for issue in runtime_report.issues:
                print(
                    f"   [WARN] Missing {issue.kind}: {issue.requirement} ({issue.reason})"
                )
        else:
            missing = resolver.check_missing()
            circular = resolver.check_circular()
            depth = resolver.check_depth()
            print("\n   Dependency check (all plugins):")
            if missing:
                print(f"   [WARN] Missing dependencies: {', '.join(missing)}")
            else:
                print("   [OK] No missing dependencies")
            if circular:
                print(f"   [SYNC] Circular dependencies: {', '.join(circular)}")
            else:
                print("   [OK] No circular dependencies")
            if depth:
                print(f"   [WARN] Depth violations:")
                for e in depth:
                    print(f"      {e}")
            else:
                print("   [OK] No depth violations")
            from tokenade.core.integration.plugin_dependencies import (
                check_runtime_dependencies,
            )

            for manifest in loader.discover():
                for issue in check_runtime_dependencies(manifest).issues:
                    print(
                        f"   [WARN] {manifest['name']} missing {issue.kind}: "
                        f"{issue.requirement} ({issue.reason})"
                    )

    elif args.plugin_command == "registry":
        reg_action = getattr(args, "registry_action", None)
        if reg_action == "add":
            name = args.name
            source = args.source
            try:
                entry = registry.add_registry(name, source)
                print(f"\n[OK] Registry added: {entry['name']}")
                print(f"   Type: {entry['type']}")
                print(f"   Source: {entry['source']}")
            except ValueError as e:
                print(f"\n[ERROR] {e}")
        elif reg_action == "remove":
            if registry.remove_registry(args.name):
                print(f"\n[OK] Registry removed: {args.name}")
            else:
                print(f"\n[ERROR] Registry not found: {args.name}")
        elif reg_action == "list":
            regs = registry.list_registries()
            print(f"\n{'=' * 60}")
            print(f"TOKENADE - Registries ({len(regs)})")
            print(f"{'=' * 60}")
            for r in regs:
                status = "enabled" if r.get("enabled", True) else "disabled"
                print(f"\n  {r['name']} [{r['type']}] ({status})")
                print(f"    Source: {r['source']}")
            print(f"\n{'=' * 60}\n")
        else:
            print("Usage: tokenade plugin registry {add,remove,list}")

    elif args.plugin_command == "configure":
        _plugin_configure(args)

    else:
        print(
            "Usage: tokenade plugin {list|install|uninstall|info|enable|disable|update|reload|search|categories|popular|recent|rate|verify|outdated|browse|test|deps|check-deps|configure}"
        )


def _plugin_dependency_lines(manifests, graph, name, indent=0, seen=None):
    """Annotated dependency tree lines: ``name vX.Y.Z [OK]`` / ``[X] missing``."""
    if seen is None:
        seen = set()
    version_by_name = {m["name"]: m.get("version", "?") for m in manifests}
    prefix = "  " * indent
    lines = []
    for dep in graph.get_dependencies(name):
        marker = "[OK]" if dep in version_by_name else "[X] missing"
        lines.append(f"{prefix}{dep} v{version_by_name.get(dep, '?')} {marker}")
        if dep in version_by_name and dep not in seen:
            seen.add(dep)
            lines.extend(
                _plugin_dependency_lines(
                    manifests, graph, dep, indent + 1, seen
                )
            )
    return lines


def _plugin_dependency_json(manifests, graph, name, seen=None):
    """Nested JSON dependency tree (cycle-safe) for ``plugin deps --json``."""
    if seen is None:
        seen = set()
    version_by_name = {m["name"]: m.get("version", "?") for m in manifests}
    node = {
        "name": name,
        "version": version_by_name.get(name, "?"),
        "installed": name in version_by_name,
    }
    deps = []
    for dep in graph.get_dependencies(name):
        if dep in seen:
            deps.append(
                {
                    "name": dep,
                    "version": version_by_name.get(dep, "?"),
                    "installed": dep in version_by_name,
                    "cycle": True,
                }
            )
            continue
        seen.add(dep)
        deps.append(_plugin_dependency_json(manifests, graph, dep, seen))
    node["dependencies"] = deps
    return node


def _runtime_issues_payload(manifest):
    """Structured runtime-dependency issues for a manifest."""
    from tokenade.core.integration.plugin_dependencies import (
        check_runtime_dependencies,
    )

    report = check_runtime_dependencies(manifest)
    return {
        "ready": report.ready,
        "issues": [
            {"kind": i.kind, "requirement": i.requirement, "reason": i.reason}
            for i in report.issues
        ],
    }


def _plugin_info_payload(name, loader, registry):
    """Structured plugin info for ``plugin info --json``."""
    installed = loader.discover()
    plugin = None
    for p in installed:
        if p["name"] == name:
            plugin = p
            break
    if not plugin:
        registry_details = registry.get_plugin_details(name)
        if not registry_details:
            return {"name": name, "installed": False, "available": False}
        run = None
        run_section = registry_details.get("run")
        if isinstance(run_section, dict) and run_section.get("enabled"):
            methods = run_section.get("methods") or {}
            run = {
                "enabled": True,
                "default_method": run_section.get("default_method")
                or next(iter(methods), ""),
                "methods": list(methods),
            }
        return {
            "name": name,
            "installed": False,
            "available": True,
            "version": registry_details.get("version"),
            "type": registry_details.get("type"),
            "author": registry_details.get("author"),
            "description": registry_details.get("description"),
            "dependencies": list(registry_details.get("dependencies") or []),
            "api_version": registry_details.get("api_version"),
            "category": registry_details.get("category"),
            "run": run,
            "runtime_dependencies": _runtime_issues_payload(registry_details),
            "install": f"tokenade plugin install {name}",
        }
    installed_names = {m["name"] for m in installed}
    payload = {
        "name": plugin["name"],
        "installed": True,
        "version": plugin.get("version"),
        "type": plugin.get("type"),
        "author": plugin.get("author"),
        "description": plugin.get("description"),
        "status": "enabled" if plugin.get("enabled", True) else "disabled",
    }
    try:
        loader.load_all()
    except Exception:
        pass
    loaded = loader.get_plugin(name)
    if loaded:
        payload["lifecycle"] = loaded.state.value
        if loaded.error:
            payload["error"] = loaded.error
        payload["config"] = _redact_config(loaded.config) or None
        try:
            from tokenade.core.context import SharedContext

            ctx = SharedContext()
            plugin_health = ctx.plugins.get_health(name)
            if plugin_health is not None:
                payload["health"] = "healthy" if plugin_health else "unhealthy"
        except Exception:
            pass
    payload["dependencies"] = [
        {"name": d, "installed": d in installed_names}
        for d in (plugin.get("dependencies") or [])
    ]
    payload["api_version"] = plugin.get("api_version")
    payload["legacy_api"] = not plugin.get("api_version")
    payload["entry_class"] = plugin.get("entry_class")
    payload["category"] = plugin.get("category")
    payload["icon"] = plugin.get("icon")
    payload["tags"] = list(plugin.get("tags") or [])
    try:
        from tokenade.plugin.api import parse_plugin_run_spec

        run_spec = parse_plugin_run_spec(plugin)
    except Exception as e:
        run_spec = None
        payload["run_spec_error"] = str(e)
    if run_spec is not None:
        payload["run"] = {
            "enabled": run_spec.enabled,
            "default_method": run_spec.default_method,
            "methods": list(run_spec.methods),
        }
        if run_spec.enabled:
            payload["run_invocation"] = "tokenade run --request request.json"
    payload["runtime_dependencies"] = _runtime_issues_payload(plugin)
    registry_details = registry.get_plugin_details(name)
    if registry_details and registry_details.get("version") != plugin.get("version"):
        payload["registry_version"] = registry_details["version"]
    from tokenade.core.integration.plugin_verifier import PluginVerifier

    verifier = PluginVerifier()
    if verifier._local_checksums.get(name):
        result = verifier.verify(name)
        payload["integrity"] = "verified" if result.verified else "tampered"
    else:
        payload["integrity"] = "unregistered"
    return payload


def _plugin_check_deps_payload(args, loader):
    """Structured dependency report for ``plugin check-deps --json``."""
    from tokenade.core.integration.dependency_graph import DependencyGraph
    from tokenade.core.integration.dependency_resolver import DependencyResolver

    manifests = loader.discover()
    graph = DependencyGraph()
    for plugin in manifests:
        graph.add_plugin(plugin["name"], plugin.get("dependencies", []))
    resolver = DependencyResolver(graph)
    runtime_issues = {}
    for manifest in manifests:
        report = _runtime_issues_payload(manifest)
        if report["issues"]:
            runtime_issues[manifest["name"]] = report["issues"]
    if args.name:
        if args.name not in graph.get_all_plugins():
            return {"plugin": args.name, "found": False}
        return {
            "plugin": args.name,
            "found": True,
            "missing": [
                d
                for d in graph.get_dependencies(args.name)
                if d not in graph.get_all_plugins()
            ],
            "runtime_issues": runtime_issues.get(args.name, []),
        }
    return {
        "missing": resolver.check_missing(),
        "circular": resolver.check_circular(),
        "depth": resolver.check_depth(),
        "runtime_issues": runtime_issues,
    }


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
        stars = f"* {p.get('rating', 0):.1f}" if p.get("rating") else ""
        verified = " [OK]" if p.get("verified") else ""
        downloads = f"v {p.get('downloads', 0)}" if p.get("downloads") else ""
        print(f"\n  {p['name']}{verified} v{p.get('version', '?')}")
        print(f"    {p.get('description', '')}")
        meta = " | ".join(filter(None, [stars, downloads, f"by {p.get('author', '')}"]))
        if meta:
            print(f"    {meta}")
        if p.get("tags"):
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
            dl_s = f"v {dl} downloads" if dl is not None else "v n/a"
            rt_s = f"* {rt:.1f}" if rt is not None else "* n/a"
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
        print(f"[OK] Rated {args.name}: {args.rating}/5")
        if args.review:
            print(f"   Review: {args.review}")

        # Sync to GitHub if PAT is set
        from tokenade.core.integration.rating_sync import RatingSync

        sync = RatingSync()
        if sync.has_pat():
            if sync.submit_rating(args.name, args.rating, args.review or ""):
                print("   [NET] Synced to GitHub")
            else:
                print("   [WARN] GitHub sync failed (local rating saved)")
        else:
            print(
                "   [TIP] Set github-token to sync globally: tokenade config set github-token <PAT>"
            )
    else:
        print(f"[ERROR] Failed to rate {args.name} (rating must be 1.0-5.0)")


def _plugin_ratings(registry, args):
    """View global ratings from GitHub."""
    from tokenade.core.integration.rating_sync import RatingSync

    sync = RatingSync()

    global_ratings = sync.get_global_ratings()

    if not global_ratings:
        print("\n  No global ratings found.")
        if not sync.has_pat():
            print(
                "  [TIP] Set github-token to sync ratings: tokenade config set github-token <PAT>"
            )
        return

    name = getattr(args, "name", None)

    if name:
        # Show specific plugin
        if name in global_ratings:
            r = global_ratings[name]
            stars = "*" * int(r.get("rating", 0)) + "*" * (5 - int(r.get("rating", 0)))
            print(f"\n  {name} - {stars} ({r.get('rating', 0):.1f}/5)")
            print(f"  Reviews: {r.get('review_count', 0)}")
            for rev in r.get("reviews", []):
                print(f"    * {rev.get('rating', 0)}: {rev.get('review', '')[:80]}")
        else:
            print(f"\n  No global ratings for: {name}")
    else:
        # Show all
        print(f"\n  [NET] Global Ratings ({len(global_ratings)} plugins)\n")
        for name, r in sorted(global_ratings.items()):
            stars = "*" * int(r.get("rating", 0)) + "*" * (5 - int(r.get("rating", 0)))
            print(
                f"  {stars} {r.get('rating', 0):.1f}  {name}  ({r.get('review_count', 0)} reviews)"
            )
        if not sync.has_pat():
            print(
                f"\n  [TIP] Set github-token to sync: tokenade config set github-token <PAT>"
            )


def _plugin_verify(args):
    """Verify plugin checksums. Auto-registers on first run."""
    from tokenade.core.integration.plugin_verifier import PluginVerifier

    verifier = PluginVerifier()
    plugin_names = (
        [args.name]
        if args.name
        else [
            d.name
            for d in sorted(verifier.plugins_dir.iterdir())
            if d.is_dir()
            and not d.name.startswith(".")
            and (d / "plugin.json").exists()
        ]
    )

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
            icon = "[NOTE]"
            status = f"registered ({r.files_checked} files checksummed)"
        elif r.verified:
            icon = "[OK]"
            status = r.summary
        else:
            icon = "[ERROR]"
            status = r.summary
            all_ok = False
        print(f"\n  {icon} {r.plugin_name}: {status}")
        for err in r.errors:
            print(f"     [WARN] {err}")

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
        print(
            f"    Installed: {p['installed_version']} -> Available: {p['available_version']}"
        )
        if p.get("description"):
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
    print(f"[OK] Marketplace page generated: {path}")
    print(f"   Open in browser: file://{path}")


def _plugin_test(args):
    """Run tests on installed plugins."""
    from tokenade.core.integration.plugin_testing import PluginTestRunner

    runner = PluginTestRunner()
    verbose = getattr(args, "verbose", False)

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
        status = "[OK]" if suite.passed else "[ERROR]"
        print(f"\n{status} {suite.summary()}")
        for result in suite.results:
            icon = "  [OK]" if result.passed else "  [X]"
            msg = (
                f" - {result.message}"
                if result.message and (not result.passed or verbose)
                else ""
            )
            dur = f" ({result.duration:.2f}s)" if verbose and result.duration else ""
            print(f"{icon} {result.test_name}{dur}{msg}")
        total_passed += suite.passed_count
        total_failed += suite.failed_count

    print(f"\n{'=' * 60}")
    print(f"Results: {total_passed} passed, {total_failed} failed")
    print(f"{'=' * 60}\n")


def _plugin_configure(args):
    """Configure plugin settings: --show/--reset/--validate/--set KEY=VALUE."""
    from tokenade.core.integration.plugin_config import PluginConfigManager

    mgr = PluginConfigManager()

    if getattr(args, "show", False):
        config = mgr.get_full_config(args.name)
        if config:
            print(f"\n   [LIST] Config for {args.name}:")
            for k, v in sorted(_redact_config(config).items()):
                print(f"      {k} = {v}")
        else:
            print(f"\n   {args.name}: no config")

    elif getattr(args, "reset", False):
        if mgr.delete_config(args.name):
            print(f"\n   [OK] Config reset to defaults: {args.name}")
        else:
            print(f"\n   No config file to reset: {args.name}")

    elif getattr(args, "validate", False):
        config = mgr.load_config(args.name)
        errors = mgr.validate_config(args.name, config)
        if errors:
            print(f"\n   [ERROR] Config validation errors:")
            for e in errors:
                print(f"      {e}")
        else:
            print(f"\n   [OK] Config valid: {args.name}")

    elif getattr(args, "set", None):
        config = mgr.load_config(args.name)
        for pair in args.set:
            if "=" in pair:
                k, v = pair.split("=", 1)
                # Type coercion
                if v.lower() == "true":
                    v = True
                elif v.lower() == "false":
                    v = False
                else:
                    try:
                        v = int(v)
                    except ValueError:
                        try:
                            v = float(v)
                        except ValueError:
                            pass
                config[k] = v
        if mgr.save_config(args.name, config):
            print(f"\n   [OK] Config saved: {args.name}")
        else:
            print(f"\n   [ERROR] Failed to save config: {args.name}")

    else:
        print(
            "Usage: tokenade plugin configure <name> [--show|--reset|--validate|--set KEY=VALUE ...]"
        )


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
            print(f"\n[OK] Created profile: {profile.name}")
            print(f"   Browser: {profile.browser} | OS: {profile.os}")
            print(f"   ID: {profile.id}")
            if profile.fingerprint.get("navigator"):
                nav = profile.fingerprint["navigator"]
                print(
                    f"   Hardware: {nav.get('hardwareConcurrency', '?')} cores, {nav.get('deviceMemory', '?')} GB RAM"
                )
            if profile.fingerprint.get("webgl"):
                gl = profile.fingerprint["webgl"]
                print(f"   GPU: {gl.get('renderer', '?')}")
            print()
        except ValueError as e:
            print(f"\n[ERROR] {e}\n")

    elif args.profile_command == "list":
        profiles = manager.list_profiles(browser=args.browser, tag=args.tag)
        if not profiles:
            print("\nNo profiles found.\n")
            return
        print(f"\n{'=' * 60}")
        print(f"TOKENADE - Browser Profiles ({len(profiles)} total)")
        print(f"{'=' * 60}")
        for p in profiles:
            last_used = (
                time.strftime("%Y-%m-%d %H:%M", time.localtime(p.last_used))
                if p.last_used
                else "never"
            )
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
            print(f"\n[ERROR] Profile not found: {args.name}\n")
            return
        print(f"\n{'=' * 60}")
        print(f"TOKENADE - Profile: {profile.name}")
        print(f"{'=' * 60}")
        print(f"  ID: {profile.id}")
        print(f"  Browser: {profile.browser}")
        print(f"  OS: {profile.os}")
        print(
            f"  Created: {time.strftime('%Y-%m-%d %H:%M', time.localtime(profile.created_at))}"
        )
        print(
            f"  Updated: {time.strftime('%Y-%m-%d %H:%M', time.localtime(profile.updated_at))}"
        )
        last_used = (
            time.strftime("%Y-%m-%d %H:%M", time.localtime(profile.last_used))
            if profile.last_used
            else "never"
        )
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
            print(
                f"    Cores: {nav.get('hardwareConcurrency', '?')} | RAM: {nav.get('deviceMemory', '?')} GB"
            )
            print(f"    Screen: {scr.get('width', '?')}x{scr.get('height', '?')}")
            print(f"    GPU: {gl.get('renderer', '?')}")
        print(f"\n{'=' * 60}\n")

    elif args.profile_command == "delete":
        if manager.delete_profile(args.name):
            print(f"\n[OK] Deleted profile: {args.name}\n")
        else:
            print(f"\n[ERROR] Profile not found: {args.name}\n")

    elif args.profile_command == "export":
        try:
            path = manager.export_profile(args.name, args.output or f"{args.name}.zip")
            print(f"\n[OK] Exported profile: {path}\n")
        except FileNotFoundError as e:
            print(f"\n[ERROR] {e}\n")

    elif args.profile_command == "import":
        try:
            profile = manager.import_profile(args.archive, name=args.name)
            print(f"\n[OK] Imported profile: {profile.name}\n")
        except (FileNotFoundError, ValueError) as e:
            print(f"\n[ERROR] {e}\n")

    elif args.profile_command == "recent":
        profiles = manager.get_recent_profiles(limit=args.limit)
        if not profiles:
            print("\nNo recently used profiles.\n")
            return
        print(f"\nRecently used profiles:")
        for i, p in enumerate(profiles, 1):
            last_used = (
                time.strftime("%Y-%m-%d %H:%M", time.localtime(p.last_used))
                if p.last_used
                else "never"
            )
            print(f"  {i}. {p.name} ({p.browser}/{p.os}) - last used: {last_used}")
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
        from tokenade.core.browser.dashboard import (
            generate_html_report,
            generate_json_report,
        )

        browser = args.browser
        print(f"\n[SEARCH] Running stealth tests ({browser})...")
        suite = StealthTestSuite(browser=browser, headless=True)
        report = asyncio.run(suite.run_all(url=args.url))

        print(f"\n{'=' * 60}")
        print(f"  STEALTH SCORE: {report.overall_score:.0f}/100 ({report._grade()})")
        print(f"{'=' * 60}")
        print(
            f"  {report.passed} passed, {report.failed} failed, {report.warned} warned"
        )
        print()

        for r in report.results:
            icon = {"pass": "[OK]", "fail": "[ERROR]", "warn": "[WARN]", "skip": "o"}[
                r.verdict.value
            ]
            print(f"  {icon} {r.name} ({r.score:.0f})")

        # Save reports
        html_path = args.output or str(
            Path.home() / ".tokenade" / "stealth_report.html"
        )
        generate_html_report(report, html_path)
        json_path = html_path.replace(".html", ".json")
        generate_json_report(report, json_path)
        print(f"\n  [FILE] HTML report: {html_path}")
        print(f"  [FILE] JSON report: {json_path}")
        print(f"{'=' * 60}\n")

    elif args.stealth_action == "report":
        import json
        from pathlib import Path

        print(f"\n[STATS] Stealth Report")
        manager = StealthManager()
        config = manager.get_config_dict()
        enabled = [
            k for k, v in config.items() if v is True and k.startswith("enable_")
        ]
        print(f"   Enabled patches: {len(enabled)}")
        for patch in enabled:
            print(f"     [OK] {patch.replace('enable_', '')}")
        print(f"\n   WebGL vendor: {config['webgl_vendor']}")
        print(f"   WebGL renderer: {config['webgl_renderer']}")
        print(f"   Screen: {config['screen_width']}x{config['screen_height']}")
        output_path = args.output or str(
            Path.home() / ".tokenade" / "stealth_report.json"
        )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(config, f, indent=2)
        print(f"   Report saved: {output_path}")

    elif args.stealth_action == "deps":
        checker = DependencyChecker()
        report = checker.get_report("chromium")
        print(f"\n[PKG] System Dependencies ({report['system']})")
        print(f"   Package manager: {report['package_manager'] or 'not found'}")
        print(f"   Installed: {report['installed']}/{report['total']}")
        if report["missing_packages"]:
            print(f"   Missing ({len(report['missing_packages'])}):")
            for pkg in report["missing_packages"]:
                print(f"     [ERROR] {pkg}")
        else:
            print(f"   [OK] All dependencies installed")

    elif args.stealth_action == "deps-install":
        print(f"\n[PKG] Installing missing dependencies...")
        checker = DependencyChecker()
        results = checker.install_playwright_deps()
        installed = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        print(f"   Installed: {installed}, Failed: {failed}")
        for r in results:
            if r.success:
                print(f"   [OK] {r.name}")
            else:
                print(f"   [ERROR] {r.name}: {r.message}")

    elif args.stealth_action == "battle":
        from tokenade.core.browser.battle import BattleTestSuite, DETECTION_SITES

        browser = args.browser
        sites = args.site if args.site else list(DETECTION_SITES.keys())
        timeout_ms = args.timeout * 1000

        print(f"\n  Running battle tests ({browser})...")
        print(f"   Sites: {len(sites)}")
        for s in sites:
            cfg = DETECTION_SITES.get(s, {})
            print(f"     - {cfg.get('name', s)}")
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
            print(f"\n  [FILE] JSON report: {args.output}")

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
        print(f"\n[PKG] System Dependencies ({report['system']})")
        print(f"   Package manager: {report['package_manager'] or 'not found'}")
        print(f"   Browser: {browser}")
        print(f"   Installed: {report['installed']}/{report['total']}")
        if report["missing_packages"]:
            print(f"   Missing packages:")
            for pkg in report["missing_packages"]:
                print(f"     [ERROR] {pkg}")
            print(f"\n   Install: tokenade deps install")
        else:
            print(f"   [OK] All dependencies installed")

    elif args.deps_action == "install":
        browser = getattr(args, "browser", "chromium")
        playwright_only = getattr(args, "playwright", False)

        if playwright_only:
            print(f"\n[PKG] Installing Playwright dependencies...")
            results = checker.install_playwright_deps()
        else:
            print(f"\n[PKG] Installing {browser} dependencies...")
            results = checker.install_missing(browser)

        installed = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        print(f"   Installed: {installed}, Failed: {failed}")
        for r in results:
            if r.success:
                print(f"   [OK] {r.name}")
            else:
                print(f"   [ERROR] {r.name}: {r.message}")

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

    print(f"\n[...] Starting Tokenade API server...")
    print(f"   Host: {config.host}")
    print(f"   Port: {config.port}")
    print(f"   Auth: {'API key required' if config.api_key else 'no authentication'}")
    print(f"   Sessions: {config.sessions_dir}")
    print()

    server = TokenadeAPIServer(config)

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n\n[STOP] Server stopped")
    except Exception as e:
        print(f"\n[ERROR] Server error: {e}")


def cmd_recommend(args):
    """Recommend site/plugin/browser for a session, URL, or cookie domains.

    Reads a .tokenade file (--session), a URL (--url), or a domain list
    (--domains), then prints the recommended site_name, handler plugin, and
    automation browser with one line of reasoning per choice.
    """
    import json as _json
    from pathlib import Path
    from tokenade.core.recommend import recommend, RecommendationConfig

    if not any((args.session, args.url, args.domains)):
        print(
            "error: pass at least one of --session / --url / --domains", file=sys.stderr
        )
        sys.exit(2)

    session = None
    if args.session:
        sess_path = Path(args.session).expanduser()
        if not sess_path.is_file():
            print(f"error: session file not found: {args.session}", file=sys.stderr)
            sys.exit(2)
        try:
            with open(sess_path, encoding="utf-8") as f:
                session = _json.load(f)
        except (OSError, _json.JSONDecodeError) as e:
            print(f"error: failed to load session: {e}", file=sys.stderr)
            sys.exit(2)

    cfg = None
    if args.browser:
        cfg = RecommendationConfig(automation_browser_override=args.browser)

    rec = recommend(
        session=session,
        url=args.url,
        domains=args.domains,
        config=cfg,
    )

    if args.json:
        print(_json.dumps(rec.as_dict(), indent=2, default=str))
        return

    print()
    print(f"  site:     {rec.site or '(none)'}")
    print(f"  plugin:   {rec.plugin or '(none)'}")
    print(f"  browser:  {rec.browser}")
    print(f"  confidence: {rec.confidence:.2f}")
    print()
    print("  reasons:")
    for r in rec.reasons:
        print(f"    - {r}")
    print()


logger = logging.getLogger("tokenade")
logger.addHandler(logging.NullHandler())


def setup_logging(verbose: bool = False):
    """Configure logging level and structured output."""
    from tokenade.core.logging.structured import LogManager

    level = "DEBUG" if verbose else "WARNING"
    json_output = getattr(setup_logging, "_json_output", False)
    LogManager.setup(level=level, json_output=json_output)


def _build_parser():
    """Build and return the CLI argument parser (extracted for testability)."""
    from tokenade import __version__

    parser = argparse.ArgumentParser(
        description="Tokenade - Browser session portability tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Quick Start:
  1. Export:   tokenade export --browser-name firefox --plugin discord-handler -o discord.tokenade
  2. Check:    tokenade health -s discord.tokenade
  3. Load:     tokenade load --file discord.tokenade --visible

Commands:
  export        Extract cookies from browser to .tokenade file
  run           Run an executable installed plugin
  load          Load .tokenade session into a browser
  encrypt       Encrypt a .tokenade file
  decrypt       Decrypt a .tokenade file
  rekey         Change encryption password
  health        Check session health
  plugin        Manage Site Handler plugins
        """,
    )

    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )
    parser.add_argument(
        "--json", dest="json_output", action="store_true", help="Output in JSON format"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    def _hide_subparser(name):
        subparsers._choices_actions = [
            action for action in subparsers._choices_actions if action.dest != name
        ]

    # Setup
    subparsers.add_parser("setup", help="Setup accounts")

    # Config
    config_parser = subparsers.add_parser("config", help="Manage configuration")
    config_parser.add_argument(
        "config_command", choices=["show", "set", "get", "path"], help="Config action"
    )
    config_parser.add_argument("key", nargs="?", help="Config key")
    config_parser.add_argument("value", nargs="?", help="Config value")

    # Generalized plugin execution
    run_parser = subparsers.add_parser("run", help="Run an executable installed plugin")
    run_parser.add_argument("--request", required=True, help="Nested request.json file")

    # Gateway control plane for multi-session routing.
    gateway_parser = subparsers.add_parser(
        "gateway", help="Run session gateway control plane"
    )
    gateway_parser.add_argument(
        "--request", required=True, help="Nested gateway request.json file"
    )

    # Extract
    extract_parser = subparsers.add_parser("extract", help="Extract tokens")
    extract_parser.add_argument(
        "--visible", action="store_true", help="Show browser window"
    )

    inspect_parser = subparsers.add_parser(
        "inspect", help="Inspect Session policy and capabilities safely"
    )
    inspect_parser.add_argument(
        "-s", "--session", required=True, help="Session file path"
    )
    inspect_parser.add_argument(
        "--decrypt-password", help="Password for an encrypted Session"
    )
    inspect_parser.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )

    # Transfer
    transfer_parser = subparsers.add_parser("transfer", help="Transfer session")
    transfer_parser.add_argument(
        "-s", "--session", required=True, help="Session file path"
    )
    transfer_parser.add_argument("-", "--fingerprint", help="Target fingerprint name")
    transfer_parser.add_argument(
        "-p", "--profile-dir", default="browser_data/transfer", help="Profile directory"
    )
    transfer_parser.add_argument(
        "--visible", action="store_true", help="Show browser window"
    )
    transfer_parser.add_argument(
        "--stealth-level",
        choices=["basic", "advanced", "maximum"],
        default="maximum",
        help="Stealth injection level",
    )
    transfer_parser.add_argument(
        "--validate-stealth",
        action="store_true",
        help="Validate stealth injection after launch",
    )

    # Test
    test_parser = subparsers.add_parser("test", help="Test portability")
    test_parser.add_argument("-s", "--session", required=True, help="Session file path")
    test_parser.add_argument(
        "--source-fp", default="default", help="Source fingerprint"
    )
    test_parser.add_argument(
        "--target-fp", default="default", help="Target fingerprint"
    )
    test_parser.add_argument(
        "--variations", action="store_true", help="Test fingerprint variations"
    )
    test_parser.add_argument("--test-api", action="store_true", help="Test API calls")
    test_parser.add_argument(
        "--stealth-level",
        choices=["basic", "advanced", "maximum"],
        default="maximum",
        help="Stealth injection level",
    )
    test_parser.add_argument(
        "--validate-stealth", action="store_true", help="Validate stealth injection"
    )
    test_parser.add_argument("-o", "--output", help="Output report path")

    # Fingerprint
    fp_parser = subparsers.add_parser("fingerprint", help="Manage fingerprints")
    fp_parser.add_argument(
        "action", choices=["list", "collect", "show", "delete"], help="Action"
    )
    fp_parser.add_argument("-n", "--name", help="Fingerprint name")
    fp_parser.add_argument("-p", "--profile-dir", help="Browser profile directory")

    # Validate
    validate_parser = subparsers.add_parser("validate", help="Validate sessions")
    validate_parser.add_argument(
        "-d", "--sessions-dir", default="sessions", help="Sessions directory"
    )

    # Export
    export_parser = subparsers.add_parser(
        "export", help="Export session from existing browser"
    )
    export_parser.add_argument(
        "--browser-name",
        help="Browser name (from profile discovery, e.g. chrome, firefox, vivaldi)",
    )
    export_parser.add_argument("--browser-path", help="Custom path to browser profile")
    export_parser.add_argument("--profile", help="Profile name within browser")
    export_parser.add_argument(
        "--site-config", help="Path to JSON site config file for filtering"
    )
    export_parser.add_argument(
        "--domains",
        help="Comma-separated domains to filter (e.g. 'google.com,accounts.google.com')",
    )
    export_parser.add_argument(
        "--cdp-port",
        type=int,
        help="Extract via CDP from running browser (bypasses SQLite decryption)",
    )
    export_parser.add_argument(
        "--cdp-launch",
        action="store_true",
        help="With --cdp-port: back up donor Cookies/Local State, quit "
        "residual browser processes, and relaunch a disposable snapshot "
        "with remote debugging when the port is not already listening "
        "(reads live values, defeats app-bound encryption; the live "
        "profile is never launched against)",
    )
    export_parser.add_argument("--file-path", help="Export from cookies file")
    export_parser.add_argument(
        "--format",
        choices=["netscape", "json", "curl"],
        default="netscape",
        help="File format",
    )
    export_parser.add_argument(
        "--collect-fingerprint",
        action="store_true",
        help="Collect source browser fingerprint",
    )
    export_parser.add_argument(
        "--output", "-o", help="Output file path (any extension)"
    )
    export_parser.add_argument(
        "--list-profiles", action="store_true", help="List available profiles"
    )
    export_parser.add_argument(
        "--decrypt", action="store_true", help="Decrypt cookies (auto-detected)"
    )
    export_parser.add_argument(
        "--extract-local-storage",
        action="store_true",
        help="Also extract localStorage data",
    )
    export_parser.add_argument(
        "--local-storage-origin", help="Origin to extract localStorage from"
    )
    export_parser.add_argument(
        "--full",
        action="store_true",
        help="Extract cookies + localStorage + sessionStorage (v3.0 format)",
    )
    export_parser.add_argument(
        "--no-storage",
        action="store_true",
        help="Extract only cookies (backward compat)",
    )
    export_parser.add_argument(
        "--encrypt-password",
        help="Encrypt .tokenade file with this password at export time",
    )
    export_parser.add_argument(
        "--plugin", help="Force specific site handler plugin (e.g., generic-handler)"
    )
    export_parser.add_argument(
        "--no-plugin", action="store_true", help="Skip plugin, use default extraction"
    )
    export_parser.add_argument(
        "--list-handlers",
        action="store_true",
        help="List available site handler plugins",
    )
    export_parser.add_argument(
        "--stamp-network",
        action="store_true",
        help="Opt in to approximate source network metadata capture",
    )
    export_parser.add_argument(
        "--include-source-ip",
        action="store_true",
        help="Store raw source IP with --stamp-network",
    )
    export_parser.add_argument(
        "--proxy-plugin",
        help="Record intended proxy provider plugin metadata without routing export traffic",
    )

    # Convert cookie file → .tokenade
    convert_parser = subparsers.add_parser(
        "convert",
        help="Convert cookie/storage file to .tokenade (JSON, Netscape, Playwright, HAR, …)",
    )
    convert_parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Input cookie file path",
    )
    convert_parser.add_argument(
        "--output",
        "-o",
        help="Output .tokenade path (default: ~/.tokenade/sessions/<stem>.tokenade)",
    )
    convert_parser.add_argument(
        "--format",
        choices=[
            "auto",
            "json",
            "netscape",
            "curl",
            "playwright",
            "puppeteer",
            "cookie-editor",
            "editthiscookie",
            "cypress",
            "selenium",
            "header",
            "set-cookie",
            "har",
            "csv",
        ],
        default="auto",
        help="Input format (default: auto-detect)",
    )
    convert_parser.add_argument(
        "--domain",
        help="Default cookie domain (header / set-cookie imports)",
    )
    convert_parser.add_argument(
        "--encrypt",
        action="store_true",
        help="Encrypt output with at-rest settings",
    )
    convert_parser.add_argument(
        "--encrypt-password",
        help="Encrypt output with this password",
    )

    # Load
    load_parser = subparsers.add_parser("load", help="Load session file into browser")
    load_parser.add_argument("--file", "-", required=True, help="Path to session file")
    load_parser.add_argument(
        "--site-config", help="Path to JSON site config file for validation"
    )
    load_parser.add_argument("--fingerprint", help="Target fingerprint name")
    load_parser.add_argument(
        "--stealth-level",
        choices=["basic", "advanced", "maximum"],
        default="maximum",
        help="Stealth level",
    )
    load_parser.add_argument(
        "--validate", action="store_true", help="Validate session after injection"
    )
    load_parser.add_argument(
        "--runtime", action="store_true", help="Load into RuntimeEngine"
    )
    load_parser.add_argument(
        "--test-api", action="store_true", help="Test API after loading"
    )
    load_parser.add_argument(
        "--visible", action="store_true", help="Show browser window"
    )
    load_parser.add_argument("--profile-dir", help="Browser profile directory")
    load_parser.add_argument(
        "--no-local-storage",
        action="store_true",
        help="Skip localStorage injection if present",
    )
    load_parser.add_argument(
        "--acknowledge-exclusive-move",
        action="store_true",
        help="Confirm source retirement for an exclusive move",
    )
    load_parser.add_argument(
        "--claim-single-use",
        action="store_true",
        help="Consume a locally single-use Session",
    )
    load_parser.add_argument(
        "--no-auto-solve",
        action="store_true",
        help="Disable automatic challenge solving during navigation",
    )
    load_parser.add_argument(
        "--capture-session",
        action="store_true",
        help="Capture and save solved challenge sessions to .tokenade",
    )
    load_parser.add_argument(
        "--capture-dir",
        help="Directory to save captured solved sessions",
    )

    # Inject Profile
    inject_parser = subparsers.add_parser(
        "inject-profile", help="Inject cookies directly into browser profile"
    )
    inject_parser.add_argument(
        "--session", "-s", required=True, help="Path to session file"
    )
    inject_parser.add_argument(
        "--profile", "-p", required=True, help="Browser profile path"
    )
    inject_parser.add_argument(
        "--browser",
        "-b",
        choices=["chrome", "brave", "edge", "firefox", "opera", "vivaldi"],
        default="chrome",
        help="Browser name",
    )
    inject_parser.add_argument(
        "--no-backup", action="store_true", help="Skip backup creation"
    )
    inject_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be injected without making changes",
    )

    # Encrypt
    encrypt_parser = subparsers.add_parser("encrypt", help="Encrypt session file")
    encrypt_parser.add_argument("--input", "-i", required=True, help="Input file path")
    encrypt_parser.add_argument("--output", "-o", help="Output file path")
    encrypt_parser.add_argument("--password", "-p", help="Encryption password")
    encrypt_parser.add_argument("--key-file", "-k", help="Password file")

    # Decrypt
    decrypt_parser = subparsers.add_parser("decrypt", help="Decrypt session file")
    decrypt_parser.add_argument(
        "--input", "-i", required=True, help="Encrypted file path"
    )
    decrypt_parser.add_argument("--output", "-o", help="Output file path")
    decrypt_parser.add_argument("--password", "-p", help="Decryption password")
    decrypt_parser.add_argument("--key-file", "-k", help="Password file")

    # Rekey
    rekey_parser = subparsers.add_parser("rekey", help="Change encryption password")
    rekey_parser.add_argument(
        "--input", "-i", required=True, help="Encrypted file path"
    )
    rekey_parser.add_argument("--output", "-o", help="Output file path")
    rekey_parser.add_argument("--old-password", help="Old password")
    rekey_parser.add_argument("--new-password", help="New password")
    rekey_parser.add_argument("--old-key-file", help="Old password file")
    rekey_parser.add_argument("--new-key-file", help="New password file")

    # Batch Export
    batch_export_parser = subparsers.add_parser(
        "batch-export", help="Batch export multiple sites"
    )
    batch_export_parser.add_argument(
        "--site-config", "-s", required=True, help="Site config JSON file"
    )
    batch_export_parser.add_argument(
        "--browser",
        "-b",
        choices=["chrome", "firefox", "edge", "brave"],
        default="firefox",
        help="Browser name",
    )
    batch_export_parser.add_argument(
        "--browser-path", help="Custom browser profile path"
    )
    batch_export_parser.add_argument("--profile", "-p", help="Profile name")
    batch_export_parser.add_argument("--output", "-o", help="Output directory")
    batch_export_parser.add_argument(
        "--extract-local-storage", action="store_true", help="Extract localStorage"
    )

    # Batch Load
    batch_load_parser = subparsers.add_parser(
        "batch-load", help="Batch load multiple sessions"
    )
    batch_load_parser.add_argument(
        "--sessions-dir", "-d", required=True, help="Sessions directory"
    )
    batch_load_parser.add_argument(
        "--target-browser",
        "-t",
        choices=["chrome", "firefox", "edge", "brave"],
        default="chrome",
        help="Target browser",
    )
    batch_load_parser.add_argument(
        "--site-config", "-s", help="Site config JSON file for validation"
    )
    batch_load_parser.add_argument("--profile-dir", help="Target profile directory")
    batch_load_parser.add_argument(
        "--validate", action="store_true", help="Validate sessions"
    )
    batch_load_parser.add_argument(
        "--visible", action="store_true", help="Show browser window"
    )

    # Health Check
    health_parser = subparsers.add_parser("health", help="Check session health")
    health_parser.add_argument("--session", "-s", help="Single session file to check")
    health_parser.add_argument(
        "--sessions-dir", "-d", help="Directory of sessions to check"
    )

    # Health Report
    health_report_parser = subparsers.add_parser(
        "health-report", help="Batch health report for CI/CD"
    )
    health_report_parser.add_argument(
        "--session", "-s", help="Single session file to check"
    )
    health_report_parser.add_argument(
        "--sessions-dir", "-d", help="Directory of sessions to check"
    )
    health_report_parser.add_argument(
        "--json", dest="json_output", action="store_true", help="Output as JSON"
    )
    health_report_parser.add_argument(
        "--min-health",
        type=float,
        default=0.5,
        help="Minimum health score (default: 0.5)",
    )
    health_report_parser.add_argument(
        "--max-expired",
        type=int,
        default=0,
        help="Max allowed expired cookies (default: 0)",
    )
    health_report_parser.add_argument("--webhook", help="Send report to webhook URL")

    # Refresh
    refresh_parser = subparsers.add_parser(
        "refresh", help="Refresh session from source browser"
    )
    refresh_parser.add_argument(
        "--session", "-s", required=True, help="Session file to refresh"
    )
    refresh_parser.add_argument(
        "--source-browser",
        "-b",
        choices=["chrome", "firefox", "edge", "brave"],
        required=True,
        help="Source browser name",
    )
    refresh_parser.add_argument(
        "--source-browser-path", help="Custom source browser profile path"
    )
    refresh_parser.add_argument("--source-profile", help="Source profile name")
    refresh_parser.add_argument(
        "--site-config", help="Site config JSON file for filtering"
    )

    def add_legacy_proxy_arguments(parser, *, hidden=False):
        help_text = argparse.SUPPRESS if hidden else None
        parser.add_argument(
            "--session",
            "-s",
            help=help_text or "Path to .tokenade session file (single mode)",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help=help_text or "Serve all sessions (multi-site mode)",
        )
        parser.add_argument(
            "--sessions-dir",
            "-d",
            help=help_text or "Directory of .tokenade files (for --all)",
        )
        parser.add_argument(
            "--decrypt-password",
            help=help_text or "Decrypt .tokenade file with this password",
        )
        parser.add_argument(
            "--mode",
            choices=["cdp", "gui", "forward"],
            default="gui",
            help=help_text or "Proxy mode",
        )
        parser.add_argument(
            "--port",
            "-p",
            type=int,
            default=9222,
            help=help_text or "Port to listen on (default: 9222)",
        )
        parser.add_argument(
            "--host",
            default="127.0.0.1",
            help=help_text or "Host to bind to (default: 127.0.0.1)",
        )
        parser.add_argument(
            "--legacy",
            action="store_true",
            help=help_text or "Use legacy service-worker proxy (default: CDP)",
        )
        parser.add_argument(
            "--visible",
            action="store_true",
            help=help_text or "Show browser window (CDP mode only)",
        )
        parser.add_argument(
            "--fingerprint",
            action="store_true",
            help=help_text or "Enable TLS fingerprint matching via curl-cffi",
        )
        parser.add_argument("--impersonate", help=help_text or "Browser to impersonate")
        parser.add_argument(
            "--no-open-browser",
            action="store_true",
            help=help_text or "Don't open browser automatically",
        )
        parser.add_argument(
            "--no-gui",
            action="store_true",
            help=help_text or "Disable GUI mode (legacy proxy only)",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=30,
            help=help_text or "Request timeout in seconds (default: 30)",
        )
        parser.add_argument(
            "--auto-refresh",
            action="store_true",
            help=help_text or "Auto-refresh session from source browser",
        )
        parser.add_argument(
            "--source-browser", help=help_text or "Source browser for auto-refresh"
        )
        parser.add_argument(
            "--source-profile", help=help_text or "Source profile for auto-refresh"
        )
        parser.add_argument(
            "--auto-navigate",
            action="store_true",
            help=help_text or "Auto-navigate to site URL when proxy starts",
        )
        parser.add_argument(
            "--target-url", help=help_text or "Override default navigation URL"
        )
        parser.add_argument(
            "--rotate",
            action="store_true",
            help=help_text or "Enable session rotation across multiple sessions",
        )
        parser.add_argument(
            "--rotate-strategy",
            choices=["health-weighted", "round-robin", "random", "least-recently-used"],
            default="health-weighted",
            help=help_text or "Rotation strategy (default: health-weighted)",
        )
        parser.add_argument(
            "--rotate-interval",
            type=int,
            default=300,
            help=help_text or "Rotation interval in seconds (default: 300)",
        )

    # Proxy - upstream proxy provider tooling. Legacy local/CDP behavior is hidden under `proxy legacy`.
    proxy_parser = subparsers.add_parser(
        "proxy", help="Resolve upstream proxy provider requests"
    )
    add_legacy_proxy_arguments(proxy_parser, hidden=True)
    proxy_sub = proxy_parser.add_subparsers(dest="proxy_action")
    proxy_resolve = proxy_sub.add_parser(
        "resolve", help="Resolve upstream proxy provider from request.json"
    )
    proxy_resolve.add_argument(
        "--request", required=True, help="Nested request.json with roles.proxy_provider"
    )
    proxy_resolve.add_argument(
        "--show-secrets",
        action="store_true",
        help="Include proxy credentials in output",
    )
    proxy_resolve.add_argument(
        "--pretty", action="store_true", help="Pretty-print JSON output"
    )

    proxy_legacy = proxy_sub.add_parser("legacy", help=argparse.SUPPRESS)
    add_legacy_proxy_arguments(proxy_legacy)

    # Sessions (subcommand group)
    sessions_parser = subparsers.add_parser("sessions", help="Manage multiple sessions")
    sessions_sub = sessions_parser.add_subparsers(
        dest="sessions_command", help="Session management commands"
    )

    # sessions list
    sessions_list_parser = sessions_sub.add_parser("list", help="List all sessions")
    sessions_list_parser.add_argument(
        "--dir", "-d", default=".", help="Directory to search"
    )
    sessions_list_parser.add_argument(
        "--pattern", "-p", default="*.tokenade", help="File pattern"
    )
    sessions_list_parser.add_argument(
        "--recursive", "-r", action="store_true", help="Search subdirectories"
    )
    sessions_list_parser.add_argument("--site", "-s", help="Filter by site name")
    sessions_list_parser.add_argument(
        "--browser", "-b", help="Filter by source browser"
    )

    # sessions merge
    sessions_merge_parser = sessions_sub.add_parser(
        "merge", help="Merge multiple sessions"
    )
    sessions_merge_parser.add_argument(
        "files", nargs="+", help="Session files to merge"
    )
    sessions_merge_parser.add_argument(
        "--output", "-o", required=True, help="Output file path"
    )
    sessions_merge_parser.add_argument(
        "--site-name", help="Site name for merged session"
    )

    # sessions rotate
    sessions_rotate_parser = sessions_sub.add_parser(
        "rotate", help="Select next session (rotation)"
    )
    sessions_rotate_parser.add_argument(
        "files", nargs="+", help="Session files to rotate through"
    )
    sessions_rotate_parser.add_argument(
        "--strategy",
        choices=["round-robin", "random"],
        default="round-robin",
        help="Rotation strategy",
    )
    sessions_rotate_parser.add_argument(
        "--state-file", help="State file for round-robin"
    )

    # sessions stats
    sessions_stats_parser = sessions_sub.add_parser(
        "stats", help="Show aggregate session statistics"
    )
    sessions_stats_parser.add_argument(
        "files", nargs="+", help="Session files to analyze"
    )

    # Share
    share_parser = subparsers.add_parser(
        "share", help="Create shareable session link or QR code"
    )
    share_parser.add_argument(
        "--session", "-s", required=True, help="Session file to share"
    )
    share_parser.add_argument(
        "--output", "-o", help="Output file path (HTML or QR image)"
    )
    share_parser.add_argument(
        "--format",
        choices=["url", "html", "qr"],
        default="url",
        help="Output format: url (default), html, qr",
    )
    share_parser.add_argument(
        "--expiry", type=int, default=24, help="Link expiry in hours (default: 24)"
    )
    share_parser.add_argument(
        "--max-uses", type=int, default=0, help="Max uses (0 = unlimited)"
    )
    share_parser.add_argument("--password", "-p", help="Password protect the link")
    share_parser.add_argument("--email-to", help="Comma-separated email recipients")
    share_parser.add_argument("--smtp-host", help="SMTP server host")
    share_parser.add_argument(
        "--smtp-port", type=int, default=587, help="SMTP server port"
    )
    share_parser.add_argument("--smtp-user", help="SMTP username")
    share_parser.add_argument("--smtp-password", help="SMTP password")
    share_parser.add_argument("--webhook-url", help="Webhook URL to notify")

    # Unshare
    unshare_parser = subparsers.add_parser("unshare", help="Revoke a shared session")
    unshare_parser.add_argument("session_id", help="Session ID to revoke")
    unshare_parser.add_argument(
        "--list", action="store_true", help="List all active shares"
    )

    # Share URL (password + full URL + optional Supabase short-id)
    def _share_url_remote_flags(p):
        p.add_argument(
            "--supabase-url", help="Private Supabase URL (overrides public default)"
        )
        p.add_argument("--supabase-key", help="Private Supabase anon/publishable key")
        p.add_argument(
            "--no-remote",
            action="store_true",
            help="Embedded full URL only (no remote)",
        )

    share_url_parser = subparsers.add_parser(
        "share-url",
        help="Share sessions via password-protected URL (full URL + optional Supabase short-id)",
    )
    share_url_subparsers = share_url_parser.add_subparsers(dest="share_action")

    share_url_create = share_url_subparsers.add_parser(
        "create", help="Create password-protected share link"
    )
    share_url_create.add_argument("session", help="Session file to share")
    share_url_create.add_argument(
        "--password", required=True, help="Password for encryption (required)"
    )
    share_url_create.add_argument(
        "--expiry", type=int, default=24, help="Expiry in hours (default: 24)"
    )
    share_url_create.add_argument(
        "--max-uses", type=int, default=0, help="Max uses (0=server default on public)"
    )
    share_url_create.add_argument(
        "--backend",
        choices=["local", "bitly", "tinyurl"],
        default="local",
        help="URL shortener backend",
    )
    share_url_create.add_argument(
        "--api-key", help="API key for URL shortener (for bitly)"
    )
    share_url_create.add_argument("--domain", help="Custom domain for shortener")
    share_url_create.add_argument(
        "--password-min-length", type=int, default=8, help="Minimum password length"
    )
    share_url_create.add_argument(
        "--include-request", action="store_true", help="Include request.json in session"
    )
    share_url_create.add_argument("--json", action="store_true", help="JSON output")
    _share_url_remote_flags(share_url_create)

    share_url_retrieve = share_url_subparsers.add_parser(
        "retrieve", help="Retrieve session with password"
    )
    share_url_retrieve.add_argument(
        "share_url", help="Share URL, short id, or full tokenade:// URL"
    )
    share_url_retrieve.add_argument(
        "--password", required=True, help="Password for decryption (required)"
    )
    share_url_retrieve.add_argument("-o", "--output", help="Output file path")
    share_url_retrieve.add_argument("--json", action="store_true", help="JSON output")
    _share_url_remote_flags(share_url_retrieve)

    share_url_revoke = share_url_subparsers.add_parser(
        "revoke", help="Revoke a share link"
    )
    share_url_revoke.add_argument("share_id", help="Share ID to revoke")
    share_url_revoke.add_argument("--json", action="store_true", help="JSON output")
    _share_url_remote_flags(share_url_revoke)

    share_url_list = share_url_subparsers.add_parser(
        "list", help="List local share links"
    )
    share_url_list.add_argument("--json", action="store_true", help="JSON output")

    share_url_cleanup = share_url_subparsers.add_parser(
        "cleanup", help="Cleanup expired local share links"
    )
    share_url_cleanup.add_argument("--json", action="store_true", help="JSON output")

    share_url_status = share_url_subparsers.add_parser(
        "status", help="Show remote share (Supabase) config"
    )
    share_url_status.add_argument("--json", action="store_true", help="JSON output")
    _share_url_remote_flags(share_url_status)

    # Import shared session
    import_parser = subparsers.add_parser(
        "import", help="Import a shared session from URL"
    )
    import_parser.add_argument("url", help="tokenade://share/ URL")
    import_parser.add_argument("--password", "-p", help="Decryption password")
    import_parser.add_argument("--output", "-o", help="Output file path")

    # Validate Rules
    validate_rules_parser = subparsers.add_parser(
        "validate-rules", help="Validate session with custom rules"
    )
    validate_rules_parser.add_argument(
        "--session", "-s", required=True, help="Session file to validate"
    )
    validate_rules_parser.add_argument(
        "--rules", "-r", required=True, help="Validation rules JSON file"
    )
    validate_rules_parser.add_argument("--url", "-u", help="Target site URL")
    validate_rules_parser.add_argument(
        "--update-baselines", action="store_true", help="Update screenshot baselines"
    )

    # Diff
    diff_parser = subparsers.add_parser("diff", help="Compare two session files")
    diff_parser.add_argument("session_a", help="First .tokenade file")
    diff_parser.add_argument("session_b", help="Second .tokenade file")
    diff_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed differences"
    )

    # Plugin
    plugin_parser = subparsers.add_parser("plugin", help="Manage plugins")
    plugin_sub = plugin_parser.add_subparsers(
        dest="plugin_command", help="Plugin commands"
    )

    plugin_list_parser = plugin_sub.add_parser("list", help="List installed plugins")
    plugin_list_parser.add_argument(
        "--available", action="store_true", help="Show available plugins from registry"
    )

    plugin_install_parser = plugin_sub.add_parser("install", help="Install a plugin")
    plugin_install_parser.add_argument("name", nargs="?", default="", help="Plugin name to install")
    plugin_install_parser.add_argument(
        "--git",
        help="Git repository URL or GitHub shorthand (e.g. user/repo or https://github.com/user/repo.git)",
    )
    plugin_install_parser.add_argument(
        "--branch",
        help="Git branch or tag to install from",
    )
    plugin_install_parser.add_argument(
        "--subdir",
        help="Subdirectory within the git repository containing the plugin(s)",
    )
    plugin_install_parser.add_argument(
        "--registry",
        help="Registry to install from (required if plugin exists in multiple)",
    )

    plugin_uninstall_parser = plugin_sub.add_parser(
        "uninstall", help="Uninstall a plugin"
    )
    plugin_uninstall_parser.add_argument("name", help="Plugin name to uninstall")

    plugin_info_parser = plugin_sub.add_parser("info", help="Show plugin details")
    plugin_info_parser.add_argument("name", help="Plugin name")
    plugin_info_parser.add_argument(
        "--json", action="store_true", help="Machine-readable JSON output"
    )

    plugin_enable_parser = plugin_sub.add_parser(
        "enable", help="Enable a disabled plugin"
    )
    plugin_enable_parser.add_argument("name", help="Plugin name to enable")

    plugin_disable_parser = plugin_sub.add_parser(
        "disable", help="Disable a plugin without uninstalling"
    )
    plugin_disable_parser.add_argument("name", help="Plugin name to disable")

    plugin_update_parser = plugin_sub.add_parser(
        "update", help="Update plugins from registry"
    )
    plugin_update_parser.add_argument(
        "name", nargs="?", default=None, help="Plugin name to update (all if omitted)"
    )
    plugin_update_parser.add_argument(
        "--force", action="store_true", help="Force re-download even if up-to-date"
    )
    plugin_update_parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be updated"
    )

    # plugin registry (multi-registry management)
    plugin_registry_parser = plugin_sub.add_parser(
        "registry", help="Manage plugin registries"
    )
    plugin_reg_sub = plugin_registry_parser.add_subparsers(
        dest="registry_action", help="Registry actions"
    )
    reg_add = plugin_reg_sub.add_parser(
        "add", help="Add a registry (local path or remote URL)"
    )
    reg_add.add_argument("name", help="Registry name")
    reg_add.add_argument("source", help="Local directory path or remote URL")
    reg_remove = plugin_reg_sub.add_parser("remove", help="Remove a registry")
    reg_remove.add_argument("name", help="Registry name")
    plugin_reg_sub.add_parser("list", help="List configured registries")

    plugin_sync_parser = plugin_sub.add_parser(
        "sync", help="Install all available plugins from registry"
    )
    plugin_sync_parser.add_argument(
        "--force", action="store_true", help="Reinstall even if already installed"
    )

    plugin_reload_parser = plugin_sub.add_parser("reload", help="Reload a plugin")
    plugin_reload_parser.add_argument("name", help="Plugin name to reload")

    # plugin search
    plugin_search_parser = plugin_sub.add_parser(
        "search", help="Search plugins in marketplace"
    )
    plugin_search_parser.add_argument(
        "query", nargs="?", default="", help="Search query"
    )
    plugin_search_parser.add_argument(
        "--type", dest="plugin_type", help="Filter by plugin type"
    )
    plugin_search_parser.add_argument("--category", help="Filter by category")
    plugin_search_parser.add_argument("--tags", help="Comma-separated tags to filter")
    plugin_search_parser.add_argument(
        "--sort",
        choices=["rating", "downloads", "name", "recent", "trending"],
        default="name",
        help="Sort order (default: name - registry has no fake download/rating metrics)",
    )

    # plugin categories
    plugin_sub.add_parser("categories", help="List plugin categories")

    # plugin popular
    plugin_popular_parser = plugin_sub.add_parser(
        "popular", help="Show most popular plugins"
    )
    plugin_popular_parser.add_argument(
        "--limit", "-n", type=int, default=10, help="Number of plugins to show"
    )

    # plugin recent
    plugin_recent_parser = plugin_sub.add_parser("recent", help="Show newest plugins")
    plugin_recent_parser.add_argument(
        "--limit", "-n", type=int, default=10, help="Number of plugins to show"
    )

    # plugin rate
    plugin_rate_parser = plugin_sub.add_parser("rate", help="Rate a plugin (1-5 stars)")
    plugin_rate_parser.add_argument("name", help="Plugin name")
    plugin_rate_parser.add_argument("rating", type=float, help="Rating (1.0-5.0)")
    plugin_rate_parser.add_argument("--review", help="Written review")

    # plugin ratings
    plugin_ratings_parser = plugin_sub.add_parser(
        "ratings", help="View global ratings from GitHub"
    )
    plugin_ratings_parser.add_argument(
        "name", nargs="?", help="Plugin name (all if omitted)"
    )

    # plugin verify
    plugin_verify_parser = plugin_sub.add_parser(
        "verify", help="Verify plugin integrity via checksums"
    )
    plugin_verify_parser.add_argument(
        "name", nargs="?", help="Plugin name (all if omitted)"
    )

    # plugin outdated
    plugin_sub.add_parser("outdated", help="Show plugins with available updates")

    # plugin browse
    plugin_browse_parser = plugin_sub.add_parser(
        "browse", help="Generate static HTML marketplace page"
    )
    plugin_browse_parser.add_argument("--output", "-o", help="Output HTML file path")

    # plugin test
    plugin_test_parser = plugin_sub.add_parser(
        "test", help="Run tests on installed plugins"
    )
    plugin_test_parser.add_argument(
        "name", nargs="?", help="Plugin name (all if omitted)"
    )
    plugin_test_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed test output"
    )

    # plugin deps
    plugin_deps_parser = plugin_sub.add_parser(
        "deps", help="Show plugin dependency tree"
    )
    plugin_deps_parser.add_argument("name", help="Plugin name")
    plugin_deps_parser.add_argument(
        "--json", action="store_true", help="Machine-readable JSON output"
    )

    # plugin check-deps
    plugin_checkdeps_parser = plugin_sub.add_parser(
        "check-deps", help="Check for missing/circular dependencies"
    )
    plugin_checkdeps_parser.add_argument(
        "name", nargs="?", help="Plugin name (optional - checks all if omitted)"
    )
    plugin_checkdeps_parser.add_argument(
        "--json", action="store_true", help="Machine-readable JSON output"
    )

    # plugin configure
    plugin_configure_parser = plugin_sub.add_parser(
        "configure", help="Configure plugin settings"
    )
    plugin_configure_parser.add_argument("name", help="Plugin name")
    plugin_configure_parser.add_argument(
        "--set",
        nargs="*",
        metavar="KEY=VALUE",
        help="Set config values (e.g. --set timeout=60 retries=3)",
    )
    plugin_configure_parser.add_argument(
        "--show", action="store_true", help="Show current config"
    )
    plugin_configure_parser.add_argument(
        "--reset", action="store_true", help="Reset to defaults"
    )
    plugin_configure_parser.add_argument(
        "--validate", action="store_true", help="Validate config against schema"
    )

    # Sync
    sync_parser = subparsers.add_parser(
        "sync", help="Package browser Sessions and synchronize peer repositories"
    )
    sync_sub = sync_parser.add_subparsers(dest="sync_command", help="Sync commands")

    sync_add_parser = sync_sub.add_parser("add", help="Add a sync target")
    sync_add_parser.add_argument(
        "--name", "-n", required=True, help="Target name (e.g., gmail)"
    )
    sync_add_parser.add_argument(
        "--domains", "-d", required=True, help="Comma-separated domains"
    )
    sync_add_parser.add_argument(
        "--browser", "-b", default="firefox", help="Browser (default: firefox)"
    )
    sync_add_parser.add_argument("--profile", "-p", help="Browser profile name")
    sync_add_parser.add_argument(
        "--output-dir", "-o", help="Output directory (default: ~/.tokenade/synced)"
    )

    sync_remove_parser = sync_sub.add_parser("remove", help="Remove a sync target")
    sync_remove_parser.add_argument("--name", "-n", required=True, help="Target name")

    sync_sub.add_parser("list", help="List sync targets")
    sync_sub.add_parser("once", help="Run one-time sync")

    sync_start_parser = sync_sub.add_parser("start", help="Start sync daemon")
    sync_start_parser.add_argument(
        "--interval", "-i", type=int, default=60, help="Check interval in seconds"
    )

    peer_parser = sync_sub.add_parser("peer", help="Manage persisted sync peers")
    peer_sub = peer_parser.add_subparsers(dest="peer_action")
    peer_add = peer_sub.add_parser("add", help="Add or update a peer")
    peer_add.add_argument("name")
    peer_add.add_argument("--transport", choices=["local", "ssh"], required=True)
    peer_add.add_argument("--path", required=True)
    peer_add.add_argument("--host")
    peer_add.add_argument("--user")
    peer_add.add_argument("--port", type=int, default=22)
    peer_add.add_argument("--identity")
    peer_add.add_argument("--known-hosts")
    peer_add.add_argument("--allow-plaintext", action="store_true")
    peer_remove = peer_sub.add_parser("remove", help="Remove peer")
    peer_remove.add_argument("name")
    peer_sub.add_parser("list", help="List peers")

    sync_plan = sync_sub.add_parser("plan", help="Preview hash-based sync plan")
    sync_plan.add_argument("peer")
    sync_plan.add_argument(
        "--direction", choices=["two-way", "push", "pull"], default="two-way"
    )
    sync_plan.add_argument("--json", action="store_true")
    sync_run = sync_sub.add_parser("run", help="Execute a peer sync plan")
    sync_run.add_argument("peer")
    sync_run.add_argument(
        "--direction", choices=["two-way", "push", "pull"], default="two-way"
    )
    sync_run.add_argument("--dry-run", action="store_true")
    sync_run.add_argument("--allow-plaintext", action="store_true")
    sync_run.add_argument("--json", action="store_true")
    sync_status = sync_sub.add_parser("status", help="Show peer sync status")
    sync_status.add_argument("peer")
    sync_status.add_argument("--json", action="store_true")

    # Monitor
    monitor_parser = subparsers.add_parser(
        "monitor", help="Monitor session health in real-time"
    )
    monitor_sub = monitor_parser.add_subparsers(
        dest="monitor_command", help="Monitor commands"
    )

    monitor_status_parser = monitor_sub.add_parser(
        "status", help="Show monitoring status"
    )
    monitor_status_parser.add_argument(
        "--sessions-dir", "-d", help="Directory of sessions to check"
    )
    monitor_status_parser.add_argument(
        "--session", "-s", help="Single session file to check"
    )

    monitor_start_parser = monitor_sub.add_parser(
        "start", help="Start background monitoring"
    )
    monitor_start_parser.add_argument(
        "--sessions-dir", "-d", help="Directory of sessions to monitor"
    )
    monitor_start_parser.add_argument(
        "--session", "-s", help="Single session file to monitor"
    )
    monitor_start_parser.add_argument(
        "--interval", "-i", type=int, default=60, help="Check interval in seconds"
    )
    monitor_start_parser.add_argument(
        "--auto-refresh", action="store_true", help="Auto-refresh expiring sessions"
    )

    monitor_stop_parser = monitor_sub.add_parser(
        "stop", help="Stop background monitoring"
    )

    monitor_history_parser = monitor_sub.add_parser(
        "history", help="Show monitor event history"
    )
    monitor_history_parser.add_argument(
        "--sessions-dir", "-d", help="Sessions directory"
    )
    monitor_history_parser.add_argument(
        "--limit", "-l", type=int, default=50, help="Max events to show"
    )

    monitor_predict_parser = monitor_sub.add_parser(
        "predict", help="Predict session expiry"
    )
    monitor_predict_parser.add_argument(
        "--sessions-dir", "-d", help="Sessions directory"
    )
    monitor_predict_parser.add_argument("--session", "-s", help="Single session file")

    # OAuth Automation CLI command
    oauth_auto_parser = subparsers.add_parser(
        "oauth", help="Automate third-party login flows using donor provider sessions"
    )
    oauth_sub = oauth_auto_parser.add_subparsers(dest="oauth_action", help="OAuth actions")
    oauth_run = oauth_sub.add_parser("automate", help="Automate login on target URL using donor session")
    oauth_run.add_argument("--provider", choices=["google", "github"], default="google", help="OAuth provider")
    oauth_run.add_argument("--donor-session", "-d", required=True, help="Path to donor .tokenade session file")
    oauth_run.add_argument("--target-url", "-t", required=True, help="Target third-party URL to authenticate on")
    oauth_run.add_argument("--output", "-o", help="Path to save output target session .tokenade file")

    # Extension Bundle CLI command
    ext_bundle_parser = subparsers.add_parser(
        "extension", help="Manage and bundle Tokenade browser extension"
    )
    ext_sub = ext_bundle_parser.add_subparsers(dest="extension_action", help="Extension actions")
    ext_bld = ext_sub.add_parser("bundle", help="Build store packages for Chrome Web Store (.zip) and Firefox AMO (.xpi)")
    ext_bld.add_argument("--source-dir", help="Path to extension source directory")
    ext_bld.add_argument("--out-dir", default="dist/extension", help="Output directory for zip/xpi bundles")
    ext_bld.add_argument("--target", choices=["all", "chrome", "firefox"], default="all", help="Target store")

    # Shell Completion
    completion_parser = subparsers.add_parser(
        "completion", help="Generate shell completion scripts"
    )
    completion_parser.add_argument(
        "shell", choices=["bash", "zsh", "fish"], help="Shell type"
    )

    # OAuth Refresh
    refresh_oauth_parser = subparsers.add_parser(
        "refresh-oauth", help="Refresh OAuth tokens using stored refresh token"
    )
    refresh_oauth_parser.add_argument(
        "--session", "-s", required=True, help="Session file to refresh"
    )

    # OAuth Config
    oauth_config_parser = subparsers.add_parser(
        "oauth-config", help="Configure OAuth settings for a session"
    )
    oauth_config_parser.add_argument(
        "--session", "-s", required=True, help="Session file to configure"
    )
    oauth_config_parser.add_argument("--client-id", help="OAuth client ID")
    oauth_config_parser.add_argument("--client-secret", help="OAuth client secret")
    oauth_config_parser.add_argument(
        "--token-endpoint", help="OAuth token endpoint URL"
    )
    oauth_config_parser.add_argument("--scopes", help="Comma-separated OAuth scopes")
    oauth_config_parser.add_argument(
        "--show", action="store_true", help="Show current OAuth config"
    )

    # Batch Refresh
    batch_refresh_parser = subparsers.add_parser(
        "batch-refresh", help="Refresh multiple sessions with rate limiting"
    )
    batch_refresh_parser.add_argument(
        "--sessions-dir", "-d", default="sessions", help="Sessions directory"
    )
    batch_refresh_parser.add_argument(
        "--max-workers", "-w", type=int, default=3, help="Max parallel workers"
    )
    batch_refresh_parser.add_argument(
        "--delay", type=float, default=1.0, help="Delay between refreshes (seconds)"
    )
    batch_refresh_parser.add_argument(
        "--source-browser",
        "-b",
        default="firefox",
        help="Source browser for cookie refresh",
    )
    batch_refresh_parser.add_argument(
        "--source-profile", "-p", help="Source profile name"
    )
    batch_refresh_parser.add_argument(
        "--force", action="store_true", help="Force refresh even if not expired"
    )
    batch_refresh_parser.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation prompt"
    )

    # CI/CD
    cicd_parser = subparsers.add_parser("cicd", help="Generate CI/CD workflow files")
    cicd_parser.add_argument(
        "--generate-all", action="store_true", help="Generate all workflow files"
    )
    cicd_parser.add_argument(
        "--workflow-type",
        choices=["github", "gitlab", "cron"],
        default="github",
        help="Workflow type",
    )
    cicd_parser.add_argument(
        "--sessions-dir", default="sessions", help="Sessions directory"
    )
    cicd_parser.add_argument(
        "--interval-hours", type=int, default=6, help="Refresh interval in hours"
    )
    cicd_parser.add_argument(
        "--source-browser", default="firefox", help="Source browser for cookie refresh"
    )
    cicd_parser.add_argument("--output", "-o", help="Output file path")
    cicd_parser.add_argument(
        "--output-dir",
        default=".tokenade/ci",
        help="Output directory for --generate-all",
    )

    # CI Runner
    ci_parser = subparsers.add_parser("ci", help="Session CI runner")
    ci_sub = ci_parser.add_subparsers(dest="ci_action")

    ci_run = ci_sub.add_parser("run", help="Run CI pipeline from tokenade.yml")
    ci_run.add_argument("--config", default="tokenade.yml", help="Config file path")
    ci_run.add_argument(
        "--format", choices=["text", "json", "junit"], help="Override output format"
    )

    ci_init = ci_sub.add_parser("init", help="Create a starter tokenade.yml")
    ci_init.add_argument("--config", default="tokenade.yml", help="Config file path")

    ci_validate = ci_sub.add_parser("validate", help="Validate tokenade.yml schema")
    ci_validate.add_argument(
        "--config", default="tokenade.yml", help="Config file path"
    )

    ci_lint = ci_sub.add_parser("lint", help="Lint tokenade.yml for common issues")
    ci_lint.add_argument("--config", default="tokenade.yml", help="Config file path")

    # Fleet Management
    fleet_parser = subparsers.add_parser(
        "fleet", help="Fleet status across containers/pods"
    )
    fleet_sub = fleet_parser.add_subparsers(dest="fleet_action")

    fleet_status = fleet_sub.add_parser(
        "status", help="Show all sessions across containers"
    )
    fleet_status.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format"
    )

    fleet_health = fleet_sub.add_parser(
        "health", help="Run health checks across the fleet"
    )
    fleet_health.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format"
    )

    fleet_sub.add_parser("refresh", help="Trigger refresh in all running containers")

    fleet_logs = fleet_sub.add_parser("logs", help="Get logs from a container")
    fleet_logs.add_argument("container", nargs="?", help="Container name")
    fleet_logs.add_argument(
        "--lines", "-n", type=int, default=50, help="Number of log lines"
    )

    # Autopsy (Forensics)
    autopsy_parser = subparsers.add_parser("autopsy", help="Analyze why a session died")
    autopsy_parser.add_argument(
        "--session", "-s", required=True, help="Session file to analyze"
    )
    autopsy_parser.add_argument(
        "--compare", "-c", help="Compare with another session file"
    )
    autopsy_parser.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format"
    )

    # TUI
    tui_parser = subparsers.add_parser("tui", help="Launch interactive terminal UI")
    tui_parser.add_argument(
        "tui_mode",
        nargs="?",
        default="full",
        choices=["full", "marketplace", "sessions"],
        help="TUI mode",
    )

    # Validate Session
    validate_session_parser = subparsers.add_parser(
        "validate-session", help="Validate session files for CI/CD"
    )
    validate_session_parser.add_argument(
        "--session", "-s", help="Single session file to validate"
    )
    validate_session_parser.add_argument(
        "--sessions-dir", "-d", help="Directory of sessions to validate"
    )
    validate_session_parser.add_argument(
        "--min-health", type=float, default=0.5, help="Minimum health score (0.0-1.0)"
    )
    validate_session_parser.add_argument(
        "--max-expired", type=int, default=0, help="Max allowed expired cookies"
    )
    validate_session_parser.add_argument(
        "--require-oauth", action="store_true", help="Require OAuth config"
    )
    validate_session_parser.add_argument(
        "--max-age-hours", type=float, help="Max session age in hours"
    )
    validate_session_parser.add_argument(
        "--json", dest="json_output", action="store_true", help="Output as JSON"
    )

    # Encrypted Refresh
    encrypted_refresh_parser = subparsers.add_parser(
        "encrypted-refresh", help="Refresh encrypted session files"
    )
    encrypted_refresh_parser.add_argument(
        "--session", "-s", help="Single session file to refresh"
    )
    encrypted_refresh_parser.add_argument(
        "--sessions-dir", "-d", help="Directory of sessions to refresh"
    )
    encrypted_refresh_parser.add_argument(
        "--password", "-p", help="Decryption password"
    )
    encrypted_refresh_parser.add_argument("--key-file", "-k", help="Key file path")
    encrypted_refresh_parser.add_argument(
        "--source-browser",
        "-b",
        default="firefox",
        help="Source browser for cookie refresh",
    )
    encrypted_refresh_parser.add_argument(
        "--force", action="store_true", help="Force refresh even if not expired"
    )

    # CloakBrowser
    cloak_parser = subparsers.add_parser("cloak", help="CloakBrowser management")
    cloak_sub = cloak_parser.add_subparsers(dest="cloak_action")

    cloak_info = cloak_sub.add_parser(
        "info", help="Show CloakBrowser status and binary info"
    )
    cloak_info.add_argument(
        "--json", dest="json_output", action="store_true", help="Output as JSON"
    )
    cloak_sub.add_parser("install", help="Download/update CloakBrowser binary")

    cloak_serve = cloak_sub.add_parser("serve", help="Start CDP server (cloakserve)")
    cloak_serve.add_argument(
        "--port", "-p", type=int, default=9222, help="Port to listen on"
    )
    cloak_serve.add_argument("--proxy", help="Upstream proxy URL")
    cloak_serve.add_argument(
        "--headless", action="store_true", default=True, help="Run headless"
    )
    cloak_serve.add_argument("--visible", action="store_true", help="Run headed")
    cloak_serve.add_argument("--idle-timeout", type=int, help="Idle timeout in seconds")

    # Launch Browser
    launch_parser = subparsers.add_parser(
        "launch", help="Launch a browser with CloakBrowser as the default backend"
    )
    launch_parser.add_argument(
        "--browser",
        "-b",
        default="cloak",
        help="Browser to launch (cloak, firefox, brave, edge, vivaldi, chrome)",
    )
    launch_parser.add_argument(
        "--session", "-s", help="Session file to inject cookies from"
    )
    launch_parser.add_argument("--url", "-u", help="URL to navigate to after injection")
    launch_parser.add_argument(
        "--port", "-p", type=int, default=9222, help="CDP debugging port"
    )
    launch_parser.add_argument(
        "--profile",
        help="Discovered browser profile name to launch (copied by default)",
    )
    launch_parser.add_argument(
        "--profile-dir", help="Exact profile directory to launch"
    )
    launch_parser.add_argument(
        "--visible",
        action="store_true",
        help="Show browser window (default unless --headless)",
    )
    launch_parser.add_argument(
        "--headless", action="store_true", help="Run headless (no window)"
    )
    launch_parser.add_argument(
        "--extra-args", help="Extra browser args (comma-separated)"
    )
    launch_parser.add_argument("--browser-path", help="Path to browser executable")
    launch_parser.add_argument(
        "--proxy", help="Upstream proxy URL (e.g. socks5://user:pass@host:port)"
    )
    launch_parser.add_argument(
        "--proxy-file", help="Proxy list file for rotation (one proxy per line)"
    )
    launch_parser.add_argument(
        "--proxy-rotate", action="store_true", help="Enable proxy rotation"
    )
    launch_parser.add_argument(
        "--proxy-strategy",
        choices=["round-robin", "random", "health-weighted", "sticky"],
        default="health-weighted",
        help="Rotation strategy (default: health-weighted)",
    )
    launch_parser.add_argument(
        "--humanize",
        action="store_true",
        help="Human-like mouse/keyboard/scroll (CloakBrowser)",
    )
    launch_parser.add_argument(
        "--geoip",
        action="store_true",
        help="Auto-detect timezone/locale from proxy IP (CloakBrowser)",
    )
    launch_parser.add_argument(
        "--no-cloak",
        action="store_true",
        help="Force Playwright + JS patches (skip CloakBrowser)",
    )
    launch_parser.add_argument(
        "--copy-profile",
        action="store_true",
        help="Copy the selected profile before launch (default for discovered profiles)",
    )
    launch_parser.add_argument(
        "--use-original-profile",
        action="store_true",
        help="Launch directly against the original discovered profile",
    )
    launch_parser.add_argument(
        "--refresh-profiles",
        action="store_true",
        help="Refresh browser profile cache before resolving --profile",
    )
    launch_parser.add_argument(
        "--decrypt-password", help="Decrypt .tokenade file with this password"
    )
    launch_parser.add_argument(
        "--plugin",
        help="Force site handler plugin for launch (e.g. generic-handler); auto-discovers when omitted",
    )
    launch_parser.add_argument(
        "--no-plugin",
        action="store_true",
        help="Skip plugin handlers; use default launch",
    )
    launch_parser.add_argument(
        "--acknowledge-exclusive-move",
        action="store_true",
        help="Confirm the source linked-device profile is closed and will not be used concurrently",
    )
    launch_parser.add_argument(
        "--claim-single-use",
        action="store_true",
        help="Consume a locally single-use Session",
    )

    # Refresh Browser (cookie-based session refresh)
    refresh_browser_parser = subparsers.add_parser(
        "refresh-browser", help="Refresh session through a browser-backed flow"
    )
    refresh_browser_parser.add_argument(
        "--session", "-s", required=True, help="Session file to refresh"
    )
    refresh_browser_parser.add_argument(
        "--browser",
        "-b",
        default="cloak",
        help="Browser to use (cloak, firefox, brave, edge, vivaldi, chrome)",
    )
    refresh_browser_parser.add_argument(
        "--url", "-u", help="Target URL (auto-detected from cookies if not specified)"
    )
    refresh_browser_parser.add_argument(
        "--port", "-p", type=int, default=9222, help="CDP debugging port"
    )
    refresh_browser_parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run headless (default; always closes after login check)",
    )
    refresh_browser_parser.add_argument(
        "--visible",
        action="store_true",
        help="Show browser window during refresh (still closes when done)",
    )
    refresh_browser_parser.add_argument(
        "--wait",
        "-w",
        type=int,
        default=8,
        help="Seconds to wait for session refresh (default: 8)",
    )
    refresh_browser_parser.add_argument(
        "--output", "-o", help="Output file (default: overwrite original)"
    )
    refresh_browser_parser.add_argument(
        "--plugin", help="Plugin to use for refresh (e.g., oauth2)"
    )
    refresh_browser_parser.add_argument(
        "--no-plugin",
        action="store_true",
        help="Skip plugin refresh; use browser-based refresh only",
    )
    refresh_browser_parser.add_argument(
        "--plugin-arg",
        action="append",
        default=[],
        nargs=2,
        metavar=("KEY", "VALUE"),
        help="Plugin credential (repeatable): --plugin-arg client_id XXX",
    )
    refresh_browser_parser.add_argument(
        "--proxy", help="Upstream proxy URL (e.g. socks5://user:pass@host:port)"
    )
    refresh_browser_parser.add_argument(
        "--proxy-file", help="Proxy list file for rotation (one proxy per line)"
    )
    refresh_browser_parser.add_argument(
        "--proxy-rotate", action="store_true", help="Enable proxy rotation"
    )
    refresh_browser_parser.add_argument(
        "--proxy-strategy",
        choices=["round-robin", "random", "health-weighted", "sticky"],
        default="health-weighted",
        help="Rotation strategy (default: health-weighted)",
    )

    # Multi-Account Orchestration
    accounts_parser = subparsers.add_parser(
        "accounts", help="Multi-account orchestration (list/status/refresh)"
    )
    accounts_subparsers = accounts_parser.add_subparsers(dest="accounts_action")

    # accounts list
    accounts_list = accounts_subparsers.add_parser("list", help="List all sessions")
    accounts_list.add_argument(
        "--sessions-dir", "-d", default=".", help="Directory to scan (default: current)"
    )
    accounts_list.add_argument("--site", "-s", help="Filter by site name")
    accounts_list.add_argument("--browser", "-b", help="Filter by browser")

    # accounts status
    accounts_status = accounts_subparsers.add_parser(
        "status", help="Show health/status of all sessions"
    )
    accounts_status.add_argument(
        "--sessions-dir", "-d", default=".", help="Directory to scan (default: current)"
    )
    accounts_status.add_argument("--site", "-s", help="Filter by site name")

    # accounts refresh
    accounts_refresh = accounts_subparsers.add_parser(
        "refresh", help="Refresh all/specific sessions"
    )
    accounts_refresh.add_argument(
        "--sessions-dir", "-d", default=".", help="Directory to scan (default: current)"
    )
    accounts_refresh.add_argument("--site", "-s", help="Filter by site name")
    accounts_refresh.add_argument(
        "--browser",
        "-b",
        default="cloak",
        help="Browser to use for refresh (cloak, firefox, brave, edge, vivaldi, chrome)",
    )
    accounts_refresh.add_argument(
        "--files", nargs="*", help="Specific session files to refresh"
    )
    accounts_refresh.add_argument(
        "--port", "-p", type=int, default=9222, help="Starting CDP port"
    )
    accounts_refresh.add_argument(
        "--visible", action="store_true", help="Show browser window"
    )
    accounts_refresh.add_argument(
        "--headless", action="store_true", default=True, help="Run headless (default)"
    )
    accounts_refresh.add_argument(
        "--wait", "-w", type=int, default=8, help="Seconds to wait per session"
    )
    accounts_refresh.add_argument(
        "--yes", "-y", action="store_true", help="Skip confirmation"
    )
    accounts_refresh.add_argument(
        "--plugin", help="Plugin to use for refresh (e.g., oauth2)"
    )
    accounts_refresh.add_argument(
        "--no-plugin",
        action="store_true",
        help="Skip plugin refresh; use browser-based refresh only",
    )
    accounts_refresh.add_argument(
        "--plugin-arg",
        action="append",
        default=[],
        nargs=2,
        metavar=("KEY", "VALUE"),
        help="Plugin credential (repeatable): --plugin-arg client_id XXX",
    )
    accounts_refresh.add_argument(
        "--proxy", help="Upstream proxy URL (e.g. socks5://user:pass@host:port)"
    )
    accounts_refresh.add_argument(
        "--proxy-file", help="Proxy list file for rotation (one proxy per line)"
    )
    accounts_refresh.add_argument(
        "--proxy-rotate", action="store_true", help="Enable proxy rotation"
    )
    accounts_refresh.add_argument(
        "--proxy-strategy",
        choices=["round-robin", "random", "health-weighted", "sticky"],
        default="health-weighted",
        help="Rotation strategy (default: health-weighted)",
    )

    # -- Mobile Import --------------------------------------------
    mobile_import_parser = subparsers.add_parser(
        "mobile-import", help=argparse.SUPPRESS
    )
    mobile_import_parser.add_argument(
        "--auto", action="store_true", help="Auto-detect device and browser"
    )
    mobile_import_parser.add_argument(
        "--list-devices", action="store_true", help="List connected mobile devices"
    )
    mobile_import_parser.add_argument("--device", "-d", help="Device serial number")
    mobile_import_parser.add_argument(
        "--browser",
        "-b",
        default="auto",
        help="Browser to extract from (chrome/firefox/samsung/brave/edge/safari, default: auto)",
    )
    mobile_import_parser.add_argument(
        "--domains", help="Comma-separated domains to filter"
    )
    mobile_import_parser.add_argument(
        "--output", "-o", help="Output .tokenade file path"
    )
    mobile_import_parser.add_argument("--site-name", help="Site name override")
    mobile_import_parser.add_argument(
        "--ios", action="store_true", help="Target iOS device (macOS only)"
    )

    # -- Daemon --------------------------------------------------
    daemon_parser = subparsers.add_parser(
        "daemon", help="Auto-refresh daemon (background session refresh)"
    )
    daemon_subparsers = daemon_parser.add_subparsers(dest="daemon_action")

    # daemon start
    daemon_start = daemon_subparsers.add_parser(
        "start", help="Start daemon in background"
    )
    daemon_start.add_argument(
        "--interval", type=float, help="Check interval in minutes (default: 30)"
    )
    daemon_start.add_argument("--webhook", help="Webhook URL for notifications")

    # daemon stop
    daemon_subparsers.add_parser("stop", help="Stop the daemon")

    # daemon status
    daemon_subparsers.add_parser("status", help="Show daemon status")

    # daemon run-once
    daemon_subparsers.add_parser(
        "run-once", help="Run single refresh cycle (foreground)"
    )

    # daemon add
    daemon_add = daemon_subparsers.add_parser("add", help="Add session to watch list")
    daemon_add.add_argument("session", help="Session file to watch")
    daemon_add.add_argument(
        "--browser", "-b", default="cloak", help="Browser for refresh (cloak default)"
    )
    daemon_add.add_argument(
        "--refresh-before",
        type=float,
        default=2.0,
        help="Refresh this many hours before expiry (default: 2.0)",
    )
    daemon_add.add_argument("--url", "-u", help="Target URL (auto-detected if not set)")
    daemon_add.add_argument(
        "--site-name", help="Site name (auto-detected from filename)"
    )

    # daemon remove
    daemon_remove = daemon_subparsers.add_parser(
        "remove", help="Remove session from watch list"
    )
    daemon_remove.add_argument("session", help="Session file to remove")

    # daemon list
    daemon_subparsers.add_parser("list", help="List all watched sessions")

    # daemon logs
    daemon_logs = daemon_subparsers.add_parser("logs", help="View daemon logs")
    daemon_logs.add_argument(
        "--lines", "-n", type=int, default=50, help="Number of lines to show"
    )
    daemon_logs.add_argument(
        "--follow", "-f", action="store_true", help="Follow log output (like tail -f)"
    )

    # -- Versions ------------------------------------------------
    versions_parser = subparsers.add_parser(
        "versions", help="Session versioning (list/create/delete)"
    )
    versions_subparsers = versions_parser.add_subparsers(dest="version_action")

    versions_list = versions_subparsers.add_parser(
        "list", help="List versions for a session"
    )
    versions_list.add_argument("session", help="Session file")

    versions_create = versions_subparsers.add_parser(
        "create", help="Create a new version"
    )
    versions_create.add_argument("session", help="Session file")
    versions_create.add_argument("--description", "-d", help="Version description")

    versions_delete = versions_subparsers.add_parser("delete", help="Delete a version")
    versions_delete.add_argument("session", help="Session file")
    versions_delete.add_argument("version", type=int, help="Version number to delete")

    # -- Rollback ------------------------------------------------
    rollback_parser = subparsers.add_parser(
        "rollback", help="Rollback session to a specific version"
    )
    rollback_parser.add_argument("session", help="Session file")
    rollback_parser.add_argument("version", type=int, help="Version number to restore")

    # -- Session Diff (version comparison) -----------------------
    session_diff_parser = subparsers.add_parser(
        "session-diff", help="Compare two session versions"
    )
    session_diff_parser.add_argument("session", help="Session file")
    session_diff_parser.add_argument("version_a", type=int, help="First version number")
    session_diff_parser.add_argument(
        "version_b", type=int, help="Second version number"
    )

    # -- Logs ----------------------------------------------------
    logs_parser = subparsers.add_parser("logs", help="View structured logs")
    logs_parser.add_argument(
        "--lines",
        "-n",
        type=int,
        default=50,
        help="Number of recent lines to show (default: 50)",
    )
    logs_parser.add_argument(
        "--follow", "-f", action="store_true", help="Follow log output (like tail -f)"
    )
    logs_parser.add_argument("--search", "-s", help="Search for text in logs")
    logs_parser.add_argument(
        "--json", dest="json_output", action="store_true", help="Output in JSON format"
    )
    logs_parser.add_argument(
        "--log-file",
        help="Path to specific log file (default: ~/.tokenade/logs/tokenade.log)",
    )
    logs_parser.add_argument(
        "--list-files", action="store_true", help="List all log files"
    )
    logs_parser.add_argument(
        "--cleanup", type=int, metavar="DAYS", help="Remove log files older than N days"
    )

    # -- Clone Profile ------------------------------------------
    clone_parser = subparsers.add_parser(
        "clone-profile", help="Clone a browser profile to a new directory"
    )
    clone_parser.add_argument(
        "source",
        nargs="?",
        help="Source profile directory (omit to use system default)",
    )
    clone_parser.add_argument(
        "--dest", "-d", required=True, help="Destination directory for the clone"
    )
    clone_parser.add_argument(
        "--browser",
        "-b",
        default="chrome",
        help="Browser name (chrome, firefox, brave, edge, vivaldi)",
    )
    clone_parser.add_argument(
        "--session", "-s", help="Session file to inject into the clone"
    )
    clone_parser.add_argument(
        "--profile", "-p", help="Profile name to clone (default: system default)"
    )
    clone_parser.add_argument(
        "--list-profiles", action="store_true", help="List available browser profiles"
    )

    # Container management
    container_parser = subparsers.add_parser("container", help=argparse.SUPPRESS)
    container_sub = container_parser.add_subparsers(dest="container_action")

    container_start = container_sub.add_parser(
        "start", help="Start proxy/API containers"
    )
    container_start.add_argument(
        "--sessions-dir", "-d", default=".", help="Directory with session files"
    )
    container_start.add_argument(
        "--proxy-port", type=int, default=9222, help="Starting proxy port"
    )
    container_start.add_argument(
        "--api-port", type=int, default=9224, help="API server port"
    )
    container_start.add_argument(
        "--no-api", action="store_true", help="Don't start API server"
    )
    container_start.add_argument(
        "--restart",
        default="unless-stopped",
        help="Restart policy (default: unless-stopped)",
    )

    container_stop = container_sub.add_parser("stop", help="Stop containers")
    container_stop.add_argument(
        "--name", help="Container name to stop (default: all tokenade)"
    )

    container_sub.add_parser("restart", help="Restart containers")
    container_sub.add_parser("status", help="Show container status")

    container_logs = container_sub.add_parser("logs", help="Tail container logs")
    container_logs.add_argument("name", help="Container name")
    container_logs.add_argument(
        "--tail", "-n", type=int, default=100, help="Number of lines to tail"
    )
    container_logs.add_argument(
        "--follow", "-f", action="store_true", help="Follow log output"
    )

    container_refresh = container_sub.add_parser(
        "refresh", help="Refresh sessions inside containers"
    )
    container_refresh.add_argument("name", help="Container name")
    container_refresh.add_argument(
        "--sessions-dir", default="/app/sessions", help="Sessions dir in container"
    )

    container_scale = container_sub.add_parser("scale", help="Scale proxy containers")
    container_scale.add_argument("replicas", type=int, help="Number of replicas")
    container_scale.add_argument(
        "--sessions-dir", "-d", default=".", help="Directory with session files"
    )

    container_sub.add_parser("cleanup", help="Stop and remove all tokenade containers")

    container_health = container_sub.add_parser("health", help="Check container health")
    container_health.add_argument(
        "--watch", action="store_true", help="Continuous health monitoring"
    )
    container_health.add_argument(
        "--interval", type=int, default=60, help="Check interval in seconds"
    )
    container_health.add_argument(
        "--max-restarts", type=int, default=3, help="Max restarts before giving up"
    )

    container_gen = container_sub.add_parser(
        "generate", help="Generate docker-compose override"
    )
    container_gen.add_argument(
        "--sessions-dir", "-d", default=".", help="Directory with session files"
    )
    container_gen.add_argument("--output", "-o", help="Output file (default: stdout)")
    container_gen.add_argument(
        "--base-port", type=int, default=9222, help="Starting port"
    )

    # Kubernetes management
    k8s_parser = subparsers.add_parser("k8s", help=argparse.SUPPRESS)
    k8s_sub = k8s_parser.add_subparsers(dest="k8s_action")

    k8s_deploy = k8s_sub.add_parser("deploy", help="Generate and apply K8s manifests")
    k8s_deploy.add_argument(
        "--namespace", "-n", default="default", help="Kubernetes namespace"
    )
    k8s_deploy.add_argument(
        "--replicas", "-r", type=int, default=1, help="Number of replicas"
    )
    k8s_deploy.add_argument(
        "--image", default="tokenade:latest", help="Container image"
    )
    k8s_deploy.add_argument("--port", type=int, default=9222, help="Proxy port")
    k8s_deploy.add_argument(
        "--dry-run", action="store_true", help="Only generate YAML, don't apply"
    )
    k8s_deploy.add_argument("--output", "-o", help="Output file for generated YAML")

    k8s_status = k8s_sub.add_parser("status", help="Show deployment status")
    k8s_status.add_argument(
        "--namespace", "-n", default="default", help="Kubernetes namespace"
    )

    k8s_scale = k8s_sub.add_parser("scale", help="Scale deployment")
    k8s_scale.add_argument("replicas", type=int, help="Number of replicas")
    k8s_scale.add_argument(
        "--namespace", "-n", default="default", help="Kubernetes namespace"
    )

    k8s_logs = k8s_sub.add_parser("logs", help="Tail pod logs")
    k8s_logs.add_argument(
        "--namespace", "-n", default="default", help="Kubernetes namespace"
    )
    k8s_logs.add_argument(
        "--tail", type=int, default=100, help="Number of lines to tail"
    )

    k8s_delete = k8s_sub.add_parser("delete", help="Delete deployment and service")
    k8s_delete.add_argument(
        "--namespace", "-n", default="default", help="Kubernetes namespace"
    )

    k8s_sub.add_parser("pods", help="List pods")

    profile_parser = subparsers.add_parser("profile", help="Manage browser profiles")
    profile_sub = profile_parser.add_subparsers(
        dest="profile_command", help="Profile commands"
    )

    profile_create = profile_sub.add_parser("create", help="Create a new profile")
    profile_create.add_argument("name", help="Profile name")
    profile_create.add_argument(
        "--browser", "-b", default="chromium", help="Browser type (default: chromium)"
    )
    profile_create.add_argument(
        "--os",
        dest="os_name",
        default="windows",
        choices=["windows", "macos", "linux"],
        help="Target OS",
    )
    profile_create.add_argument(
        "--proxy", help="Proxy URL (e.g., socks5://user:pass@host:port)"
    )
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

    profile_recent = profile_sub.add_parser(
        "recent", help="Show recently used profiles"
    )
    profile_recent.add_argument(
        "--limit", "-n", type=int, default=5, help="Number of profiles"
    )

    profile_sub.add_parser("stats", help="Show profile statistics")

    stealth_parser = subparsers.add_parser("stealth", help="Stealth Level diagnostics")
    stealth_sub = stealth_parser.add_subparsers(dest="stealth_action")

    stealth_test = stealth_sub.add_parser(
        "test", help="Test Stealth Level behavior against detection sites"
    )
    stealth_test.add_argument("--url", "-u", help="Custom test URL")
    stealth_test.add_argument(
        "--browser", "-b", choices=["chrome", "firefox"], default="chrome"
    )
    stealth_test.add_argument("--output", "-o", help="Output file for HTML report")

    stealth_report = stealth_sub.add_parser(
        "report", help="Generate Stealth Level report"
    )
    stealth_report.add_argument("--output", "-o", help="Output file for report")
    stealth_report.add_argument(
        "--browser", "-b", choices=["chrome", "firefox"], default="chrome"
    )

    stealth_battle = stealth_sub.add_parser(
        "battle", help="Run detection-site diagnostics"
    )
    stealth_battle.add_argument(
        "--browser", "-b", choices=["chromium", "firefox"], default="chromium"
    )
    stealth_battle.add_argument(
        "--site", "-s", action="append", help="Specific site(s) to test (default: all)"
    )
    stealth_battle.add_argument(
        "--timeout", "-t", type=int, default=30, help="Per-site timeout in seconds"
    )
    stealth_battle.add_argument("--output", "-o", help="Output file for JSON report")

    stealth_sub.add_parser("deps", help="Check browser automation system dependencies")
    stealth_sub.add_parser(
        "deps-install", help="Install missing browser automation dependencies"
    )

    deps_parser = subparsers.add_parser("deps", help="System dependency management")
    deps_sub = deps_parser.add_subparsers(dest="deps_action")

    deps_sub.add_parser("check", help="Check system dependencies")
    deps_install = deps_sub.add_parser("install", help="Install missing dependencies")
    deps_install.add_argument(
        "--browser", "-b", choices=["chrome", "firefox"], default="chrome"
    )
    deps_install.add_argument(
        "--playwright", action="store_true", help="Install Playwright dependencies"
    )

    serve_parser = subparsers.add_parser(
        "serve", help="Start API server for session management"
    )
    serve_parser.add_argument(
        "--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)"
    )
    serve_parser.add_argument(
        "--port", "-p", type=int, default=9224, help="Port to listen on (default: 9224)"
    )
    serve_parser.add_argument("--api-key", help="API key for authentication")
    serve_parser.add_argument("--sessions-dir", "-d", help="Sessions directory")
    serve_parser.add_argument("--cors", help="Allowed CORS origins (comma-separated)")

    # Vault
    vault_parser = subparsers.add_parser("vault", help="Encrypted session storage")
    vault_parser.add_argument("--vault-path", help="Vault path")
    vault_sub = vault_parser.add_subparsers(dest="vault_action")

    vault_store = vault_sub.add_parser("store", help="Store session in vault")
    vault_store.add_argument("name", help="Entry name")
    vault_store.add_argument("file", help="Session file to store")
    vault_store.add_argument("--json", action="store_true", help="JSON output")
    vault_store.add_argument(
        "--replace", action="store_true", help="Replace an existing entry"
    )

    vault_retrieve = vault_sub.add_parser("retrieve", help="Retrieve from vault")
    vault_retrieve.add_argument("name", help="Entry name")
    vault_retrieve.add_argument("--output", help="Output file path")
    vault_retrieve.add_argument("--json", action="store_true", help="JSON output")
    vault_retrieve.add_argument(
        "--overwrite", action="store_true", help="Overwrite output file"
    )

    vault_delete = vault_sub.add_parser("delete", help="Delete from vault")
    vault_delete.add_argument("name", help="Entry name")
    vault_delete.add_argument("--json", action="store_true", help="JSON output")

    vault_list = vault_sub.add_parser("list", help="List vault entries")
    vault_list.add_argument("--json", action="store_true", help="JSON output")

    vault_rotate = vault_sub.add_parser("rotate", help="Rotate encryption key")
    vault_rotate.add_argument("--json", action="store_true", help="JSON output")

    vault_backup = vault_sub.add_parser("backup", help="Backup vault")
    vault_backup.add_argument("--name", help="Backup name")
    vault_backup.add_argument("--json", action="store_true", help="JSON output")

    vault_restore = vault_sub.add_parser("restore", help="Restore vault from backup")
    vault_restore.add_argument("name", help="Backup name")
    vault_restore.add_argument("--json", action="store_true", help="JSON output")

    vault_verify = vault_sub.add_parser("verify", help="Verify every encrypted entry")
    vault_verify.add_argument("--json", action="store_true", help="JSON output")

    vault_migrate = vault_sub.add_parser(
        "migrate", help="Migrate the legacy on-disk Vault format"
    )
    vault_migrate.add_argument("--json", action="store_true", help="JSON output")

    # Dashboard
    dashboard_parser = subparsers.add_parser(
        "dashboard", help="Session monitoring web dashboard"
    )
    dashboard_sub = dashboard_parser.add_subparsers(dest="dashboard_action")

    dashboard_start = dashboard_sub.add_parser("start", help="Start dashboard server")
    dashboard_start.add_argument("--host", default="127.0.0.1", help="Bind host")
    dashboard_start.add_argument("--port", type=int, default=8080, help="Bind port")
    dashboard_start.add_argument("--title", help="Dashboard title")
    dashboard_start.add_argument(
        "--refresh", type=int, help="Refresh interval (seconds)"
    )

    dashboard_status = dashboard_sub.add_parser("status", help="Check dashboard status")
    dashboard_status.add_argument("--host", default="127.0.0.1", help="Dashboard host")
    dashboard_status.add_argument(
        "--port", type=int, default=8080, help="Dashboard port"
    )

    dashboard_sessions = dashboard_sub.add_parser(
        "sessions", help="List sessions via dashboard"
    )
    dashboard_sessions.add_argument(
        "--host", default="127.0.0.1", help="Dashboard host"
    )
    dashboard_sessions.add_argument(
        "--port", type=int, default=8080, help="Dashboard port"
    )
    dashboard_sessions.add_argument("--json", action="store_true", help="JSON output")

    # Sync Remote (cross-machine synchronization)
    sync_remote_parser = subparsers.add_parser(
        "sync-remote", help="Synchronize sessions across machines (SSH/rsync)"
    )
    sync_remote_sub = sync_remote_parser.add_subparsers(dest="sync_action")

    sync_remote_push = sync_remote_sub.add_parser(
        "push", help="Push sessions to remote"
    )
    sync_remote_push.add_argument("--remote-host", required=True, help="Remote host")
    sync_remote_push.add_argument(
        "--remote-port", type=int, default=22, help="Remote SSH port"
    )
    sync_remote_push.add_argument(
        "--remote-path", default="~/.tokenade/sessions", help="Remote path"
    )
    sync_remote_push.add_argument(
        "--local-path", default="~/.tokenade/sessions", help="Local path"
    )
    sync_remote_push.add_argument("--json", action="store_true", help="JSON output")

    sync_remote_pull = sync_remote_sub.add_parser(
        "pull", help="Pull sessions from remote"
    )
    sync_remote_pull.add_argument("--remote-host", required=True, help="Remote host")
    sync_remote_pull.add_argument(
        "--remote-port", type=int, default=22, help="Remote SSH port"
    )
    sync_remote_pull.add_argument(
        "--remote-path", default="~/.tokenade/sessions", help="Remote path"
    )
    sync_remote_pull.add_argument(
        "--local-path", default="~/.tokenade/sessions", help="Local path"
    )
    sync_remote_pull.add_argument("--json", action="store_true", help="JSON output")

    sync_remote_bidi = sync_remote_sub.add_parser(
        "bidirectional", help="Bidirectional sync"
    )
    sync_remote_bidi.add_argument("--remote-host", required=True, help="Remote host")
    sync_remote_bidi.add_argument(
        "--remote-port", type=int, default=22, help="Remote SSH port"
    )
    sync_remote_bidi.add_argument(
        "--remote-path", default="~/.tokenade/sessions", help="Remote path"
    )
    sync_remote_bidi.add_argument(
        "--local-path", default="~/.tokenade/sessions", help="Local path"
    )
    sync_remote_bidi.add_argument(
        "--conflict",
        choices=["newest", "oldest", "local", "remote"],
        default="newest",
        help="Conflict resolution",
    )
    sync_remote_bidi.add_argument("--json", action="store_true", help="JSON output")

    sync_remote_status = sync_remote_sub.add_parser("status", help="Show sync status")
    sync_remote_status.add_argument("--remote-host", required=True, help="Remote host")
    sync_remote_status.add_argument(
        "--remote-port", type=int, default=22, help="Remote SSH port"
    )
    sync_remote_status.add_argument(
        "--remote-path", default="~/.tokenade/sessions", help="Remote path"
    )
    sync_remote_status.add_argument(
        "--local-path", default="~/.tokenade/sessions", help="Local path"
    )
    sync_remote_status.add_argument("--json", action="store_true", help="JSON output")

    # Recommend site/plugin/browser for a session, URL, or cookie domains.
    recommend_parser = subparsers.add_parser(
        "recommend",
        help="Recommend site/plugin/browser for a session, URL, or domain list",
    )
    recommend_parser.add_argument(
        "--session",
        "-s",
        help="Path to a .tokenade session file",
    )
    recommend_parser.add_argument(
        "--url",
        "-u",
        help="Target URL to recommend a handler for",
    )
    recommend_parser.add_argument(
        "--domains",
        "-d",
        nargs="*",
        help="Cookie domains to match (space-separated)",
    )
    recommend_parser.add_argument(
        "--browser",
        help="Force a browser override (cloak / firefox / brave / chrome)",
    )
    recommend_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of human text",
    )

    for hidden_command in (
        "setup",
        "extract",
        "transfer",
        "inject-profile",
        "batch-export",
        "batch-load",
        "health-report",
        "refresh",
        "share",
        "unshare",
        "import",
        "validate-rules",
        "diff",
        "sync",
        "monitor",
        "container",
        "refresh-oauth",
        "oauth-config",
        "batch-refresh",
        "cicd",
        "ci",
        "fleet",
        "autopsy",
        "validate-session",
        "encrypted-refresh",
        "accounts",
        "mobile-import",
        "daemon",
        "versions",
        "rollback",
        "session-diff",
        "logs",
        "k8s",
        "stealth",
        "deps",
        "vault",
        "dashboard",
        "sync-remote",
    ):
        _hide_subparser(hidden_command)
    subparsers.metavar = (
        "{" + ",".join(action.dest for action in subparsers._choices_actions) + "}"
    )

    return parser


def cmd_oauth(args):
    """Handle OAuth automation commands."""
    if getattr(args, "oauth_action", None) != "automate":
        print("Usage: tokenade oauth automate --donor-session <file> --target-url <url>", file=sys.stderr)
        sys.exit(1)

    import json
    from pathlib import Path
    from tokenade.core.importer.session_packager import SessionPackager
    from tokenade.core.integration.oauth_handlers import GoogleOAuthAutomation, GitHubOAuthAutomation

    donor_path = Path(args.donor_session).resolve()
    if not donor_path.is_file():
        print(f"[ERROR] Donor session file not found: {donor_path}", file=sys.stderr)
        sys.exit(1)

    packager = SessionPackager()
    source_session = packager.load(str(donor_path))
    if not source_session:
        print(f"[ERROR] Failed to load donor session from {donor_path}", file=sys.stderr)
        sys.exit(1)

    provider = getattr(args, "provider", "google")
    print(f"\n[AUTH] Starting OAuth automation via provider: {provider}")
    print(f"   Target URL: {args.target_url}")
    print(f"   Donor: {donor_path.name} ({len(source_session.get('cookies', []))} cookies)")

    if provider == "google":
        handler = GoogleOAuthAutomation()
    else:
        handler = GitHubOAuthAutomation()

    result = handler.process(source_session, args.target_url, output_path=args.output)
    if result.success:
        out = args.output or f"{Path(args.target_url).name or 'target'}.tokenade"
        print(f"   [OK] Successfully authenticated and generated target session -> {out}")
    else:
        print(f"   [ERROR] OAuth automation failed: {result.error}", file=sys.stderr)
        sys.exit(1)


def cmd_extension(args):
    """Handle extension bundle commands."""
    if getattr(args, "extension_action", None) != "bundle":
        print("Usage: tokenade extension bundle [options]", file=sys.stderr)
        sys.exit(1)

    from pathlib import Path
    from tokenade.core.browser.extension_bundler import ExtensionBundler

    source_dir = Path(args.source_dir) if getattr(args, "source_dir", None) else None
    bundler = ExtensionBundler(source_dir=source_dir)
    valid, errors = bundler.validate_source()
    if not valid:
        print("[ERROR] Extension source validation failed:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = bundler.get_manifest_data()
    version = manifest.get("version", "1.0.0")

    print(f"\n[EXT] Bundling Tokenade browser extension v{version}...")
    target = getattr(args, "target", "all")

    if target in ("all", "chrome"):
        czip = out_dir / f"tokenade-extension-chrome-v{version}.zip"
        bundler.build_chrome_zip(czip)
        print(f"   [OK] Chrome Web Store bundle: {czip} ({czip.stat().st_size / 1024:.1f} KB)")

    if target in ("all", "firefox"):
        fxpi = out_dir / f"tokenade-extension-firefox-v{version}.xpi"
        bundler.build_firefox_xpi(fxpi)
        print(f"   [OK] Firefox AMO bundle: {fxpi} ({fxpi.stat().st_size / 1024:.1f} KB)")


def main():
    """Main CLI entry point."""
    if os.name == "nt":
        # Windows consoles default to a legacy codepage (e.g. cp1252/cp437)
        # that cannot encode the checkmarks, arrows, and box-drawing glyphs
        # the CLI prints. Prefer UTF-8 output instead of crashing.
        for stream_name in ("stdout", "stderr"):
            stream = getattr(sys, stream_name, None)
            reconfigure = getattr(stream, "reconfigure", None)
            if callable(reconfigure):
                try:
                    reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    setup_logging._json_output = getattr(args, "json_output", False)
    setup_logging(args.verbose)

    commands = {
        "setup": cmd_setup,
        "config": cmd_config,
        "run": cmd_run,
        "gateway": cmd_gateway,
        "inspect": cmd_inspect,
        "extract": cmd_extract,
        "transfer": cmd_transfer,
        "test": cmd_test,
        "fingerprint": cmd_fingerprint,
        "validate": cmd_validate,
        "export": cmd_export,
        "convert": cmd_convert,
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
        "share-url": cmd_share_url,
        "import": cmd_import,
        "sync": cmd_sync,
        "monitor": cmd_monitor,
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
        "recommend": cmd_recommend,
        "vault": cmd_vault,
        "dashboard": cmd_dashboard,
        "sync-remote": cmd_sync_remote,
        "oauth": cmd_oauth,
        "extension": cmd_extension,
    }

    try:
        commands[args.command](args)
    except KeyboardInterrupt:
        print("\n\n[WARN] Interrupted by user")
        sys.exit(130)
    except Exception as e:
        from tokenade.core.errors import TokenadeError

        logger.exception("Command failed")
        if isinstance(e, TokenadeError):
            print(f"\n[ERROR] {e}")
        else:
            print(f"\nUnexpected error: {e}")
            print("   Run with --verbose for full traceback")
            print("   Logs: ~/.tokenade/logs/")
        sys.exit(1)
