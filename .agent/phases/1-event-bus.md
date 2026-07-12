# Phase 1: Core Event Bus Infrastructure

**Objective:** Build the event bus as core infrastructure. Sync by default, async opt-in. Handles notifications, scheduler, session lifecycle, plugin communication.

**Status:** NOT STARTED
**Dependencies:** Phase 0
**Blocks:** Phase 2, Phase 3, Phase 4, Phase 5

---

## Scope

### IN
- Create `tokenade/core/events/` module
- Implement `EventType` enum
- Implement `Event` dataclass
- Implement `EventBus` class
- Implement `Scheduler` class (cron, health, expiry triggers)
- Implement base handler classes
- Implement dispatcher implementations
- Unit tests for all event bus components

### OUT
- No integration with existing code yet (Phase 3)
- No plugin hooks yet (Phase 4)
- No TUI integration (Phase 10)

---

## Strict Rules

1. **Core works without plugins** — Event bus must function with zero plugins installed
2. **Sync by default** — All event handlers are sync unless explicitly opted into async
3. **Non-blocking** — Async handlers run in background threads, don't block core flow
4. **No imports from plugin system** — Event bus is independent of `tokenade/plugin/`
5. **No config file changes** — Event bus uses programmatic configuration, not config files yet
6. **Test everything** — Every component has unit tests
7. **No commits until tests pass** — All tests must pass before committing

---

## Detailed Tasks

### T1.1: Create Module Structure
```
tokenade/core/events/
├── __init__.py          # Public API exports
├── types.py             # EventType enum, Event dataclass
├── bus.py               # EventBus implementation
├── scheduler.py         # Cron/scheduler integration
├── handlers.py          # Base handler classes
├── dispatchers.py       # Dispatcher implementations
└── triggers.py          # Trigger types (cron, health, expiry)
```

### T1.2: Implement types.py
```python
# EventType enum — all event types
# Event dataclass — event payload with metadata
# Priority enum — handler execution priority
```

**Rules:**
- EventType must be extensible (users can add custom events)
- Event must include: event_type, data, timestamp, source, id
- Priority must have numeric values for ordering

### T1.3: Implement bus.py
```python
class EventBus:
    def on(event_type, callback, priority=0, async_mode=False)
    def off(event_type, callback)
    def emit(event_type, data, source=None)
    def emit_sync(event_type, data, source=None)
    def emit_async(event_type, data, source=None)
    def get_listeners(event_type)
    def clear_listeners(event_type)
```

**Rules:**
- Default handler execution is sync (blocks until complete)
- Async handlers run in ThreadPoolExecutor (max_workers=4)
- Handler failures are caught and logged, never propagate
- Priority determines execution order (higher = runs first)
- Thread-safe (handlers can be registered from any thread)

### T1.4: Implement scheduler.py
```python
class Scheduler:
    def __init__(event_bus)
    def add_cron_task(name, event_type, data, cron_expr)
    def add_health_task(name, event_type, data, health_check_fn)
    def add_expiry_task(name, event_type, data, expiry_check_fn)
    def remove_task(name)
    def start()
    def stop()
    def get_tasks()
    def is_running()
```

**Rules:**
- Scheduler uses event bus to emit events
- Cron tasks use croniter library (if available) or simple interval fallback
- Health tasks poll health_check_fn at configurable interval
- Expiry tasks check expiry_check_fn at configurable interval
- Scheduler is non-blocking (runs in background thread)
- Tasks can be added/removed while scheduler is running

### T1.5: Implement triggers.py
```python
class Trigger(ABC):
    def should_fire() -> bool
    def reset()

class CronTrigger(Trigger):
    def __init__(cron_expr)

class HealthTrigger(Trigger):
    def __init__(health_check_fn, interval_seconds)

class ExpiryTrigger(Trigger):
    def __init__(expiry_check_fn, interval_seconds)

class IntervalTrigger(Trigger):
    def __init__(interval_seconds)
```

**Rules:**
- Each trigger type implements should_fire()
- Trigger state is reset after firing
- Triggers are independent of event bus

### T1.6: Implement handlers.py
```python
class EventHandler(ABC):
    def handle(event: Event)
    def get_priority() -> int

class SyncHandler(EventHandler):
    # Default — blocks until complete

class AsyncHandler(EventHandler):
    # Runs in background thread
```

**Rules:**
- All handlers inherit from EventHandler
- SyncHandler is the default
- AsyncHandler opts into background execution
- Handlers must be stateless (no side effects between calls)

### T1.7: Implement dispatchers.py
```python
class EventDispatcher:
    def dispatch(event: Event, handlers: List[EventHandler])
    def dispatch_sync(event: Event, handlers: List[EventHandler])
    def dispatch_async(event: Event, handlers: List[EventHandler])
```

**Rules:**
- Dispatchers execute handlers in priority order
- Sync dispatchers block until all handlers complete
- Async dispatchers submit handlers to thread pool
- Dispatchers catch and log handler failures

### T1.8: Implement __init__.py
Export public API:
- EventBus, Event, EventType, Priority
- Scheduler, Trigger, CronTrigger, HealthTrigger, ExpiryTrigger
- EventHandler, SyncHandler, AsyncHandler

### T1.9: Write Unit Tests
```
tests/test_event_bus.py
```

**Test cases:**
- EventBus: register, emit, priority ordering, thread safety
- EventBus: async handlers don't block
- EventBus: handler failures don't propagate
- EventBus: custom event types
- Scheduler: cron task fires
- Scheduler: health task fires when check returns True
- Scheduler: expiry task fires when check returns True
- Scheduler: tasks can be added/removed while running
- Triggers: should_fire() behavior
- Handlers: sync vs async execution
- Dispatchers: priority ordering, failure handling

---

## Files to Create

| File | Purpose |
|------|---------|
| `tokenade/core/events/__init__.py` | Public API |
| `tokenade/core/events/types.py` | EventType, Event, Priority |
| `tokenade/core/events/bus.py` | EventBus |
| `tokenade/core/events/scheduler.py` | Scheduler |
| `tokenade/core/events/handlers.py` | Handler base classes |
| `tokenade/core/events/dispatchers.py` | Dispatchers |
| `tokenade/core/events/triggers.py` | Trigger types |
| `tests/test_event_bus.py` | Unit tests |

---

## Verification

- [ ] All files created
- [ ] All unit tests pass
- [ ] EventBus works with zero plugins
- [ ] Sync handlers block as expected
- [ ] Async handlers don't block
- [ ] Scheduler fires cron tasks
- [ ] Scheduler fires health tasks
- [ ] Scheduler fires expiry tasks
- [ ] Priority ordering works
- [ ] Handler failures are logged, not propagated
- [ ] No imports from `tokenade/plugin/`
- [ ] No config file changes
- [ ] All tests pass before commit
