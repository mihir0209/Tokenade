# Phase 3: Fix Existing Plugin Wiring

**Objective:** Wire existing plugin infrastructure to actually work. on_configure(), health_check(), OAuth2Plugin→PluginBase, remove duplicates, wire getters into production code.

**Status:** NOT STARTED
**Dependencies:** Phase 1, Phase 2
**Blocks:** Phase 4, Phase 5, Phase 6

---

## Scope

### IN
- Wire `on_configure()` in plugin loader
- Wire `health_check()` in health reporter
- Convert `OAuth2Plugin` to inherit from `SessionRefreshPlugin`
- Remove duplicate `ProxyPlugin` (keep `ProxyProviderPlugin`)
- Remove duplicate `CaptchaPlugin` (unify with `CaptchaSolver`)
- Wire `get_exporter()` into export flow (if applicable)
- Wire `get_validator()` into validation flow (if applicable)
- Wire `get_refresher_for_session()` into auto-discovery
- Update all tests

### OUT
- No new plugin types
- No event bus integration yet (Phase 3 does wiring only)
- No shared context integration yet
- No CLI changes yet (Phase 9)

---

## Strict Rules

1. **Don't break existing tests** — All 5216 tests must still pass
2. **Minimal changes** — Only wire what's needed, don't refactor unnecessarily
3. **Backward compatible** — Old plugins must still work
4. **Test changes** — Add tests for new wiring
5. **No commits until tests pass**
6. **One change at a time** — Wire one thing, test, commit, then next

---

## Detailed Tasks

### T3.1: Wire on_configure() in Plugin Loader
**File:** `tokenade/core/integration/plugin_loader.py`

**Changes:**
- After loading plugin, check if `plugin.json` has `config` section
- If config exists, load user config from `~/.tokenade/plugins/<name>/config.json`
- Create `PluginConfig` from user config + schema
- Call `plugin.on_configure(config)`

**Rules:**
- If no config section in manifest, skip on_configure()
- If no user config file, skip on_configure()
- If config validation fails, log warning and skip on_configure()
- Don't crash on missing config

### T3.2: Wire health_check() in Health Reporter
**File:** `tokenade/core/health/health_reporter.py`

**Changes:**
- After loading plugins, call `plugin.health_check()` for each
- Store health status in shared context (Phase 2)
- Log unhealthy plugins
- Don't crash on health_check failure

**Rules:**
- Health check runs periodically (configurable interval)
- Health check is non-blocking (async if needed)
- Unhealthy plugins are logged, not removed
- Health status is available via CLI (`tokenade plugin info`)

### T3.3: Convert OAuth2Plugin to PluginBase
**File:** `tokenade/plugin/oauth2/plugin.py`

**Changes:**
- Make `OAuth2Plugin` inherit from `SessionRefreshPlugin`
- Add `API_VERSION = "1.0.0"`
- Add `on_load()`, `on_unload()` stubs
- Ensure `can_refresh()`, `refresh()`, `get_credentials_args()` match interface

**Rules:**
- Don't change OAuth2 functionality
- Don't break existing `--plugin oauth2` CLI flow
- Add tests for new inheritance
- Verify plugin can be loaded by PluginLoader

### T3.4: Remove Duplicate ProxyPlugin
**File:** `tokenade/plugin/base.py`

**Changes:**
- Remove `ProxyPlugin` class (lines 492-536)
- Keep `ProxyProviderPlugin` as the canonical proxy plugin type
- Update `PluginLoader` to only register `ProxyProviderPlugin`
- Update tests to remove `ProxyPlugin` references

**Rules:**
- Check if any code uses `ProxyPlugin` (should be none)
- Update all imports
- Don't break existing plugins (there shouldn't be any)

### T3.5: Unify CaptchaPlugin with CaptchaSolver
**Files:**
- `tokenade/plugin/base.py` — Keep `CaptchaPlugin`
- `tokenade/core/browser/captcha.py` — Add `PluginCaptchaSolver` adapter

**Changes:**
- Create `PluginCaptchaSolver` class in `captcha.py` that wraps `CaptchaPlugin`
- `PluginCaptchaSolver.solve()` delegates to `CaptchaPlugin.solve()`
- Register `PluginCaptchaSolver` in `CaptchaManager` when plugin is loaded
- Keep `CaptchaPlugin` interface as the plugin-facing API

**Rules:**
- Don't change `CaptchaSolver` interface (it's used by core)
- Don't change `CaptchaPlugin` interface (it's used by plugins)
- Bridge the two with adapter pattern
- Add tests for adapter

### T3.5b: Wire ProxyManager to PluginLoader
**File:** `tokenade/core/proxy/manager.py`

**Changes:**
- After loading plugins, inject `ProxyProviderPlugin` into `ProxyManager` instances
- `ProxyManager.register_plugin()` already exists (line 146) but is never called
- Wire `PluginLoader` to call `register_plugin()` when proxy plugins are loaded

**Rules:**
- Don't change `ProxyManager` interface
- Don't change `ProxyProviderPlugin` interface
- Just wire the existing hook
- Add tests for wiring

### T3.5c: Fix _run_post_refresh_plugins Duck-Typing
**File:** `tokenade/core/operations/session_ops.py`

**Changes:**
- Replace `hasattr(refresher, "_send_webhook")` duck-typing with proper type check
- Use `isinstance(refresher, NotificationPlugin)` or check `plugin_type` attribute
- Ensure only notification-type plugins are called in post-refresh

**Rules:**
- Don't break existing functionality
- Use proper type checking, not duck-typing
- Add tests for fix

### T3.6: Wire get_refresher_for_session() Auto-Discovery
**File:** `tokenade/core/integration/plugin_loader.py`

**Changes:**
- Implement `get_refresher_for_session(session)` logic:
  1. Get session domains from session data
  2. Find plugins that declare those domains
  3. Call `can_refresh(session)` on each
  4. Return first match (or None)

**Rules:**
- Auto-discovery is optional (user can still use `--plugin` flag)
- If no plugin found, return None (core handles refresh)
- Don't crash on missing session data
- Add tests for auto-discovery logic

### T3.7: Wire Shared Context Integration
**Files:**
- `tokenade/core/integration/plugin_loader.py`
- `tokenade/core/health/health_reporter.py`

**Changes:**
- Plugin loader registers plugins in shared context
- Health reporter stores health status in shared context
- Plugin config stored in shared context

**Rules:**
- Shared context is optional (system works without it)
- If shared context not available, skip integration
- Don't break existing functionality

### T3.8: Wire Event Bus Integration (Minimal)
**Files:**
- `tokenade/core/operations/session_ops.py`
- `tokenade/core/integration/plugin_loader.py`

**Changes:**
- Emit `plugin_loaded` event when plugin is loaded
- Emit `plugin_unloaded` event when plugin is unloaded
- Emit `plugin_error` event when plugin fails to load

**Rules:**
- Event bus is optional (system works without it)
- If event bus not available, skip emission
- Don't break existing functionality

### T3.9: Update Tests
**Files:**
- `tests/test_plugin_system.py`
- `tests/test_plugin_loader.py`
- `tests/test_plugin_api.py`
- New: `tests/test_plugin_wiring.py`

**Changes:**
- Update tests for on_configure() wiring
- Update tests for health_check() wiring
- Update tests for OAuth2Plugin inheritance
- Update tests for ProxyPlugin removal
- Update tests for CaptchaPlugin unification
- Add tests for auto-discovery
- Add tests for shared context integration
- Add tests for event bus integration

---

## Files to Modify

| File | Changes |
|------|---------|
| `tokenade/core/integration/plugin_loader.py` | Wire on_configure(), auto-discovery, shared context |
| `tokenade/core/health/health_reporter.py` | Wire health_check(), shared context |
| `tokenade/plugin/oauth2/plugin.py` | Convert to PluginBase subclass |
| `tokenade/plugin/base.py` | Remove ProxyPlugin |
| `tokenade/core/browser/captcha.py` | Add PluginCaptchaSolver adapter |
| `tokenade/core/operations/session_ops.py` | Emit events |
| `tests/test_plugin_system.py` | Update tests |
| `tests/test_plugin_loader.py` | Update tests |
| `tests/test_plugin_api.py` | Update tests |
| `tests/test_plugin_wiring.py` | New tests |

---

## Verification

- [ ] on_configure() is called when config exists
- [ ] health_check() is called periodically
- [ ] OAuth2Plugin inherits from SessionRefreshPlugin
- [ ] ProxyPlugin is removed
- [ ] CaptchaPlugin bridges to CaptchaSolver
- [ ] Auto-discovery finds refreshers for sessions
- [ ] Shared context integration works
- [ ] Event bus integration works
- [ ] All 5216 existing tests pass
- [ ] New tests pass
- [ ] No commits until all tests pass
