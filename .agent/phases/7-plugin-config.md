# Phase 7: Plugin Configuration System

**Objective:** Implement plugin configuration system. Schema validation, user config storage, on_configure() wiring, CLI for configuration.

**Status:** NOT STARTED
**Dependencies:** Phase 2, Phase 5
**Blocks:** Phase 9

---

## Scope

### IN
- Implement plugin config schema validation
- Implement user config storage (`~/.tokenade/plugins/<name>/config.json`)
- Implement config CLI commands
- Wire on_configure() to config loading
- Unit tests for configuration

### OUT
- No TUI integration yet (Phase 10)
- No global config changes yet

---

## Strict Rules

1. **Schema validation** — Config must match plugin's declared schema
2. **User config in plugin directory** — Config stored in `~/.tokenade/plugins/<name>/config.json`
3. **Global config in core config** — Global settings in `~/.tokenade/config.json`
4. **on_configure() wiring** — Config loaded and passed to plugin on load
5. **CLI for configuration** — `tokenade plugin configure` command
6. **Test everything** — Every config scenario has tests
7. **No commits until tests pass**

---

## Detailed Tasks

### T7.1: Implement Config Schema
**File:** `tokenade/plugin/api.py`

**Changes:**
- Extend `PluginConfigSchema` to support more types
- Add `min`, `max`, `pattern` constraints
- Add `env_var` support (read from environment)

**Rules:**
- Supported types: string, int, float, bool, list, dict
- Constraints: min, max, pattern, choices
- env_var: Read from environment variable if set
- Schema is optional (plugins without config don't need it)

### T7.2: Implement User Config Storage
**File:** `tokenade/core/integration/plugin_config.py`

```python
class PluginConfigManager:
    def __init__(plugins_dir="~/.tokenade/plugins")
    def load_config(plugin_name) -> Dict
    def save_config(plugin_name, config)
    def delete_config(plugin_name)
    def has_config(plugin_name) -> bool
    def validate_config(plugin_name, config) -> List[str]
    def get_schema(plugin_name) -> Dict
```

**Rules:**
- Config stored in `~/.tokenade/plugins/<name>/config.json`
- Config is JSON format
- Config is validated against schema on save
- Config is optional (plugins can work without config)

### T7.3: Implement Config CLI Commands
**File:** `tokenade/cli/__init__.py`

**New commands:**
```bash
tokenade plugin configure <name> --set key=value [key=value ...]
tokenade plugin configure <name> --show
tokenade plugin configure <name> --reset
tokenade plugin configure <name> --validate
```

**Rules:**
- `--set` sets config values (multiple key=value pairs)
- `--show` displays current config
- `--reset` resets to defaults (deletes config file)
- `--validate` validates config against schema

### T7.4: Wire on_configure() to Config Loading
**File:** `tokenade/core/integration/plugin_loader.py`

**Changes:**
- After loading plugin, check if plugin has config schema
- If schema exists, load user config
- Validate config against schema
- Create PluginConfig instance
- Call `plugin.on_configure(config)`

**Rules:**
- Config loading is optional (plugins without schema skip it)
- Config validation failures are logged, plugin still loads
- Config is passed as PluginConfig instance
- Config is stored in shared context

### T7.5: Implement Global Config Integration
**File:** `tokenade/core/integration/plugin_config.py`

**Changes:**
- Read global settings from `~/.tokenade/config.json`
- Merge global settings with plugin-specific config
- Global settings override plugin defaults

**Rules:**
- Global settings are under `plugins` key
- Plugin-specific config overrides global settings
- Global settings are optional

### T7.6: Write Unit Tests
**File:** `tests/test_plugin_config.py`

**Test cases:**
- Config schema: validation with types
- Config schema: constraints (min, max, pattern)
- Config schema: env_var support
- User config: load/save/delete
- User config: validation against schema
- Config CLI: --set, --show, --reset, --validate
- on_configure(): called with config
- on_configure(): skipped without schema
- Global config: merged with plugin config
- Edge cases: missing config, invalid config, empty config

---

## Files to Create

| File | Purpose |
|------|---------|
| `tokenade/core/integration/plugin_config.py` | PluginConfigManager |
| `tests/test_plugin_config.py` | Unit tests |

## Files to Modify

| File | Changes |
|------|---------|
| `tokenade/plugin/api.py` | Extend PluginConfigSchema |
| `tokenade/cli/__init__.py` | Add configure commands |
| `tokenade/core/integration/plugin_loader.py` | Wire on_configure() |

---

## Verification

- [ ] Config schema validation works
- [ ] User config storage works
- [ ] Config CLI commands work
- [ ] on_configure() called with config
- [ ] Config skipped without schema
- [ ] Global config merged correctly
- [ ] All tests pass
- [ ] No commits until all tests pass
