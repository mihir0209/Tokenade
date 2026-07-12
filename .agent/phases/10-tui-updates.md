# Phase 10: TUI Updates

**Objective:** Update TUI to support new plugin system. Registry management through TUI. Plugin lifecycle visualization.

**Status:** NOT STARTED
**Dependencies:** Phase 4, Phase 5, Phase 9
**Blocks:** None

---

## Scope

### IN
- Update TUI plugin screens for new lifecycle
- Add registry management to TUI
- Add plugin health visualization
- Add plugin config visualization
- Add plugin task visualization
- Future: Analytics, sessions UI (deferred)

### OUT
- No new plugin types
- No analytics yet (future)
- No sessions UI yet (future)

---

## Strict Rules

1. **TUI is primary for registry management** — CLI is secondary
2. **Registry management through TUI** — Add/remove/enable/disable registries
3. **Plugin lifecycle visualization** — Show state, health, config, tasks
4. **Responsive** — TUI must be responsive to user input
5. **Test everything** — Every TUI screen has tests
6. **No commits until tests pass**

---

## Detailed Tasks

### T10.1: Update MarketplaceView
**File:** `tokenade/tui/app.py`

**Changes:**
- Show plugin lifecycle state
- Show plugin health status
- Show plugin config status
- Show dependency status

**Rules:**
- Marketplace shows: name, version, type, state, health, config, dependencies
- Filter by type, state, health
- Sort by name, version, state

### T10.2: Update InstalledView
**File:** `tokenade/tui/app.py`

**Changes:**
- Show installed plugins with lifecycle state
- Show health status
- Show config status
- Show task history

**Rules:**
- Installed shows: name, version, type, state, health, config, tasks
- Can enable/disable plugins
- Can configure plugins
- Can reload plugins

### T10.3: Update PluginDetailScreen
**File:** `tokenade/tui/app.py`

**Changes:**
- Show full plugin metadata
- Show plugin config
- Show plugin health history
- Show plugin dependencies
- Show plugin task history

**Rules:**
- Detail shows: metadata, config, health, dependencies, tasks
- Can install/uninstall
- Can enable/disable
- Can configure
- Can reload

### T10.4: Add Registry Management Screen
**File:** `tokenade/tui/app.py`

**New screen:**
```
Registry Management
├── Official Registry (priority 1, enabled)
├── Community Registry (priority 2, enabled)
└── My Registry (priority 3, disabled)

Actions:
- Add Registry
- Remove Registry
- Enable/Disable Registry
- Set Priority
- Refresh Cache
```

**Rules:**
- Registry management is primary through TUI
- Can add/remove registries
- Can enable/disable registries
- Can set priority
- Can refresh cache

### T10.5: Add Plugin Health Visualization
**File:** `tokenade/tui/app.py`

**New widget:**
```
Plugin Health
├── google-handler: Healthy (last checked: 5m ago)
├── email-notifier: Unhealthy (error: SMTP connection failed)
└── oauth2-plugin: Healthy (last checked: 2m ago)
```

**Rules:**
- Health status is shown for each plugin
- Last checked time is shown
- Error messages are shown for unhealthy plugins
- Health refreshes periodically

### T10.6: Add Plugin Config Visualization
**File:** `tokenade/tui/app.py`

**New widget:**
```
Plugin Configuration
├── google-handler:
│   ├── client_id: [redacted]
│   └── timeout: 30
├── email-notifier:
│   ├── smtp_host: smtp.gmail.com
│   ├── smtp_port: 587
│   └── [encrypted]
└── oauth2-plugin:
    └── [no configuration]
```

**Rules:**
- Config is shown for each plugin
- Sensitive values are redacted
- Encrypted values show [encrypted]
- Can edit config through TUI

### T10.7: Add Plugin Task Visualization
**File:** `tokenade/tui/app.py`

**New widget:**
```
Active Tasks
├── google-handler: Extracting session (started: 2m ago)
├── email-notifier: Sending notification (started: 30s ago)
└── oauth2-plugin: Refreshing token (started: 1m ago)

Recent Tasks
├── google-handler: Session extracted (completed: 5m ago)
├── email-notifier: Notification sent (completed: 3m ago)
└── oauth2-plugin: Token refreshed (completed: 2m ago)
```

**Rules:**
- Active tasks are shown with start time
- Recent tasks are shown with completion time
- Failed tasks are shown with error
- Tasks refresh periodically

### T10.8: Write Tests
**File:** `tests/test_tui_plugins.py`

**Test cases:**
- MarketplaceView: shows plugin state, health, config
- InstalledView: shows installed plugins
- PluginDetailScreen: shows full metadata
- Registry Management: add/remove/enable/disable
- Plugin Health: visualization works
- Plugin Config: visualization works
- Plugin Task: visualization works

---

## Files to Modify

| File | Changes |
|------|---------|
| `tokenade/tui/app.py` | Update/add TUI screens |
| `tests/test_tui_plugins.py` | New tests |

---

## Verification

- [ ] MarketplaceView shows plugin state, health, config
- [ ] InstalledView shows installed plugins
- [ ] PluginDetailScreen shows full metadata
- [ ] Registry Management works
- [ ] Plugin Health visualization works
- [ ] Plugin Config visualization works
- [ ] Plugin Task visualization works
- [ ] All tests pass
- [ ] No commits until all tests pass
