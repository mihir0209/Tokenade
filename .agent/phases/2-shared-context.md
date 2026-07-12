# Phase 2: Shared Context Module

**Objective:** Build the shared context that plugins read/write through. Core owns it. 4 namespaces: Sessions, Plugins, Config, Runtime.

**Status:** NOT STARTED
**Dependencies:** Phase 0
**Blocks:** Phase 3, Phase 4, Phase 5

---

## Scope

### IN
- Create `tokenade/core/context/` module
- Implement `SharedContext` class
- Implement namespace classes (Sessions, Plugins, Config, Runtime)
- Implement task state tracking (for plugin enforcement)
- Unit tests for all context components

### OUT
- No integration with existing code yet (Phase 3)
- No plugin integration yet (Phase 4)
- No event bus integration yet (Phase 3)

---

## Strict Rules

1. **Core owns context** — Context is created and managed by core, not plugins
2. **Plugins read/write through context** — Plugins access context via provided API, not direct access
3. **Thread-safe** — Context must be safe for concurrent access
4. **No plugin imports** — Context is independent of `tokenade/plugin/`
5. **No config file changes** — Context uses programmatic configuration
6. **Test everything** — Every component has unit tests
7. **No commits until tests pass**

---

## Detailed Tasks

### T2.1: Create Module Structure
```
tokenade/core/context/
├── __init__.py          # Public API exports
├── context.py           # SharedContext implementation
├── sessions.py          # Sessions namespace
├── plugins.py           # Plugins namespace
├── config.py            # Config namespace
├── runtime.py           # Runtime namespace
└── tasks.py             # Task state tracking
```

### T2.2: Implement context.py
```python
class SharedContext:
    def __init__()
    @property
    def sessions() -> SessionsNamespace
    @property
    def plugins() -> PluginsNamespace
    @property
    def config() -> ConfigNamespace
    @property
    def runtime() -> RuntimeNamespace
    def get_namespace(name) -> Namespace
    def list_namespaces() -> List[str]
```

**Rules:**
- Context is a singleton (one instance per application)
- Namespaces are accessed via properties
- Thread-safe (all operations are locked)
- No plugin access to internal state

### T2.3: Implement sessions.py
```python
class SessionsNamespace:
    def get(session_id) -> Optional[Dict]
    def set(session_id, data)
    def delete(session_id)
    def list() -> List[str]
    def exists(session_id) -> bool
    def get_health(session_id) -> Optional[float]
    def set_health(session_id, score)
    def get_metadata(session_id) -> Dict
    def set_metadata(session_id, metadata)
```

**Rules:**
- Session data is stored as Dict
- Health scores are float 0-100
- Metadata includes: site, created_at, updated_at, source
- Thread-safe operations

### T2.4: Implement plugins.py
```python
class PluginsNamespace:
    def register(name, plugin_info)
    def unregister(name)
    def get(name) -> Optional[Dict]
    def list() -> List[str]
    def is_loaded(name) -> bool
    def set_config(name, config)
    def get_config(name) -> Dict
    def set_health(name, healthy)
    def get_health(name) -> bool
    def set_version(name, version)
    def get_version(name) -> str
```

**Rules:**
- Plugin info includes: name, version, type, enabled, loaded_at
- Config is plugin-specific dictionary
- Health is boolean (healthy/unhealthy)
- Thread-safe operations

### T2.5: Implement config.py
```python
class ConfigNamespace:
    def get(key, default=None)
    def set(key, value)
    def delete(key)
    def list() -> List[str]
    def exists(key) -> bool
    def get_registry_url() -> str
    def set_registry_url(url)
    def get_notification_settings() -> Dict
    def set_notification_settings(settings)
    def get_scheduler_settings() -> Dict
    def set_scheduler_settings(settings)
```

**Rules:**
- Config stores user preferences
- Includes registry URL, notification settings, scheduler settings
- Thread-safe operations
- No config file I/O in this phase (Phase 7)

### T2.6: Implement runtime.py
```python
class RuntimeNamespace:
    def get_active_proxy() -> Optional[Dict]
    def set_active_proxy(proxy)
    def get_solved_captcha(captcha_id) -> Optional[Dict]
    def set_solved_captcha(captcha_id, solution)
    def get_refresh_timestamp(session_id) -> Optional[datetime]
    def set_refresh_timestamp(session_id, timestamp)
    def get_task_state(task_id) -> Optional[TaskState]
    def set_task_state(task_id, state)
    def list_active_tasks() -> List[str]
```

**Rules:**
- Runtime stores transient state
- Active proxy is the currently used proxy
- Solved CAPTCHAs are cached with expiry
- Refresh timestamps track when sessions were last refreshed
- Task state tracks plugin task lifecycle
- Thread-safe operations

### T2.7: Implement tasks.py
```python
class TaskState(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class TaskTracker:
    def start_task(task_id, plugin_name, task_type)
    def update_task(task_id, state, result=None)
    def get_task(task_id) -> Optional[Dict]
    def list_tasks(plugin_name=None) -> List[Dict]
    def abandon_task(task_id)
    def is_task_active(task_id) -> bool
```

**Rules:**
- Task states: PENDING → IN_PROGRESS → COMPLETED/FAILED
- Task info includes: id, plugin_name, task_type, state, created_at, updated_at, result
- Abandoned tasks are marked FAILED
- Active tasks are IN_PROGRESS
- Thread-safe operations

### T2.8: Implement __init__.py
Export public API:
- SharedContext
- SessionsNamespace, PluginsNamespace, ConfigNamespace, RuntimeNamespace
- TaskState, TaskTracker

### T2.9: Write Unit Tests
```
tests/test_shared_context.py
```

**Test cases:**
- SharedContext: namespace access, singleton behavior
- SessionsNamespace: CRUD operations, health, metadata
- PluginsNamespace: register/unregister, config, health
- ConfigNamespace: get/set/delete, registry URL, notification settings
- RuntimeNamespace: active proxy, solved CAPTCHAs, refresh timestamps
- TaskTracker: state transitions, abandon, active tasks
- Thread safety: concurrent access from multiple threads
- Task state enforcement: invalid state transitions rejected

---

## Files to Create

| File | Purpose |
|------|---------|
| `tokenade/core/context/__init__.py` | Public API |
| `tokenade/core/context/context.py` | SharedContext |
| `tokenade/core/context/sessions.py` | Sessions namespace |
| `tokenade/core/context/plugins.py` | Plugins namespace |
| `tokenade/core/context/config.py` | Config namespace |
| `tokenade/core/context/runtime.py` | Runtime namespace |
| `tokenade/core/context/tasks.py` | Task state tracking |
| `tests/test_shared_context.py` | Unit tests |

---

## Verification

- [ ] All files created
- [ ] All unit tests pass
- [ ] SharedContext works as singleton
- [ ] All namespaces support CRUD operations
- [ ] Task state tracking works
- [ ] Invalid state transitions are rejected
- [ ] Thread safety verified
- [ ] No imports from `tokenade/plugin/`
- [ ] No config file changes
- [ ] All tests pass before commit
