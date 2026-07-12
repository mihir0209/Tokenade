# Phase 0: Research Findings

**Date:** 2026-07-12
**Status:** COMPLETE
**Purpose:** Audit current codebase state, validate design assumptions, identify all files needing changes

---

## Executive Summary

**Plugin system state:** 9 base classes defined, 8 types registered in loader, only 2 types actually invoked in production (SiteHandlerPlugin, SessionRefreshPlugin). The remaining 6 types are loaded into dictionaries and never called.

**Event/notification state:** 5 independent ad-hoc webhook implementations. No unified event bus. NotificationPlugin interface exists but is never invoked.

**Scheduler state:** 3 independent internal schedulers (daemon, refresher, monitor). No unified scheduler abstraction. No plugin hooks.

**CLI state:** 4 commands have `--plugin` flags. Only `export` has `--no-plugin`. Default behavior varies by command.

**Key finding:** The infrastructure is architecturally complete (loader, registry, type registries, testing framework) but has a massive gap between "loaded" and "consumed."

---

## 1. Plugin System Files

### 1.1 Base Classes (`tokenade/plugin/base.py`)

| Class | Lines | Status | Notes |
|-------|-------|--------|-------|
| `PluginBase` | 34-106 | Active | Root class, has on_load/on_configure/on_unload/health_check |
| `SessionRefreshPlugin` | 108-158 | **Active** | Used in refresh commands via `--plugin` flag |
| `SiteHandlerPlugin` | 161-413 | **Active** | Used in export flow for domain filtering |
| `ExportFormatPlugin` | 416-433 | **Dead** | `get_exporter()` never called |
| `SessionValidatorPlugin` | 436-448 | **Dead** | `get_validator()` never called |
| `StealthPlugin` | 451-489 | **Dead** | StealthManager handles everything |
| `ProxyPlugin` | 492-536 | **Dead** | "Legacy", replaced by ProxyProviderPlugin |
| `CaptchaPlugin` | 538-584 | **Dead** | CaptchaSolver system ignores it |
| `ProxyProviderPlugin` | 587-682 | **Partial** | ProxyManager has hook but not wired |
| `NotificationPlugin` | 685-721 | **Dead** | No event bus to trigger it |

### 1.2 API Types (`tokenade/plugin/api.py`)

| Type | Lines | Status | Notes |
|------|-------|--------|-------|
| `API_VERSION` | 21 | Active | Currently "1.1.0" |
| `PluginResult` | 24-48 | Active | Standard result type |
| `PluginMetadata` | 51-66 | Active | Plugin metadata |
| `PluginConfigSchema` | 69-76 | Active | Config schema |
| `PluginConfig` | 79-139 | Active | Config with validation |

### 1.3 OAuth2 Plugin (`tokenade/plugin/oauth2/plugin.py`)

| Item | Lines | Status | Notes |
|------|-------|--------|-------|
| `OAuth2Plugin` | 49-282 | **Standalone** | Does NOT inherit from PluginBase or SessionRefreshPlugin |
| `can_refresh()` | 60-84 | Works | Checks for refresh_token in session |
| `refresh()` | 86-162 | Works | Exchanges refresh token for new access token |
| `get_credentials_args()` | 164-192 | Works | Defines CLI args |

**Critical finding:** OAuth2Plugin is a standalone class, not a PluginBase subclass. It cannot be loaded by PluginLoader (which checks `issubclass(attr, target_cls)`). It works via manual instantiation in the `--plugin oauth2` CLI flow.

### 1.4 Plugin `__init__.py` (`tokenade/plugin/__init__.py`)

Exports all 9 base classes + 4 API types. Clean, no issues.

---

## 2. Plugin Infrastructure

### 2.1 Plugin Loader (`tokenade/core/integration/plugin_loader.py`)

| Item | Lines | Status | Notes |
|------|-------|--------|-------|
| `PluginLoader.__init__` | 62-74 | Active | 8 type registries + disabled set |
| `discover()` | 76-98 | Active | Scans `~/.tokenade/plugins/` for plugin.json |
| `load_all()` | 100-118 | Active | Loads all discovered plugins |
| `load_plugin()` | 120-275 | Active | Import, instantiate, register by type |
| `unload()` | 277-305 | Active | Remove from registries |
| `get_handler()` | 307-309 | **Used** | Called in export flow |
| `get_exporter()` | 311-313 | **Dead** | Never called |
| `get_validator()` | 315-317 | **Dead** | Never called |
| `get_refresher()` | 319-321 | **Used** | Called in refresh commands |
| `get_stealth()` | 323-325 | **Dead** | Never called |
| `get_proxy_plugin()` | 327-329 | **Dead** | Never called |
| `get_captcha()` | 331-333 | **Dead** | Never called |
| `get_refresher_for_session()` | 335-343 | **Used** | Called in auto-discovery |
| `reload()` | 377-389 | Active | Manual reload |
| `enable()/disable()` | 409-432 | Active | Plugin management |

**Critical finding:** `on_configure()` is never called by the loader. `health_check()` is never called by the loader.

### 2.2 Plugin Registry (`tokenade/core/integration/plugin_registry.py`)

| Item | Lines | Status | Notes |
|------|-------|--------|-------|
| `PluginRegistry.__init__` | 73-85 | Active | Single registry URL |
| `search()` | 115-194 | Active | Search with filtering/sorting |
| `install()` | 309-348 | Active | Install from registry |
| `uninstall()` | 350-366 | Active | Remove plugin |
| `list_installed()` | 368-397 | Active | List local plugins |
| `get_outdated()` | 399-416 | Active | Check for updates |
| `update()` | 418-441 | Active | Update plugins |
| `_fetch_registry()` | 443-469 | Active | Fetch from GitHub with 1-hour cache |
| `discover_from_url()` | 508-585 | Active | Discover from any URL |

**Critical finding:** Registry is hardcoded to single URL (`DEFAULT_REGISTRY_URL`). No multiple registry support. No priority ordering.

### 2.3 Plugin Verifier (`tokenade/core/integration/plugin_verifier.py`)

| Item | Lines | Status | Notes |
|------|-------|--------|-------|
| `PluginVerifier.__init__` | 39-43 | Active | Checksums file |
| `verify()` | 45-107 | Active | SHA256 verification |
| `verify_all()` | 109-117 | Active | Verify all plugins |
| `store_checksums()` | 119-122 | Active | Store expected checksums |
| `compute_plugin_checksums()` | 124-139 | Active | Compute checksums |

**Status:** Working, no changes needed for Phase 1-8.

### 2.4 Plugin Testing (`tokenade/core/integration/plugin_testing.py`)

| Item | Lines | Status | Notes |
|------|-------|--------|-------|
| `PluginTestRunner.test_plugin()` | 60-73 | Active | 8 contract tests |
| Test 1: manifest_exists | 75-83 | Active | |
| Test 2: manifest_valid | 85-122 | Active | Validates JSON, required fields, type enum |
| Test 3: entry_point_exists | 124-142 | Active | |
| Test 4: entry_class_importable | 144-170 | Active | |
| Test 5: plugin_instantiable | 172-229 | Active | |
| Test 6: plugin_metadata | 231-256 | Active | |
| Test 7: type_methods | 258-341 | Active | Checks required methods per type |
| Test 8: type_class_match | 343-412 | Active | Manifest type matches class base |

**Status:** Working, no changes needed for Phase 1-8.

### 2.5 Plugin Export (`tokenade/core/importer/plugin_export.py`)

| Item | Lines | Status | Notes |
|------|-------|--------|-------|
| `PluginExporter.__init__` | 28-29 | Active | Handler cache |
| `_load_handlers()` | 31-43 | Active | Load all handler plugins |
| `find_handler()` | 45-104 | Active | Find handler by domains |
| `get_handler()` | 106-115 | Active | Get handler by name |
| `export()` | 117-146 | Active | Export with plugin or default |
| `_export_with_plugin()` | 148-238 | Active | Plugin-based export |
| `_export_default()` | 240-309 | Active | Default export |

**Status:** Working. Uses SiteHandlerPlugin for domain filtering and site config.

### 2.6 Plugin Search (`tokenade/core/integration/plugin_search.py`)

**Not read in detail** — TF-IDF search index. Working, no changes needed.

### 2.7 Plugin Browser (`tokenade/core/integration/plugin_browser.py`)

**Not read in detail** — HTML marketplace generator. Working, no changes needed.

---

## 3. Event/Notification Infrastructure

### 3.1 Ad-hoc Webhook Implementations (5 independent)

| Location | File | Lines | Format | Signing | Notes |
|----------|------|-------|--------|---------|-------|
| SessionDaemon | `core/daemon/session_daemon.py` | 618-663 | Slack `{"text": ...}` | No | Bare urllib |
| HealthReporter | `core/refresh/health_reporter.py` | 334-379 | Slack `{"text": ...}` | No | Bare urllib |
| SessionSharer | `core/importer/session_sharer.py` | 416-488 | Structured JSON | HMAC-SHA256 | Best implementation |
| CI Runner | `cli/handlers/ci.py` | 196-208 | Slack `{"text": ...}` | No | Uses requests |
| WorkflowGenerator | `core/cicd/workflow_generator.py` | 41 | Config field only | No | Not used |

**Critical finding:** No unified event bus. No pub/sub system. NotificationPlugin interface exists but is never invoked.

### 3.2 NotificationPlugin Integration Gap

- `NotificationPlugin` defined at `base.py:685-721`
- `PluginLoader._notifications` stores instances at `plugin_loader.py:72,266`
- **No code anywhere loads or invokes NotificationPlugin instances**
- Example webhook plugin (`examples/plugins/my_webhook_notify/plugin.py`) uses architectural hack (pretends to be refresher) because NotificationPlugin has no invocation pathway

### 3.3 WebSocket Notifications (Internal)

- `core/refresh/session_refresher.py:33-34,443-449` — Async WebSocket notification
- Uses callback pattern (`notify_ws` on `RefreshConfig`)
- Not connected to plugin system

### 3.4 Session Monitor Events

- `core/monitoring/session_monitor.py:67-74` — MonitorEvent dataclass
- `core/monitoring/session_monitor.py:314-325` — `_emit_event()` to history and alert callback
- Callback-based, not plugin-connected

---

## 4. Scheduler/Cron Infrastructure

### 4.1 Internal Schedulers (3 independent)

| Scheduler | File | Lines | Mechanism | Plugin Hooks |
|-----------|------|-------|-----------|--------------|
| SessionDaemon | `core/daemon/session_daemon.py` | 486-515 | `threading.Event.wait(timeout)` | **No** |
| SessionRefresher | `core/refresh/session_refresher.py` | 150-168 | `asyncio.create_task` loop | **No** |
| SessionMonitor | `core/monitoring/session_monitor.py` | 179-193 | `threading.Thread` loop | **No** |

### 4.2 External Scheduler (Template Generation)

- `core/cicd/workflow_generator.py` — Generates GitHub Actions, GitLab CI, cron scripts
- Generates static files, no dynamic scheduling
- `notification_webhook` config field (line 41) not used in generated output
- Generated CI/CD templates do not invoke plugins

**Critical finding:** No unified scheduler abstraction. No plugin hooks in any scheduler.

---

## 5. Session Management Flow

### 5.1 Plugin Integration Call Sites

| Call Site | File | Lines | Plugin Used | Default Behavior |
|-----------|------|-------|-------------|-----------------|
| `cmd_refresh_browser` | `browser_ops.py` | 579-629 | SessionRefreshPlugin | **Opt-in** (`--plugin` required) |
| `_accounts_refresh` | `browser_ops.py` | 1077-1140 | SessionRefreshPlugin | **Opt-in** (`--plugin` required) |
| `cmd_export` | `session_export.py` | 176-219 | SiteHandlerPlugin | **Opt-out** (plugins ON by default) |
| `cmd_launch` | `browser_ops.py` | 145-186 | SiteHandlerPlugin | **Auto-discover** (no opt-out) |
| `_run_post_refresh_plugins` | `session_ops.py` | 757-767 | All refreshers | **Duck-typed** (checks `_send_webhook`) |
| `SessionDaemon._refresh_session` | `session_daemon.py` | 358-467 | **None** | No plugin support |

### 5.2 CLI Plugin Flags

| Command | `--plugin` | `--no-plugin` | Default |
|---------|-----------|---------------|---------|
| `export` | Yes (string) | **Yes** | Plugins ON |
| `launch` | Yes (string) | **No** | Auto-discover |
| `refresh-browser` | Yes (string) | **No** | Opt-in only |
| `accounts refresh` | Yes (string) | **No** | Opt-in only |

**Critical finding:** Default behavior varies by command. `refresh-browser` and `accounts refresh` require explicit `--plugin` flag. Need to change to auto-discover by default.

### 5.3 `_run_post_refresh_plugins` Duck-Typing

```python
# session_ops.py:757-767
for name, refresher in loader.list_refreshers().items():
    if hasattr(refresher, "_send_webhook") or refresher.can_refresh(session):
        try:
            refresher.refresh(session, {})
        except Exception:
            pass
```

**Critical finding:** Uses duck-typing (`_send_webhook` attribute) to identify webhook-type plugins. Fragile and non-intuitive.

---

## 6. Captcha System

### 6.1 Core System (`tokenade/core/browser/captcha.py`)

| Component | Lines | Notes |
|-----------|-------|-------|
| `CaptchaType` enum | 17-27 | 8 types: RECAPTCHA_V2, RECAPTCHA_V3, HCAPTCHA, TURNSTILE, etc. |
| `CaptchaSolver` ABC | 49-78 | `solve(challenge) -> CaptchaSolution` |
| `CaptchaDetector` | 100-183 | HTML pattern detection |
| `CaptchaManager` | 186-244 | Orchestrates detection + solving |
| `NullCaptchaSolver` | 81-97 | Default no-op solver |

### 6.2 Plugin System (`tokenade/plugin/base.py:538-584`)

| Component | Lines | Notes |
|-----------|-------|-------|
| `CaptchaPlugin` | 538-584 | `solve(captcha_type, site_key, page_url) -> Dict` |

**Critical finding:** `CaptchaPlugin` and `CaptchaSolver` are completely separate interfaces. No adapter exists. `CaptchaManager.set_solver()` accepts only `CaptchaSolver` instances.

---

## 7. Stealth System

### 7.1 Core System (`tokenade/core/browser/stealth/manager.py`)

| Component | Lines | Notes |
|-----------|-------|-------|
| `StealthConfig` | 32-49 | 14 toggleable patches |
| `build_stealth_script()` | 431-463 | Composes all patches into IIFE JS |
| `StealthManager` | 597-671 | Production-grade, 10+ patches |

### 7.2 Plugin System (`tokenade/plugin/base.py:451-489`)

| Component | Lines | Notes |
|-----------|-------|-------|
| `StealthPlugin` | 451-489 | `get_patches() -> List[str]` |

**Critical finding:** `StealthManager` is never composed with `StealthPlugin` instances. No adapter exists. `get_patches() -> List[str]` is too simple for real stealth work.

---

## 8. Proxy System

### 8.1 Core System (`tokenade/core/proxy/manager.py`)

| Component | Lines | Notes |
|-----------|-------|-------|
| `ProxyConfig` | 24-115 | Standard proxy dataclass |
| `ProxyManager` | 118-275 | Priority chain: plugin -> CLI -> config |
| `register_plugin()` | 146 | **Exists but never called** |
| `_get_from_plugin()` | 216-248 | Calls `plugin.get_sticky_proxy()` / `plugin.get_rotating_proxy()` |

### 8.2 Plugin System

| Component | Lines | Notes |
|-----------|-------|-------|
| `ProxyPlugin` | 492-536 | Legacy, returns Dict |
| `ProxyProviderPlugin` | 587-682 | New, returns PluginResult |

**Critical finding:** `ProxyManager` already has `register_plugin()` and `_get_from_plugin()` that match `ProxyProviderPlugin`'s interface. But **no CLI command passes a loaded plugin to ProxyManager**. The wiring exists but is not connected.

---

## 9. CLI Plugin Commands

### 9.1 Plugin Management Commands (17 subcommands)

| Command | File | Lines | Status |
|---------|------|-------|--------|
| `tokenade plugin list` | `__init__.py` | 149-166 | Working |
| `tokenade plugin install` | `__init__.py` | 168-180 | Working |
| `tokenade plugin uninstall` | `__init__.py` | 182-187 | Working |
| `tokenade plugin info` | `__init__.py` | 189-229 | Working |
| `tokenade plugin enable` | `__init__.py` | 231-235 | Working |
| `tokenade plugin disable` | `__init__.py` | 237-241 | Working |
| `tokenade plugin update` | `__init__.py` | 243-263 | Working |
| `tokenade plugin sync` | `__init__.py` | 264-283 | Working |
| `tokenade plugin reload` | `__init__.py` | 284-289 | Working |
| `tokenade plugin search` | `__init__.py` | 291-359 | Working |
| `tokenade plugin categories` | `__init__.py` | 294-375 | Working |
| `tokenade plugin popular` | `__init__.py` | 297-402 | Working |
| `tokenade plugin recent` | `__init__.py` | 300-422 | Working |
| `tokenade plugin rate` | `__init__.py` | 303-443 | Working |
| `tokenade plugin ratings` | `__init__.py` | 306-479 | Working |
| `tokenade plugin verify` | `__init__.py` | 309-532 | Working |
| `tokenade plugin outdated` | `__init__.py` | 312-554 | Working |
| `tokenade plugin browse` | `__init__.py` | 315-569 | Working |
| `tokenade plugin test` | `__init__.py` | 318-606 | Working |

### 9.2 Missing Commands (from design doc)

| Command | Status | Notes |
|---------|--------|-------|
| `tokenade plugin deps` | **Missing** | Dependency tree |
| `tokenade plugin check-deps` | **Missing** | Check missing deps |
| `tokenade plugin configure` | **Missing** | Plugin configuration |
| `tokenade registry list` | **Missing** | Registry management |
| `tokenade registry add` | **Missing** | Add registry |
| `tokenade registry remove` | **Missing** | Remove registry |
| `tokenade registry enable` | **Missing** | Enable registry |
| `tokenade registry disable` | **Missing** | Disable registry |
| `tokenade registry priority` | **Missing** | Set priority |

---

## 10. TUI Plugin Integration

### 10.1 TUI Screens (`tokenade/tui/app.py`)

| Screen | Lines | Status | Notes |
|--------|-------|--------|-------|
| `MarketplaceView` | 428-444 | Working | Browse/search plugins |
| `InstalledView` | 448-454 | Working | Manage installed plugins |
| `PluginDetailScreen` | 249-363 | Working | Full plugin detail |
| `RateScreen` | 367-424 | Working | Rate plugins |
| `SettingsView` | 467-494 | Working | Registry settings |
| `SessionsView` | 458-464 | Working | Session management |

### 10.2 Missing TUI Features (from design doc)

| Feature | Status | Notes |
|---------|--------|-------|
| Registry management (add/remove/enable/disable) | **Partial** | Can change URL, not multi-registry |
| Plugin health visualization | **Missing** | No health status display |
| Plugin config visualization | **Missing** | No config display |
| Plugin task visualization | **Missing** | No task display |

---

## 11. Files Needing Changes (by Phase)

### Phase 1: Event Bus
| File | Action | Notes |
|------|--------|-------|
| `tokenade/core/events/__init__.py` | **Create** | Public API |
| `tokenade/core/events/types.py` | **Create** | EventType, Event, Priority |
| `tokenade/core/events/bus.py` | **Create** | EventBus |
| `tokenade/core/events/scheduler.py` | **Create** | Scheduler |
| `tokenade/core/events/handlers.py` | **Create** | Handler base classes |
| `tokenade/core/events/dispatchers.py` | **Create** | Dispatchers |
| `tokenade/core/events/triggers.py` | **Create** | Trigger types |
| `tests/test_event_bus.py` | **Create** | Unit tests |

### Phase 2: Shared Context
| File | Action | Notes |
|------|--------|-------|
| `tokenade/core/context/__init__.py` | **Create** | Public API |
| `tokenade/core/context/context.py` | **Create** | SharedContext |
| `tokenade/core/context/sessions.py` | **Create** | Sessions namespace |
| `tokenade/core/context/plugins.py` | **Create** | Plugins namespace |
| `tokenade/core/context/config.py` | **Create** | Config namespace |
| `tokenade/core/context/runtime.py` | **Create** | Runtime namespace |
| `tokenade/core/context/tasks.py` | **Create** | Task state tracking |
| `tests/test_shared_context.py` | **Create** | Unit tests |

### Phase 3: Fix Wiring
| File | Action | Notes |
|------|--------|-------|
| `tokenade/core/integration/plugin_loader.py` | **Modify** | Wire on_configure(), shared context |
| `tokenade/core/health/health_reporter.py` | **Modify** | Wire health_check() |
| `tokenade/plugin/oauth2/plugin.py` | **Modify** | Convert to PluginBase subclass |
| `tokenade/plugin/base.py` | **Modify** | Remove ProxyPlugin |
| `tokenade/core/browser/captcha.py` | **Modify** | Add PluginCaptchaSolver adapter |
| `tokenade/core/operations/session_ops.py` | **Modify** | Emit events, fix duck-typing |
| `tests/test_plugin_wiring.py` | **Create** | New tests |

### Phase 4: Registry System
| File | Action | Notes |
|------|--------|-------|
| `tokenade/core/integration/registry_manager.py` | **Create** | RegistryManager |
| `tokenade/core/integration/registry_cache.py` | **Create** | RegistryCache |
| `tokenade/core/integration/plugin_registry.py` | **Modify** | Add registry_name, priority params |
| `tokenade/cli/__init__.py` | **Modify** | Add registry commands |
| `tests/test_registry_manager.py` | **Create** | Unit tests |

### Phase 5: Plugin Lifecycle
| File | Action | Notes |
|------|--------|-------|
| `tokenade/core/integration/plugin_loader.py` | **Modify** | Lifecycle states, hooks, reload |
| `tokenade/core/health/health_reporter.py` | **Modify** | Plugin health checks |
| `tokenade/core/context/tasks.py` | **Modify** | Task state tracking |
| `tests/test_plugin_lifecycle.py` | **Create** | Unit tests |

### Phase 6: Dependency Resolution
| File | Action | Notes |
|------|--------|-------|
| `tokenade/core/integration/dependency_graph.py` | **Create** | DependencyGraph |
| `tokenade/core/integration/dependency_resolver.py` | **Create** | DependencyResolver |
| `tokenade/cli/__init__.py` | **Modify** | Add dependency commands |
| `tests/test_dependency_resolution.py` | **Create** | Unit tests |

### Phase 7: Plugin Config
| File | Action | Notes |
|------|--------|-------|
| `tokenade/core/integration/plugin_config.py` | **Create** | PluginConfigManager |
| `tokenade/plugin/api.py` | **Modify** | Extend PluginConfigSchema |
| `tokenade/cli/__init__.py` | **Modify** | Add configure commands |
| `tokenade/core/integration/plugin_loader.py` | **Modify** | Wire on_configure() |
| `tests/test_plugin_config.py` | **Create** | Unit tests |

### Phase 8: Convert Handlers
| File | Action | Notes |
|------|--------|-------|
| `~/.tokenade/plugins/google-handler/` | **Create** | Google handler plugin |
| `~/.tokenade/plugins/github-handler/` | **Create** | GitHub handler plugin |
| `~/.tokenade/plugins/generic-oauth-handler/` | **Create** | Generic OAuth plugin |
| `tokenade/core/importer/plugin_export.py` | **Modify** | Add legacy fallback |
| `tests/test_handler_conversion.py` | **Create** | Tests |

### Phase 9: CLI Updates
| File | Action | Notes |
|------|--------|-------|
| `tokenade/cli/session_export.py` | **Modify** | Update export commands |
| `tokenade/cli/handlers/browser_ops.py` | **Modify** | Update refresh commands |
| `tokenade/cli/__init__.py` | **Modify** | Update/add plugin commands |
| `tests/test_cli_plugins.py` | **Create** | Tests |

### Phase 10: TUI Updates
| File | Action | Notes |
|------|--------|-------|
| `tokenade/tui/app.py` | **Modify** | Update/add TUI screens |
| `tests/test_tui_plugins.py` | **Create** | Tests |

### Phase 11: Documentation
| File | Action | Notes |
|------|--------|-------|
| `docs/plugin-author-guide.md` | **Create** | Plugin author guide |
| `docs/plugin-api.md` | **Create** | API documentation |
| `docs/plugin-user-guide.md` | **Create** | User guide |
| `docs/plugin-contributor-guide.md` | **Create** | Contributor guide |
| `docs/plugin-migration-guide.md` | **Create** | Migration guide |
| `examples/plugins/*/` | **Create** | Example plugins |
| `README.md` | **Modify** | Update plugin section |
| `CONTRIBUTING.md` | **Modify** | Add plugin contribution guide |
| `ARCHITECTURE.md` | **Modify** | Add plugin system architecture |
| `CHANGELOG.md` | **Modify** | Add plugin system changes |

---

## 12. Design Assumption Validation

| Assumption | Validated? | Notes |
|-----------|-----------|-------|
| Plugin system is architecturally complete | **Yes** | Loader, registry, type registries, testing framework exist |
| Only 2 plugin types are actually used | **Yes** | SiteHandlerPlugin and SessionRefreshPlugin |
| 8 plugin types are dead code | **Yes** | Loaded but never called |
| OAuth2Plugin doesn't inherit from PluginBase | **Yes** | Standalone class |
| Duplicate abstractions exist | **Yes** | ProxyPlugin vs ProxyProviderPlugin, CaptchaPlugin vs CaptchaSolver |
| on_configure() never called | **Yes** | Loader doesn't invoke it |
| health_check() never called | **Yes** | Loader doesn't invoke it |
| No event bus exists | **Yes** | 5 ad-hoc webhook implementations |
| No scheduler abstraction exists | **Yes** | 3 independent schedulers |
| Registry is hardcoded to single URL | **Yes** | No multiple registry support |
| CLI default behavior varies | **Yes** | export=opt-out, refresh=opt-in |
| TUI has registry management | **Partial** | Can change URL, not multi-registry |

---

## 13. Recommended Phase Adjustments

Based on findings, the following adjustments to the phase plan are recommended:

### Phase 0: Complete ✅
All tasks completed. Research findings documented.

### Phase 1: Event Bus — No changes needed
Create `tokenade/core/events/` module as planned.

### Phase 2: Shared Context — No changes needed
Create `tokenade/core/context/` module as planned.

### Phase 3: Fix Wiring — Adjustments needed
- **Add:** Wire `ProxyManager.register_plugin()` to load plugins from `PluginLoader`
- **Add:** Create `PluginCaptchaSolver` adapter in `captcha.py`
- **Add:** Fix `_run_post_refresh_plugins` duck-typing
- **Note:** OAuth2Plugin conversion is straightforward (add inheritance)

### Phase 4: Registry System — Adjustments needed
- **Add:** Config file support (`~/.tokenade/config.json`)
- **Add:** Cache directory support (`~/.tokenade/cache/registries/`)

### Phase 5: Plugin Lifecycle — No changes needed
Implement lifecycle states and hooks as planned.

### Phase 6: Dependency Resolution — No changes needed
Implement dependency graph and resolver as planned.

### Phase 7: Plugin Config — No changes needed
Implement config manager and CLI as planned.

### Phase 8: Convert Handlers — No changes needed
Convert Google, GitHub, Generic OAuth handlers as planned.

### Phase 9: CLI Updates — Adjustments needed
- **Add:** `--no-plugin` flag to `launch`, `refresh-browser`, `accounts refresh`
- **Change:** `refresh-browser` and `accounts refresh` default to auto-discover
- **Add:** `tokenade plugin deps`, `check-deps`, `configure` commands
- **Add:** `tokenade registry` commands

### Phase 10: TUI Updates — Adjustments needed
- **Add:** Multi-registry management UI
- **Add:** Plugin health visualization
- **Add:** Plugin config visualization
- **Add:** Plugin task visualization

### Phase 11: Documentation — No changes needed
Write all documentation as planned.

---

## 14. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Breaking existing tests | High | Run full test suite before each commit |
| Breaking existing plugins | Medium | Backward compatible changes only |
| Event bus performance | Medium | Async handlers, thread pool, non-blocking |
| Shared context thread safety | Medium | Lock all operations |
| Dependency resolution complexity | Medium | Topological sort, depth limit, circular detection |
| Registry cache staleness | Low | TTL-based cache, manual refresh |
| Plugin security | Low | Trust model (user installs), no sandboxing |
| Documentation drift | Low | Documentation updated in Phase 11, tested |

---

## 15. Summary

**Phase 0 is complete.** All files have been read, all call sites identified, all design assumptions validated. The research findings document provides a comprehensive audit of the current codebase state.

**Key findings:**
1. Plugin system is architecturally complete but has a massive gap between "loaded" and "consumed"
2. 5 ad-hoc webhook implementations need to be unified into an event bus
3. 3 independent schedulers need to be unified behind a common interface
4. CLI default behavior varies by command and needs standardization
5. Several adapter patterns are needed (CaptchaPlugin→CaptchaSolver, StealthPlugin→StealthManager)
6. ProxyManager already has plugin hooks but they're not wired

**Ready to proceed with Phase 1: Event Bus Infrastructure.**
