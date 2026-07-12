# Phase 4: Plugin Registry System

**Objective:** Build multiple registry support with priority ordering. Latest version wins, `--registry` flag to override. Primary management through TUI.

**Status:** NOT STARTED
**Dependencies:** Phase 0
**Blocks:** Phase 7, Phase 9

---

## Scope

### IN
- Implement `RegistryManager` class
- Implement registry configuration in `~/.tokenade/config.json`
- Implement multiple registry support with priority
- Implement registry CLI commands
- Implement registry caching
- Unit tests for registry system

### OUT
- No TUI integration yet (Phase 10)
- No plugin installation yet (existing registry handles that)
- No plugin discovery yet (existing registry handles that)

---

## Strict Rules

1. **Latest version wins** — When same plugin exists in multiple registries, latest version is default
2. **`--registry` flag** — User can override with `--registry <name>` flag
3. **Priority ordering** — Registries checked in priority order (lower number = higher priority)
4. **Cache with TTL** — Registry data cached with configurable TTL (default 1 hour)
5. **No breaking changes** — Existing registry functionality must still work
6. **Test everything** — Every component has unit tests
7. **No commits until tests pass**

---

## Detailed Tasks

### T4.1: Implement RegistryManager
**File:** `tokenade/core/integration/registry_manager.py`

```python
class RegistryManager:
    def __init__(config_path="~/.tokenade/config.json")
    def add_registry(url, name, priority=None, enabled=True)
    def remove_registry(name)
    def enable_registry(name)
    def disable_registry(name)
    def set_priority(name, priority)
    def list_registries() -> List[Dict]
    def get_registry(name) -> Optional[Dict]
    def search(query, plugin_type=None, category=None, registry_name=None)
    def get_plugin(name, registry_name=None)
    def install_plugin(name, registry_name=None)
    def _load_config()
    def _save_config()
    def _fetch_registry(registry)
    def _merge_results(results)
```

**Rules:**
- Config stored in `~/.tokenade/config.json` under `registries` key
- Each registry entry: `{url, name, priority, enabled, last_fetched, cache_ttl}`
- Search merges results from all enabled registries
- Latest version wins on conflict
- `registry_name` parameter overrides priority ordering
- Cache TTL defaults to 3600 seconds (1 hour)

### T4.2: Implement Registry Configuration
**File:** `~/.tokenade/config.json`

**Structure:**
```json
{
  "registries": [
    {
      "url": "https://raw.githubusercontent.com/mihir0209/tokenade-plugins/main",
      "name": "official",
      "priority": 1,
      "enabled": true,
      "last_fetched": null,
      "cache_ttl": 3600
    }
  ],
  "plugins": {},
  "notifications": {},
  "scheduler": {}
}
```

**Rules:**
- Official registry is default (priority 1)
- User can add more registries
- Disabled registries are skipped in search
- Cache is per-registry

### T4.3: Implement Registry Cache
**File:** `tokenade/core/integration/registry_cache.py`

```python
class RegistryCache:
    def __init__(cache_dir="~/.tokenade/cache/registries")
    def get(registry_url) -> Optional[Dict]
    def set(registry_url, data, ttl=3600)
    def invalidate(registry_url)
    def clear()
    def is_valid(registry_url) -> bool
```

**Rules:**
- Cache stored in `~/.tokenade/cache/registries/`
- Cache keyed by registry URL (hashed)
- Cache expires after TTL
- Manual invalidation supported

### T4.4: Implement Registry CLI Commands
**File:** `tokenade/cli/__init__.py`

**New commands:**
```bash
tokenade registry list                          # List all registries
tokenade registry add <url> [--name NAME] [--priority N]
tokenade registry remove <name>
tokenade registry enable <name>
tokenade registry disable <name>
tokenade registry priority <name> <N>
tokenade registry refresh [name]                # Force refresh cache
```

**Rules:**
- `list` shows name, URL, priority, enabled, last_fetched
- `add` auto-generates name if not provided
- `remove` confirms before removing
- `enable`/`disable` toggle enabled flag
- `priority` sets priority (lower = higher priority)
- `refresh` clears cache and re-fetches

### T4.5: Update Existing Registry Integration
**File:** `tokenade/core/integration/plugin_registry.py`

**Changes:**
- Add `registry_name` parameter to search/install methods
- Add `priority` parameter to search results
- Add `registry` field to plugin metadata
- Don't break existing API (backward compatible)

**Rules:**
- Existing code continues to work with default registry
- New parameters are optional
- Search results include registry source

### T4.6: Write Unit Tests
**File:** `tests/test_registry_manager.py`

**Test cases:**
- RegistryManager: add/remove registries
- RegistryManager: enable/disable registries
- RegistryManager: set priority
- RegistryManager: search across registries
- RegistryManager: latest version wins
- RegistryManager: --registry flag override
- RegistryCache: get/set/invalidate
- RegistryCache: TTL expiration
- Registry CLI: all commands
- Backward compatibility: existing registry code works

---

## Files to Create

| File | Purpose |
|------|---------|
| `tokenade/core/integration/registry_manager.py` | RegistryManager |
| `tokenade/core/integration/registry_cache.py` | RegistryCache |
| `tests/test_registry_manager.py` | Unit tests |

## Files to Modify

| File | Changes |
|------|---------|
| `tokenade/core/integration/plugin_registry.py` | Add registry_name, priority params |
| `tokenade/cli/__init__.py` | Add registry commands |

---

## Verification

- [ ] RegistryManager can add/remove registries
- [ ] RegistryManager can enable/disable registries
- [ ] RegistryManager can set priority
- [ ] Search merges results from multiple registries
- [ ] Latest version wins on conflict
- [ ] --registry flag overrides priority
- [ ] Cache works with TTL
- [ ] Cache invalidation works
- [ ] CLI commands work
- [ ] Existing registry code still works
- [ ] All tests pass
- [ ] No commits until all tests pass
