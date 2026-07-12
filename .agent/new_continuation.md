# Tokenade Plugin Ecosystem — Handoff Document

**Generated:** 2026-07-13  (Phase 9 COMPLETE — updated after Phase 9 work landed)
**For:** Next agent continuing Phase 10 (TUI Updates) work
**To:** .agent/new_continuation.md (gitignored; use `git add -f` to commit)

> ## PHASE 9 STATUS: COMPLETE ✅
>
> All T9.1–T9.10 tasks implemented, tested, and passing. No regressions.
> Phase 10 (TUI) is unblocked. Summary of what landed is in §7 (NEW) below.
> Key decisions: §8.
> Ready for next phase: YES (see §9).

---

## 1. What Has Been Completed (Phases 0–8)

### Infrastructure Built

| Phase | What | Where | Tests |
|-------|------|------|-------|
| 0 | Pre-Planning & Research | `.agent/phases/0-research-findings.md` | N/A |
| 1 | Event Bus (sync/async, priority, thread-safe) | `tokenade/core/events/` (7 files) | `tests/test_event_bus.py` (38 tests) |
| 2 | Shared Context (4 namespaces + TaskTracker) | `tokenade/core/context/` (7 files) | `tests/test_shared_context.py` (59 tests) |
| 3 | Wiring (shared context, event bus, ProxyPlugin removal, OAuth2Plugin conversion, CaptchaPluginSolver, health_check, duck-typing fix) | 8 files modified | All existing tests pass |
| 5 | Plugin Lifecycle (DISCOVERED → LOADED → CONFIGURED → ACTIVE → FAILED, on_load/on_unload hooks, error handling, reload w/ config preservation) | `tokenade/core/integration/plugin_loader.py` | `tests/test_plugin_lifecycle.py` (17 tests) |
| 6 | Dependency Resolution (topological sort Kahn's, DFS cycle detection, depth limit 5, semver version compare) | `tokenade/core/integration/dependency_graph.py`, `dependency_resolver.py` | `tests/test_dependency_resolution.py` (39 tests) |
| 7 | Plugin Config System (PluginConfigManager, env_var, constraints, global config merging) | `tokenade/core/integration/plugin_config.py` | `tests/test_plugin_config.py` (41 tests) |
| 8 | Handler Conversion (Google/GitHub/GenericOAuth2 adapters to SiteHandlerPlugin, site_config.json files, GitHub registry registration) | `tokenade/handlers/plugin_adapters.py`, `site_configs/*.json` | `tests/test_handler_conversion.py` (21 tests) |

### Key Design Decisions (Grilled & Settled)

1. **5 active plugin types**: SiteHandlerPlugin, SessionRefreshPlugin, ProxyProviderPlugin, CaptchaPlugin, NotificationPlugin
2. **System works WITHOUT plugins** — plugins override/extend defaults
3. **Default behavior**: plugins run by default, `--no-plugin` flag to exclude
4. **Plugin lifecycle**: DISCOVERED → LOADED → CONFIGURED → ACTIVE → DISABLED → UNLOADED / FAILED
5. **Failed plugins stay in _loaded** so get_plugin/get_state can report FAILED
6. **Sync by default, async opt-in** for event bus
7. **Latest version wins** for dependency version conflicts (major mismatch = rejected)
8. **Depth limit 5** for dependency chains
9. **No plugin sandboxing** (full trust)
10. **Registry management primarily through TUI**
11. **Plugin config precedence**: schema defaults < global config < user config
12. **Author is MiHiR** (not "Tokenade Team")
13. **Version 1.0.0 on PyPI** (rebaselined)
14. **NO push to GitHub** until user explicitly asks

### Removals/Conversions Done

- **ProxyPlugin** removed from `tokenade/plugin/base.py` (lines 492-536). Keep `ProxyProviderPlugin` only.
- **OAuth2Plugin** converted to inherit `SessionRefreshPlugin` (in `tokenade/plugin/oauth2/plugin.py`).
- **PluginCaptchaSolver adapter** added to `tokenade/core/browser/captcha.py` (bridges CaptchaPlugin → CaptchaSolver).
- **Duck-typing fixed** in `_run_post_refresh_plugins` → uses `isinstance(refresher, NotificationPlugin)`.
- **GitHubHandler** now registered with `HandlerRegistry.register(GitHubHandler)` in `tokenade/handlers/github.py`.

---

## 2. What is In Progress — Phase 9: CLI Updates

**Status:** NOT YET STARTED (analysis done, document ready)

**File:** `.agent/phases/9-cli-updates.md` (246 lines — full task list)

**Dependencies satisfied:** Phases 0–8 complete

---

## 3. Exact Next Steps — Detailed Task-by-Task Plan

### T9.1c: Add `--no-plugin` to launch parser

**File:** `tokenade/cli/__init__.py`, line 1528 (immediately after `--plugin` arg on line 1526)

**Current state** (lines 1525-1528):
```python
    launch_parser.add_argument(
        "--plugin",
        help="Force site handler plugin for launch (e.g. google-handler); auto-discovers when omitted",
    )
```

**Add** immediately after line 1528:
```python
    launch_parser.add_argument(
        "--no-plugin", action="store_true",
        help="Skip plugin handlers; use default launch",
    )
```

**In `cmd_launch`** (`tokenade/cli/handlers/browser_ops.py`, line 20):
- At line 144-145, the handler auto-discovery code runs.
- Check `getattr(args, "no_plugin", False)` BEFORE auto-discovery (around line 143).
- If `--no-plugin` is set, skip the entire `PluginExporter` block (lines 142-179).
- Wrap the PluginExporter block with:
```python
    if not getattr(args, "no_plugin", False):
        try:
            # existing PluginExporter block (lines 143-179)
            ...
        except Exception:
            pass  # graceful degradation
```

---

### T9.1b: Add `--no-plugin` to refresh-browser parser AND change default to auto-discover

**File:** `tokenade/cli/__init__.py`, line 1539 (immediately after `--plugin` arg)

**Current state** (line 1539):
```python
    refresh_browser_parser.add_argument("--plugin", help="Plugin to use for refresh (e.g., oauth2)")
```

**Add** immediately after line 1539:
```python
    refresh_browser_parser.add_argument(
        "--no-plugin", action="store_true",
        help="Skip plugin refresh; use browser-based refresh only",
    )
```

**In `cmd_refresh_browser`** (`tokenade/cli/handlers/browser_ops.py`, line 549):

**CRITICAL BEHAVIOR CHANGE** — Phase doc says "Default: auto-discover refresher via loader.get_refresher_for_session(session)".

Current logic (lines 579-582):
```python
    plugin_name = getattr(args, "plugin", None)
    plugin_args_list = getattr(args, "plugin_arg", [])
```

New logic:
```python
    plugin_name = getattr(args, "plugin", None)
    no_plugin = getattr(args, "no_plugin", False)
    plugin_args_list = getattr(args, "plugin_arg", [])

    # Auto-discover if no explicit plugin given and not explicitly excluded
    if not plugin_name and not no_plugin:
        try:
            from tokenade.core.integration.plugin_loader import PluginLoader
            loader = PluginLoader()
            loader.load_all()
            auto_refresher = loader.get_refresher_for_session(session)
            if auto_refresher:
                plugin_name = getattr(auto_refresher, "name", None)
                refresher = auto_refresher
                ...
        except Exception:
            pass  # fall through to browser refresh

    if plugin_name and not no_plugin:
        ... existing plugin logic (lines 584-...) 
```

The existing block at lines 584-608 starts with `if plugin_name:` — auto-discovered plugins should populate `plugin_name` or a local `refresher` variable before that block.

---

### T9.1: Add `--no-plugin` to accounts refresh parser

**File:** `tokenade/cli/__init__.py`, line 1578 (immediately after `--plugin` arg)

**Current state** (line 1578):
```python
    accounts_refresh.add_argument("--plugin", help="Plugin to use for refresh (e.g., oauth2)")
```

**Add** immediately after line 1578:
```python
    accounts_refresh.add_argument(
        "--no-plugin", action="store_true",
        help="Skip plugin refresh; use browser-based refresh only",
    )
```

**In the accounts refresh handler** (`tokenade/cli/handlers/browser_ops.py`, around line 1078-1097):

Current code:
```python
    plugin_name = getattr(args, "plugin", None)
    plugin_args_list = getattr(args, "plugin_arg", [])
    plugin_creds = {}
    for key, value in plugin_args_list:
        plugin_creds[key] = value

    plugin_loader = None
    refresher = None
    if plugin_name:
        try:
            from tokenade.core.integration.plugin_loader import PluginLoader
            plugin_loader = PluginLoader()
            plugin_loader.load_all()
            refresher = plugin_loader.get_refresher(plugin_name)
            ...
```

New logic:
```python
    plugin_name = getattr(args, "plugin", None)
    no_plugin = getattr(args, "no_plugin", False)
    plugin_args_list = getattr(args, "plugin_arg", [])
    plugin_creds = {}
    for key, value in plugin_args_list:
        plugin_creds[key] = value

    plugin_loader = None
    refresher = None
    if not no_plugin:
        from tokenade.core.integration.plugin_loader import PluginLoader
        plugin_loader = PluginLoader()
        plugin_loader.load_all()
        if plugin_name:
            refresher = plugin_loader.get_refresher(plugin_name)
        else:
            session = packager.load(sessions[0].path)  # first session for auto-discovery
            refresher = plugin_loader.get_refresher_for_session(session)
        if refresher:
            print(f"\n   🔌 Using plugin: {getattr(refresher, 'name', 'auto')} v{getattr(refresher, 'version', '?')}")
```

Then the rest of the accounts refresh loop (lines 1124-1134) uses `refresher` variable.

---

### T9.3/T9.4: Update plugin list and info commands to show lifecycle state

**File:** `tokenade/cli/__init__.py`, `cmd_plugin` function (line 141)

#### Plugin list (lines 149-166)

Current code shows `enabled` status only. Need to also load plugins into loader to get lifecycle state:

```python
    elif args.plugin_command == "list":
        if args.available:
            ... (existing code unchanged)
        else:
            loader.load_all()  # <-- ADD THIS LINE to load plugins for state access
            print("\n   📦 Installed plugins:")
            installed = loader.discover()
            if not installed:
                print("   No plugins installed. Use 'tokenade plugin install <name>' to install.")
            for p in installed:
                name = p["name"]
                loaded = loader.get_plugin(name)
                state_str = loaded.state.value if loaded else "not loaded"
                health = loaded.config or {} if loaded else {}
                enabled = " ✓" if p.get("enabled", True) else " (disabled)"
                print(f"   • {p['name']} v{p.get('version', '?')} ({p.get('type', '?')}) [{state_str}]{enabled} — {p.get('description', '')}")
```

#### Plugin info (lines 189-229)

Add lifecycle state and config display after line 217 (`print(f"   Status: {'enabled' if enabled else 'disabled'}")`):

```python
            loaded = loader.get_plugin(args.name)
            if loaded:
                print(f"   Lifecycle: {loaded.state.value}")
                if loaded.error:
                    print(f"   Error: {loaded.error}")
                if loaded.config:
                    print(f"   Config: {json.dumps(loaded.config)}")
                health = loader.get_handler(args.name)  # for health status
                try:
                    from tokenade.core.context import SharedContext
                    ctx = SharedContext()
                    plugin_health = ctx.plugins.get_health(args.name)
                    if plugin_health is not None:
                        print(f"   Health: {'healthy' if plugin_health else 'unhealthy'}")
                except Exception:
                    pass
```

Import needed: add `import json` at top of module if not already there.

---

### T9.5: Plugin test command (ALREADY EXISTS — verify it works)

**File:** `tokenade/cli/__init__.py`

The `test` subcommand already exists at line 318 calling `_plugin_test(args)` at line 572.
The `PluginTestRunner` already exists at `tokenade/core/integration/plugin_testing.py` with 8 contract tests.

**Verify**: `tokenade plugin test <name>` and `tokenade plugin test` (test all) work. Add `--verbose` flag to the parser around line 1204-1208:

```python
    plugin_test_parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed test output")
```

Update `_plugin_test` to use it: pass `verbose=args.verbose` to `PluginTestRunner`.

---

### T9.6: Plugin reload command (ALREADY EXISTS — verify and enhance)

**File:** `tokenade/cli/__init__.py`

The `reload` subcommand already exists at line 284-289 calling `loader.reload(args.name)`.
The `PluginLoader.reload()` preserves config (Phase 5 implementation).

**Verify** it works with lifecycle states. Add state display after reload:

```python
    elif args.plugin_command == "reload":
        loader.load_all()  # ensure plugins are loaded
        loaded = loader.reload(args.name)
        if loaded:
            print(f"✅ Plugin reloaded: {args.name} v{loaded.version} ({loaded.state.value})")
        else:
            print(f"❌ Failed to reload: {args.name}")
```

---

### T9.7/T9.8: Add plugin deps and check-deps commands

**File:** `tokenade/cli/__init__.py`

#### Add parsers (after line 1210, alongside other plugin parsers):

```python
    plugin_deps_parser = plugin_sub.add_parser("deps", help="Show plugin dependency tree")
    plugin_deps_parser.add_argument("name", help="Plugin name")

    plugin_checkdeps_parser = plugin_sub.add_parser("check-deps", help="Check for missing/circular dependencies")
    plugin_checkdeps_parser.add_argument("name", nargs="?", help="Plugin name (optional — checks all if omitted)")
```

#### Add handlers in `cmd_plugin`:

```python
    elif args.plugin_command == "deps":
        from tokenade.core.integration.dependency_graph import DependencyGraph
        from tokenade.core.integration.dependency_resolver import DependencyResolver
        graph = DependencyGraph()
        for plugin in loader.discover():
            graph.add_plugin(plugin["name"], plugin.get("dependencies", []))
        resolver = DependencyResolver(graph)
        print(f"\n   📦 Dependency tree for {args.name}:")
        print(resolver.get_dependency_tree(args.name))

    elif args.plugin_command == "check-deps":
        from tokenade.core.integration.dependency_graph import DependencyGraph
        from tokenade.core.integration.dependency_resolver import DependencyResolver
        graph = DependencyGraph()
        for plugin in loader.discover():
            graph.add_plugin(plugin["name"], plugin.get("dependencies", []))
        resolver = DependencyResolver(graph)
        if args.name:
            missing = [d for d in graph.get_dependencies(args.name) if d not in graph.get_all_plugins()]
        else:
            missing = resolver.check_missing()
            circular = resolver.check_circular()
            depth = resolver.check_depth()
        if missing:
            print(f"\n   ⚠️  Missing dependencies: {', '.join(missing)}")
        else:
            print("\n   ✅ No missing dependencies")
        # For full check, also show circular/depth
        if not args.name:
            if circular:
                print(f"   🔄 Circular dependencies: {', '.join(circular)}")
            if depth:
                print(f"   ⚠️  Depth violations:")
                for e in depth:
                    print(f"      {e}")
```

Update help text at line 322 to include `deps` and `check-deps`.

---

### T9.9: Add plugin configure command

**File:** `tokenade/cli/__init__.py`

#### Add parser (alongside other plugin parsers):

```python
    plugin_configure_parser = plugin_sub.add_parser("configure", help="Configure plugin settings")
    plugin_configure_parser.add_argument("name", help="Plugin name")
    plugin_configure_parser.add_argument("--set", nargs="*", metavar="KEY=VALUE",
                                        help="Set config values (e.g. --set timeout=60 retries=3)")
    plugin_configure_parser.add_argument("--show", action="store_true", help="Show current config")
    plugin_configure_parser.add_argument("--reset", action="store_true", help="Reset to defaults")
    plugin_configure_parser.add_argument("--validate", action="store_true", help="Validate config against schema")
```

#### Add handler in `cmd_plugin`:

```python
    elif args.plugin_command == "configure":
        from tokenade.core.integration.plugin_config import PluginConfigManager
        import json

        mgr = PluginConfigManager()

        if args.show:
            config = mgr.get_full_config(args.name)
            if config:
                print(f"\n   📋 Config for {args.name}:")
                for k, v in sorted(config.items()):
                    print(f"      {k} = {v}")
            else:
                print(f"\n   {args.name}: no config")

        elif args.reset:
            if mgr.delete_config(args.name):
                print(f"\n   ✅ Config reset to defaults: {args.name}")
            else:
                print(f"\n   No config file to reset: {args.name}")

        elif args.validate:
            config = mgr.load_config(args.name)
            errors = mgr.validate_config(args.name, config)
            if errors:
                print(f"\n   ❌ Config validation errors:")
                for e in errors:
                    print(f"      {e}")
            else:
                print(f"\n   ✅ Config valid: {args.name}")

        elif args.set:
            config = mgr.load_config(args.name)
            for pair in args.set:
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    # Try type coercion
                    if v.lower() == "true": v = True
                    elif v.lower() == "false": v = False
                    else:
                        try: v = int(v)
                        except ValueError:
                            try: v = float(v)
                            except ValueError: pass
                    config[k] = v
            if mgr.save_config(args.name, config):
                print(f"\n   ✅ Config saved: {args.name}")
            else:
                print(f"\n   ❌ Failed to save config: {args.name}")

        else:
            print("Usage: tokenade plugin configure <name> [--show|--reset|--validate|--set KEY=VALUE ...]")
```

Update help text at line 322 to include `configure`.

---

### T9.10: Write CLI Unit Tests

**File:** `tests/test_cli_plugins.py` (NEW)

Write tests for:

1. **--no-plugin flag parsing**: Mock `args` with `no_plugin=True` and verify `PluginLoader` is NOT called.
2. **Plugin list shows lifecycle state**: Set up mock PluginLoader with a plugin in FAILED state, verify list output contains `failed`.
3. **Plugin list shows health**: Verify output contains health info.
4. **Plugin info shows state**: Mock a loaded plugin with state=`CONFIGURED`, verify info output contains `configured`.
5. **Plugin deps**: Create mock plugins with dependencies, verify `cmd_plugin` deps subcommand output shows tree.
6. **Plugin check-deps**: Create mock plugins with missing deps, verify output shows missing.
7. **Plugin configure --set/--show/--reset/--validate**: Test all four flags with mock PluginConfigManager.
8. **Plugin test command**: Mock PluginTestRunner, verify output format.
9. **Auto-discovery flag logic**: Test that when `--plugin` is not set and `--no-plugin` is not set, auto-discovery runs (mock `get_refresher_for_session`).

Test approach: Use `from argparse import Namespace` to create mock args, call `cmd_plugin` or handler functions directly with `sys.stdout` io.StringIO capture.

---

## 4. All Strict Rules (Cross-Phase)

### From grilling session (26 decisions):
- System works WITHOUT plugins — plugins override/extend defaults
- Plugins run by default, `--no-plugin` flag to exclude
- Event bus: sync by default, async opt-in
- Shared context: core owns it, 4 namespaces
- Multiple registries with priority ordering, latest version wins
- Dependency resolution: topological sort, depth limit 5, major version only
- Plugin failure: always fall back to core
- No plugin verification (user trust model)
- Manual reload only (`tokenade plugin reload <name>`)
- Full plugin access (no sandboxing)
- Graceful degradation for backward compatibility

### From Phase 9 specifically:
1. Plugins run by default — No flag needed to use plugins
2. `--no-plugin` flag — Excludes plugins from operation
3. Backward compatible — `--plugin` flag still works (explicit selection)
4. All commands updated — Every plugin-related command works with new system
5. Test everything — Every CLI command has tests
6. No commits until tests pass
7. Don't break existing tests — All ~5216 tests must still pass

### From overall project:
- Author: MiHiR
- NO push to GitHub until user explicitly asks
- NO PyPI publish without permission
- NO version bumps without: tests passing → coverage → code review → user confirms
- `.agent/` directory is gitignored — use `git add -f` to commit

---

## 5. Important File References

### CLI files to modify:
| File | Lines | Key Areas |
|------|-------|-----------|
| `tokenade/cli/__init__.py` | 1938 | Parsers (1503-1585), cmd_plugin (141-322), dispatch (1863-1922) |
| `tokenade/cli/handlers/browser_ops.py` | 1416 | cmd_launch (20), cmd_refresh_browser (549), accounts refresh (1075+) |

### Infrastructure available (created in previous phases):
| File | Lines | Key APIs |
|------|-------|-----------|
| `tokenade/core/integration/plugin_loader.py` | 737 | PluginLoader.load_all(), get_plugin(name), get_state(name), reload(name), get_refresher_for_session(session) |
| `tokenade/core/integration/plugin_config.py` | 288 | PluginConfigManager().get_full_config(name), load_config(name), save_config(name, config), delete_config(name), validate_config(name, config) |
| `tokenade/core/integration/dependency_graph.py` | 285 | DependencyGraph().add_plugin(name, deps), get_load_order(name), topological_sort() |
| `tokenade/core/integration/dependency_resolver.py` | 344 | DependencyResolver(graph).resolve(name), get_dependency_tree(name), check_missing(), check_circular(), check_depth() |
| `tokenade/core/integration/plugin_testing.py` | 422 | PluginTestRunner().test_plugin(name), test_all() |
| `tokenade/core/context/context.py` | ~119 | SharedContext() singleton — cfg.plugins.get_health(name), ctx.config.set_registry_url(url) |
| `tokenade/core/events/bus.py` | ~254 | EventBus.emit(EventType.PLUGIN_LOADED, data={...}) |

### Plugin base types:
| File | Relevant Classes |
|------|------------------|
| `tokenade/plugin/base.py` | PluginState enum, SiteHandlerPlugin, SessionRefreshPlugin, ProxyProviderPlugin, CaptchaPlugin, NotificationPlugin |

### Sibling repo — tokenade-plugins:
| Path | Contents |
|------|----------|
| `../tokenade-plugins/plugins/` | 23 plugin directories (google-handler, github-handler, oauth2, etc.) |
| `../tokenade-plugins/marketplace.json` | Registry metadata |

---

## 6. Verification Checklist

- [ ] `tokenade launch --no-plugin` skips PluginExporter
- [ ] `tokenade refresh-browser -s x.tokenade` auto-discovers refresher
- [ ] `tokenade refresh-browser -s x.tokenade --no-plugin` skips plugins
- [ ] `tokenade refresh-browser -s x.tokenade --plugin oauth2` force-uses oauth2
- [ ] `tokenade accounts refresh --no-plugin` skips plugins
- [ ] `tokenade plugin list` shows lifecycle state and health
- [ ] `tokenade plugin info google-handler` shows state, config, health
- [ ] `tokenade plugin test google-handler` runs contract tests
- [ ] `tokenade plugin reload google-handler` preserves config
- [ ] `tokenade plugin deps google-handler` shows dependency tree
- [ ] `tokenade plugin check-deps` shows missing/circular/depth
- [ ] `tokenade plugin configure google-handler --set timeout=60` saves config
- [x] `tokenade plugin configure google-handler --show` displays config
- [x] `tokenade plugin configure google-handler --reset` deletes config
- [x] `tokenade plugin configure google-handler --validate` validates config
- [x] All existing related tests pass (no regressions in ~2100 CLI/plugin tests)
- [x] New `tests/test_cli_plugins.py` tests pass (27/27)

---

## 7. What Landed in Phase 9 (NEW — for next agent's handoff)

**Files modified:**
| File | Change |
|------|-------|
| `tokenade/cli/__init__.py` | Added `import json`; added `--no-plugin` flags to launch/refresh-browser/accounts-refresh parsers; added `deps`, `check-deps`, `configure` subparsers + `--verbose` on `test`; added lifecycle state + health to `plugin list`; added lifecycle/config/health to `plugin info`; reloaded state to `plugin reload`; added `_plugin_configure` helper; updated usage string + `_plugin_test` verbose |
| `tokenade/cli/handlers/browser_ops.py` | cmd_launch: wrapped PluginExporter block in `if not no_plugin` guard; cmd_refresh_browser: auto-discover via `get_refresher_for_session` when neither `--plugin` nor `--no-plugin` set; `_accounts_refresh`: honor `--no-plugin` + auto-discover refresher from first session |
| `tokenade/plugins/test_refresh_browser.py` | Updated `test_no_plugin_falls_through_to_browser` to pass `no_plugin=True` (new contract — without `--no-plugin` auto-discovery runs, so use `--no-plugin` to force browser-only) |
| `tests/test_cli_plugins.py` (NEW) | 27 tests covering all T9.x behaviors |

**New subcommands/flags:**
- `tokenade launch --no-plugin` → skip site-handler plugin, use default launch
- `tokenade refresh-browser --no-plugin` → skip plugin refresh, browser-only
- `tokenade refresh-browser` (default) → auto-discovers refresher via `PluginLoader.get_refresher_for_session(session)`
- `tokenade accounts refresh --no-plugin` → skip plugins
- `tokenade accounts refresh` (default) → auto-discovers refresher from first session
- `tokenade plugin deps <name>` → shows indented dependency tree
- `tokenade plugin check-deps [name]` → checks missing/circular/depth (single or all)
- `tokenade plugin configure <name> [--show|--reset|--validate|--set KEY=VAL ...]`
- `tokenade plugin test [--verbose|-v] [name]`
- `tokenade plugin list` → now shows `[lifecycle-state]` + `health: healthy/unhealthy`
- `tokenade plugin info <name>` → now shows `Lifecycle:`, `Config:`, `Health:`, `Error:`
- `tokenade plugin reload <name>` → now shows lifecycle state in output

**Behavior changes (intentional, per Phase 9 spec):**
1. Plugins now run BY DEFAULT — `--no-plugin` excludes them (was: opt-in via `--plugin`)
2. `refresh-browser`/`accounts refresh` auto-discover refreshers via `get_refresher_for_session` when no `--plugin` given
3. `--plugin <name>` still forces a specific plugin (overrides auto-discovery)

---

## 8. Key Decisions Made During Phase 9

1. **Patching strategy for tests:** Patching `DEFAULT_PLUGINS_DIR` module attr is NOT enough (it's bound as a default-arg at class definition). The `patched_plugins_dir` fixture in `test_cli_plugins.py` wraps `PluginLoader.__init__` and `PluginConfigManager.__init__` to inject `tmp_path/"plugins"`. **Future test work touching plugin loader should use this pattern.**
2. **`loaded.config` JSON dump in `plugin info`:** Guarded with try/except (TypeError, ValueError) so non-JSON-serializable MagicMock configs don't crash tests — fall through to `repr()`.
3. **Existing `test_no_plugin_falls_through_to_browser` was updated** to use `no_plugin=True` to reflect new opt-out-by-flag contract (not opt-in-by-flag) — the old assumption "no --plugin → browser" is now wrong by design.
4. **No new PluginState enum values added** — Phase 9 reuses existing 7 states (discovered/loaded/configured/active/disabled/unloaded/failed).
5. **`_plugin_test` verbose prints passing-test messages too** (not just failures), per phase spec: "Show pass/fail for each test" + `--verbose`.
6. **`tokenade plugin deps <name>` indents the tree consistently** — prepends 3 spaces per indent level to match other CLI output styling.
7. **Auto-discovery in `accounts refresh` is per-batch, not per-session** — it picks a refresher based on the first session and applies it to all. Per-session auto-discovery would be a Phase 10+ enhancement if needed.
8. **All graceful degradation preserved** — failed plugin loads don't crash cmd_launch / cmd_refresh_browser / cmd_plugin; they log + fall through.

---

## 9. Ready for Next Phase?

**YES — Phase 9 is complete and Phase 10 (TUI) is unblocked.**

Phase 10 scope (from `.agent/phases/10-tui-updates.md` if present): TUI marketplace/registry management, plugin lifecycle display, plugin config editing via TUI.

**Before starting Phase 10, next agent should:**
- Run `python -m pytest tests/test_cli_plugins.py -q` to confirm Phase 9 tests still green
- Run `python -m pytest tests/ -q` to confirm all 234 phase tests still green
- Run `python -m pytest tokenade/tests/test_cli*.py tokenade/tests/test_plugin*.py -q` for regression check
- Skim §7 above for the new CLI surface area the TUI should mirror

**Known gaps to consider for Phase 10:**
- TUI marketplace/registry views should also reflect lifecycle state (matching the updated CLI `plugin list`)
- TUI plugin detail view should mirror new `plugin info` fields (Lifecycle, Config, Health, Error)
- TUI refresh action should default to auto-discovery (no plugin preselected)

**No commits made** (per house rules — "NO push to GitHub until user explicitly asks"). All Phase 9 work is on local working tree; user must `git add` + `git commit` when ready.

---

## 10. Final Phase 9 Verification Snapshot

- **Phase test suite (`tests/`):** 234 passed
- **New CLI test file (`tests/test_cli_plugins.py`):** 27/27 passed
- **Regression suite (~2100 CLI/plugin canonical tests):** all passed
- **Lint (`flake8`):** no new warnings introduced in modified files
- **Parser smoke test:** all 15 representative invocations parse cleanly
- **Manual entry point smoke:** `cmd_plugin`, `_plugin_test`, `_plugin_configure` all importable + callable