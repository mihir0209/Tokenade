# Phase 9: CLI Updates

**Objective:** Update CLI to support new plugin system. Default behavior: plugins run by default, `--no-plugin` flag to exclude. Update all plugin commands.

**Status:** NOT STARTED
**Dependencies:** Phase 3, Phase 4, Phase 5, Phase 6, Phase 7, Phase 8
**Blocks:** Phase 10

---

## Scope

### IN
- Update `--plugin` flag to be optional (default: use plugins)
- Add `--no-plugin` flag to exclude plugins
- Update all plugin CLI commands
- Update export commands to use plugins by default
- Update refresh commands to use plugins by default
- Add plugin test command
- Add plugin reload command
- Add plugin deps command
- Add plugin check-deps command
- Add plugin configure command
- Unit tests for all CLI changes

### OUT
- No TUI changes yet (Phase 10)
- No new plugin types

---

## Strict Rules

1. **Plugins run by default** — No flag needed to use plugins
2. **`--no-plugin` flag** — Excludes plugins from operation
3. **Backward compatible** — `--plugin` flag still works (explicit selection)
4. **All commands updated** — Every plugin-related command works with new system
5. **Test everything** — Every CLI command has tests
6. **No commits until tests pass**

---

## Detailed Tasks

### T9.1: Update Export Commands
**File:** `tokenade/cli/session_export.py`

**Changes:**
- Default: Use plugins if available (already correct)
- `--plugin <name>`: Use specific plugin (explicit)
- `--no-plugin`: Don't use plugins (exclude)
- Auto-discovery: Find handler by domain

**Rules:**
- Default behavior: auto-discover handler by domain
- `--plugin`: Explicitly select plugin (override auto-discovery)
- `--no-plugin`: Disable plugin usage entirely
- Fallback: If no plugin found, use core export

### T9.1b: Update Refresh Commands (Critical Change)
**File:** `tokenade/cli/handlers/browser_ops.py`

**Changes:**
- **Current:** Plugin only runs if `--plugin` explicitly passed (opt-in)
- **New:** Default: auto-discover refresher via `loader.get_refresher_for_session(session)`
- `--plugin <name>`: Force specific plugin (override auto-discovery)
- `--no-plugin`: Skip plugin refresh entirely (browser-based only)

**Rules:**
- Default behavior: auto-discover refresher for session
- `--plugin`: Explicitly select plugin (override auto-discovery)
- `--no-plugin`: Disable plugin usage entirely
- Fallback: If no plugin found, use browser-based refresh
- **This is the critical behavior change from opt-in to opt-out**

### T9.1c: Add --no-plugin to Launch Command
**File:** `tokenade/cli/handlers/browser_ops.py`

**Changes:**
- Add `--no-plugin` flag to `launch` parser
- Current auto-discovery behavior is correct for "plugins run by default"
- Just add the opt-out flag

**Rules:**
- Default behavior: auto-discover handler (already correct)
- `--plugin`: Force specific plugin (already works)
- `--no-plugin`: Skip plugin, use default launch

### T9.2: Update Refresh Commands
**File:** `tokenade/cli/handlers/browser_ops.py`

**Changes:**
- Default: Use plugins if available
- `--plugin <name>`: Use specific plugin (explicit)
- `--no-plugin`: Don't use plugins (exclude)
- Auto-discovery: Find refresher for session

**Rules:**
- Default behavior: auto-discover refresher for session
- `--plugin`: Explicitly select plugin (override auto-discovery)
- `--no-plugin`: Disable plugin usage entirely
- Fallback: If no plugin found, use core refresh

### T9.3: Update Plugin List Command
**File:** `tokenade/cli/__init__.py`

**Changes:**
- Show plugin lifecycle state (LOADED, CONFIGURED, ACTIVE, etc.)
- Show plugin health status
- Show plugin config status
- Show dependency status

**Rules:**
- List shows: name, version, type, state, health, config, dependencies
- Filter by type, state, health
- Sort by name, version, state

### T9.4: Update Plugin Info Command
**File:** `tokenade/cli/__init__.py`

**Changes:**
- Show full plugin metadata
- Show plugin config
- Show plugin health history
- Show plugin dependencies
- Show plugin task history

**Rules:**
- Info shows: metadata, config, health, dependencies, tasks
- JSON output option
- Verbose option for full details

### T9.5: Add Plugin Test Command
**File:** `tokenade/cli/__init__.py`

**Changes:**
- Run contract tests for plugin
- Show test results
- Support `--verbose` flag

**Rules:**
- Test runs 8 contract tests
- Show pass/fail for each test
- Show summary

### T9.6: Add Plugin Reload Command
**File:** `tokenade/cli/__init__.py`

**Changes:**
- Unload plugin, re-read manifest, re-load plugin
- Preserve config across reload
- Show reload status

**Rules:**
- Reload is atomic (unload + load)
- Config is preserved
- Reload failure leaves plugin in previous state

### T9.7: Add Plugin Deps Command
**File:** `tokenade/cli/__init__.py`

**Changes:**
- Show dependency tree for plugin
- Show depth
- Show circular dependencies (if any)

**Rules:**
- Tree is indented
- Depth is shown
- Circular dependencies are highlighted

### T9.8: Add Plugin Check-Deps Command
**File:** `tokenade/cli/__init__.py`

**Changes:**
- Check for missing dependencies
- Check for circular dependencies
- Check for depth limit violations

**Rules:**
- Missing dependencies are listed
- Circular dependencies are listed
- Depth violations are listed

### T9.9: Add Plugin Configure Command
**File:** `tokenade/cli/__init__.py`

**Changes:**
- `--set key=value`: Set config values
- `--show`: Show current config
- `--reset`: Reset to defaults
- `--validate`: Validate config against schema

**Rules:**
- Config is stored in plugin directory
- Config is validated against schema
- Config is passed to plugin via on_configure()

### T9.10: Write Unit Tests
**File:** `tests/test_cli_plugins.py`

**Test cases:**
- Export: default uses plugins
- Export: --plugin flag
- Export: --no-plugin flag
- Refresh: default uses plugins
- Refresh: --plugin flag
- Refresh: --no-plugin flag
- Plugin list: shows state, health, config
- Plugin info: shows full metadata
- Plugin test: runs contract tests
- Plugin reload: config preserved
- Plugin deps: shows tree
- Plugin check-deps: shows missing
- Plugin configure: --set, --show, --reset, --validate

---

## Files to Modify

| File | Changes |
|------|---------|
| `tokenade/cli/session_export.py` | Update export commands |
| `tokenade/cli/handlers/browser_ops.py` | Update refresh commands |
| `tokenade/cli/__init__.py` | Update/add plugin commands |
| `tests/test_cli_plugins.py` | New tests |

---

## Verification

- [ ] Export: plugins run by default
- [ ] Export: --plugin flag works
- [ ] Export: --no-plugin flag works
- [ ] Refresh: plugins run by default
- [ ] Refresh: --plugin flag works
- [ ] Refresh: --no-plugin flag works
- [ ] Plugin list: shows all info
- [ ] Plugin info: shows full metadata
- [ ] Plugin test: runs contract tests
- [ ] Plugin reload: config preserved
- [ ] Plugin deps: shows tree
- [ ] Plugin check-deps: shows missing
- [ ] Plugin configure: works correctly
- [ ] All tests pass
- [ ] No commits until all tests pass
