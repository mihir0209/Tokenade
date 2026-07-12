# Phase 8: Convert Built-in Handlers to Plugins

**Objective:** Convert existing legacy handlers (Google, GitHub, generic OAuth) to plugin format. Make them work with the plugin system.

**Status:** NOT STARTED
**Dependencies:** Phase 3, Phase 5
**Blocks:** Phase 9

---

## Scope

### IN
- Convert `tokenade/handlers/google.py` to plugin format
- Convert `tokenade/handlers/github.py` to plugin format
- Convert `tokenade/handlers/generic_oauth.py` to plugin format
- Create plugin manifests for each handler
- Create site_config.json for each handler
- Add handlers to official registry
- Update legacy handler loading to use plugin system

### OUT
- No new site handlers
- No changes to handler logic (only format conversion)
- No TUI changes yet (Phase 10)

---

## Strict Rules

1. **Don't change handler logic** — Only convert format, don't modify behavior
2. **Backward compatible** — Legacy loading must still work
3. **Plugin format** — Each handler becomes a SiteHandlerPlugin
4. **Site config** — Each handler gets site_config.json
5. **Test everything** — All handler tests must pass
6. **No commits until tests pass**

---

## Detailed Tasks

### T8.1: Convert Google Handler
**Files:**
- `tokenade/handlers/google.py` → `~/.tokenade/plugins/google-handler/plugin.py`
- Create `~/.tokenade/plugins/google-handler/plugin.json`
- Create `~/.tokenade/plugins/google-handler/site_config.json`

**Changes:**
- Change class inheritance to `SiteHandlerPlugin`
- Add `API_VERSION = "1.0.0"`
- Add `on_load()`, `on_unload()` stubs
- Ensure methods match SiteHandlerPlugin interface

**Rules:**
- Don't change extraction/injection logic
- Don't change validation logic
- Keep all existing functionality
- Add plugin manifest and site config

### T8.2: Convert GitHub Handler
**Files:**
- `tokenade/handlers/github.py` → `~/.tokenade/plugins/github-handler/plugin.py`
- Create `~/.tokenade/plugins/github-handler/plugin.json`
- Create `~/.tokenade/plugins/github-handler/site_config.json`

**Changes:**
- Same as Google handler conversion

### T8.3: Convert Generic OAuth Handler
**Files:**
- `tokenade/handlers/generic_oauth.py` → `~/.tokenade/plugins/generic-oauth-handler/plugin.py`
- Create `~/.tokenade/plugins/generic-oauth-handler/plugin.json`
- Create `~/.tokenade/plugins/generic-oauth-handler/site_config.json`

**Changes:**
- Same as Google handler conversion

### T8.4: Update Legacy Handler Loading
**File:** `tokenade/core/importer/plugin_export.py`

**Changes:**
- Add fallback to legacy loading if plugin not found
- Log deprecation warning when legacy loading is used
- Don't break existing functionality

**Rules:**
- Legacy loading is deprecated but still works
- Plugins are preferred over legacy handlers
- Deprecation warning is logged

### T8.5: Add Handlers to Official Registry
**File:** `tokenade-plugins/plugins/` (external repo)

**Changes:**
- Add google-handler to official registry
- Add github-handler to official registry
- Add generic-oauth-handler to official registry

**Rules:**
- Handlers are in official registry
- Handlers are installable via `tokenade plugin install`
- Handlers are optional (core works without them)

### T8.6: Write Tests
**File:** `tests/test_handler_conversion.py`

**Test cases:**
- Google handler: plugin format works
- GitHub handler: plugin format works
- Generic OAuth handler: plugin format works
- Legacy loading: still works
- Plugin loading: works with new format
- All handler tests pass

---

## Files to Create

| File | Purpose |
|------|---------|
| `~/.tokenade/plugins/google-handler/plugin.json` | Google handler manifest |
| `~/.tokenade/plugins/google-handler/plugin.py` | Google handler plugin |
| `~/.tokenade/plugins/google-handler/site_config.json` | Google site config |
| `~/.tokenade/plugins/github-handler/plugin.json` | GitHub handler manifest |
| `~/.tokenade/plugins/github-handler/plugin.py` | GitHub handler plugin |
| `~/.tokenade/plugins/github-handler/site_config.json` | GitHub site config |
| `~/.tokenade/plugins/generic-oauth-handler/plugin.json` | Generic OAuth manifest |
| `~/.tokenade/plugins/generic-oauth-handler/plugin.py` | Generic OAuth plugin |
| `~/.tokenade/plugins/generic-oauth-handler/site_config.json` | Generic OAuth site config |
| `tests/test_handler_conversion.py` | Tests |

## Files to Modify

| File | Changes |
|------|---------|
| `tokenade/core/importer/plugin_export.py` | Add legacy fallback |

---

## Verification

- [ ] Google handler works in plugin format
- [ ] GitHub handler works in plugin format
- [ ] Generic OAuth handler works in plugin format
- [ ] Legacy loading still works
- [ ] Deprecation warning logged for legacy loading
- [ ] All handler tests pass
- [ ] All new tests pass
- [ ] No commits until all tests pass
