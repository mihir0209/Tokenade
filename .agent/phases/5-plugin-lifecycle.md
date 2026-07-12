# Phase 5: Plugin Lifecycle & Hooks

**Objective:** Implement complete plugin lifecycle with proper hooks. on_load(), on_configure(), on_unload(), health_check(), task state tracking.

**Status:** NOT STARTED
**Dependencies:** Phase 1, Phase 2, Phase 3
**Blocks:** Phase 6, Phase 7

---

## Scope

### IN
- Implement complete plugin lifecycle in loader
- Wire all lifecycle hooks (on_load, on_configure, on_unload)
- Implement plugin health monitoring
- Implement task state tracking for plugins
- Implement plugin error handling
- Unit tests for lifecycle

### OUT
- No new plugin types
- No CLI changes yet (Phase 9)
- No TUI changes yet (Phase 10)

---

## Strict Rules

1. **Lifecycle is deterministic** — Plugins go through states in order
2. **Hooks are called at right time** — on_load after loading, on_configure after config, on_unload before removal
3. **Health monitoring is non-blocking** — health_check() runs in background
4. **Task state is enforced** — Plugins can't skip states
5. **Error handling is graceful** — Plugin failures don't crash core
6. **Test everything** — Every lifecycle transition has tests
7. **No commits until tests pass**

---

## Detailed Tasks

### T5.1: Implement Plugin Lifecycle States
**File:** `tokenade/core/integration/plugin_loader.py`

**States:**
```
DISCOVERED → LOADED → CONFIGURED → ACTIVE → DISABLED → UNLOADED
                   ↓
                 FAILED
```

**Rules:**
- DISCOVERED: Plugin found in directory, not yet loaded
- LOADED: Module imported, class instantiated, on_load() called
- CONFIGURED: on_configure() called with config (if config exists)
- ACTIVE: Plugin is ready to use
- DISABLED: Plugin is disabled via `tokenade plugin disable`
- UNLOADED: Plugin is removed from registries, on_unload() called
- FAILED: Plugin failed to load (on_load() threw, config validation failed)

### T5.2: Implement Lifecycle Hooks
**File:** `tokenade/core/integration/plugin_loader.py`

**Changes:**
- Call `on_load()` immediately after instantiation
- Call `on_configure()` after loading if config exists
- Call `on_unload()` before removing from registries
- Track lifecycle state in shared context

**Rules:**
- on_load() is called once per load
- on_configure() is called once per config change
- on_unload() is called once per unload
- Hooks are called in order (on_load → on_configure → on_unload)
- Hook failures are caught and logged

### T5.3: Implement Plugin Health Monitoring
**File:** `tokenade/core/health/health_reporter.py`

**Changes:**
- Add plugin health checks to periodic health report
- Call `plugin.health_check()` for each loaded plugin
- Store health status in shared context
- Emit `health_check` event with results

**Rules:**
- Health checks run periodically (configurable, default 5 minutes)
- Health checks are non-blocking (async)
- Unhealthy plugins are logged, not removed
- Health status available via CLI and TUI

### T5.4: Implement Task State Tracking
**File:** `tokenade/core/context/tasks.py`

**Changes:**
- Track plugin tasks (start, update, complete, fail, abandon)
- Enforce state transitions (PENDING → IN_PROGRESS → COMPLETED/FAILED)
- Block invalid transitions (e.g., COMPLETED → IN_PROGRESS)
- Store task history in shared context

**Rules:**
- Tasks are created when plugin starts work
- Tasks are updated as plugin progresses
- Tasks are completed when work is done
- Tasks are failed on error
- Tasks are abandoned if plugin doesn't complete
- Core can query task state to enforce ordering

### T5.5: Implement Plugin Error Handling
**File:** `tokenade/core/integration/plugin_loader.py`

**Changes:**
- Catch exceptions during on_load(), on_configure(), on_unload()
- Log errors with full traceback
- Mark plugin as FAILED
- Emit `plugin_error` event
- Don't propagate exceptions to core

**Rules:**
- Plugin errors never crash core
- Plugin errors are logged with context
- Plugin errors are emitted as events
- Plugin state is updated to FAILED

### T5.6: Implement Plugin Reload
**File:** `tokenade/core/integration/plugin_loader.py`

**Changes:**
- Add `reload(name)` method
- Unload plugin, re-read manifest, re-load plugin
- Preserve plugin config across reload
- Emit `plugin_unloaded` and `plugin_loaded` events

**Rules:**
- Reload is manual (`tokenade plugin reload <name>`)
- Config is preserved across reload
- Reload is atomic (unload + load in one operation)
- Reload failure leaves plugin in previous state

### T5.7: Write Unit Tests
**File:** `tests/test_plugin_lifecycle.py`

**Test cases:**
- Lifecycle states: DISCOVERED → LOADED → CONFIGURED → ACTIVE
- Lifecycle states: ACTIVE → DISABLED → UNLOADED
- Lifecycle states: LOADED → FAILED (on_load throws)
- on_load() is called after instantiation
- on_configure() is called after load with config
- on_unload() is called before removal
- Health monitoring: health_check() called periodically
- Health monitoring: unhealthy plugins logged
- Task state: PENDING → IN_PROGRESS → COMPLETED
- Task state: PENDING → IN_PROGRESS → FAILED
- Task state: invalid transitions rejected
- Error handling: on_load failure caught
- Error handling: on_configure failure caught
- Error handling: on_unload failure caught
- Plugin reload: config preserved

---

## Files to Modify

| File | Changes |
|------|---------|
| `tokenade/core/integration/plugin_loader.py` | Lifecycle states, hooks, reload |
| `tokenade/core/health/health_reporter.py` | Plugin health checks |
| `tokenade/core/context/tasks.py` | Task state tracking |
| `tests/test_plugin_lifecycle.py` | New tests |

---

## Verification

- [ ] Plugin lifecycle states work correctly
- [ ] on_load() called after instantiation
- [ ] on_configure() called with config
- [ ] on_unload() called before removal
- [ ] Health monitoring runs periodically
- [ ] Unhealthy plugins are logged
- [ ] Task state tracking works
- [ ] Invalid state transitions rejected
- [ ] Plugin errors are caught and logged
- [ ] Plugin reload preserves config
- [ ] All tests pass
- [ ] No commits until all tests pass
