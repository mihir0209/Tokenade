# Tokenade Plugin Ecosystem — Implementation Phases

**Date:** 2026-07-12
**Status:** Planning complete, ready for implementation
**Design doc:** `.agent/plans/plugin-ecosystem-design.md`
**Grilling decisions:** `.agent/plans/plugin-ecosystem-design.md` (Section 15)

---

## Phase Overview

| Phase | Name | Dependencies | Blocks | Status |
|-------|------|-------------|--------|--------|
| 0 | Pre-Planning & Research | None | All | NOT STARTED |
| 1 | Core Event Bus Infrastructure | Phase 0 | 2, 3, 4, 5 | NOT STARTED |
| 2 | Shared Context Module | Phase 0 | 3, 4, 5 | NOT STARTED |
| 3 | Fix Existing Plugin Wiring | 1, 2 | 4, 5, 6 | NOT STARTED |
| 4 | Plugin Registry System | Phase 0 | 7, 9 | NOT STARTED |
| 5 | Plugin Lifecycle & Hooks | 1, 2, 3 | 6, 7 | NOT STARTED |
| 6 | Dependency Resolution | 4, 5 | 7 | NOT STARTED |
| 7 | Plugin Configuration System | 2, 5 | 9 | NOT STARTED |
| 8 | Convert Built-in Handlers | 3, 5 | 9 | NOT STARTED |
| 9 | CLI Updates | 3, 4, 5, 6, 7, 8 | 10 | NOT STARTED |
| 10 | TUI Updates | 4, 5, 9 | None | NOT STARTED |
| 11 | Documentation & Polish | All | None | NOT STARTED |

---

## Dependency Graph

```
Phase 0 (Pre-Planning)
├── Phase 1 (Event Bus)
│   ├── Phase 3 (Fix Wiring)
│   │   ├── Phase 5 (Lifecycle)
│   │   │   ├── Phase 6 (Dependencies)
│   │   │   │   └── Phase 7 (Config)
│   │   │   └── Phase 8 (Convert Handlers)
│   │   └── Phase 4 (Registry)
│   └── Phase 2 (Shared Context)
└── Phase 4 (Registry)
    └── Phase 7 (Config)

Phase 9 (CLI Updates) ← depends on 3, 4, 5, 6, 7, 8
Phase 10 (TUI Updates) ← depends on 4, 5, 9
Phase 11 (Documentation) ← depends on all
```

---

## Execution Order

**Parallel tracks (can be done simultaneously):**

| Track | Phases | Description |
|-------|--------|-------------|
| A | 0 → 1 → 2 | Core infrastructure (event bus + context) |
| B | 0 → 4 | Registry system |

**Sequential (must be done in order):**

| Sequence | Phases | Description |
|----------|--------|-------------|
| 1 | 0 | Pre-planning (both tracks start here) |
| 2 | 1, 2, 4 | Core infrastructure (parallel) |
| 3 | 3 | Fix wiring (needs 1, 2) |
| 4 | 5, 6, 7, 8 | Plugin system (needs 3) |
| 5 | 9 | CLI updates (needs all above) |
| 6 | 10 | TUI updates (needs 9) |
| 7 | 11 | Documentation (needs all) |

---

## Strict Rules (From Grilling Session)

### Core Principles
1. **System works without plugins** — All functionality works by default
2. **Plugins override/extend** — Plugins are not required dependencies
3. **Core owns context** — Shared context is managed by core
4. **Sync by default** — Event handlers are sync unless opted into async
5. **Manual reload only** — No hot-reload, restart required
6. **Full access** — Plugins have full system access, trust is explicit
7. **No verification** — User trusts registry, no signature/checksum verification

### Plugin Types (5 active)
1. **SiteHandlerPlugin** — Site-specific session extraction/injection
2. **SessionRefreshPlugin** — Provider-specific session refresh
3. **ProxyProviderPlugin** — Provider-specific proxy logic
4. **CaptchaPlugin** — Provider-specific CAPTCHA solving
5. **NotificationPlugin** — Multi-channel notifications

### Removed Types (handled by core)
- ~~ExportFormatPlugin~~ — Core handles export formats
- ~~SessionValidatorPlugin~~ — Core handles session validation
- ~~StealthPlugin~~ — Core handles stealth via StealthManager

### Registry
- **Multiple registries** with priority ordering
- **Latest version wins** on conflict
- **`--registry` flag** to override
- **Primary through TUI** — CLI is secondary

### Dependencies
- **Topological sort** for load order
- **Latest version wins** on conflict
- **Depth limit 5**
- **Circular detection** and rejection
- **Major version only** (`@1`)

### Error Handling
- **Always fall back to core** — Plugin failure doesn't crash core
- **Both PluginResult + exceptions** — Expected failures return PluginResult, unexpected raise exceptions
- **Graceful degradation** — Old plugins still work

### Configuration
- **Both plugin directory + core config** — Plugin-specific in plugin dir, global in core config
- **Schema validation** — Config validated against plugin schema
- **on_configure() wiring** — Called after loading, on user command, at runtime

---

## Key Files

| Phase | Files Created/Modified |
|-------|----------------------|
| 0 | `.agent/phases/0-research-findings.md` |
| 1 | `tokenade/core/events/` (7 files) |
| 2 | `tokenade/core/context/` (7 files) |
| 3 | `tokenade/core/integration/plugin_loader.py`, `tokenade/plugin/oauth2/plugin.py`, `tokenade/plugin/base.py`, `tokenade/core/browser/captcha.py` |
| 4 | `tokenade/core/integration/registry_manager.py`, `tokenade/core/integration/registry_cache.py` |
| 5 | `tokenade/core/integration/plugin_loader.py`, `tokenade/core/health/health_reporter.py` |
| 6 | `tokenade/core/integration/dependency_graph.py`, `tokenade/core/integration/dependency_resolver.py` |
| 7 | `tokenade/core/integration/plugin_config.py` |
| 8 | `~/.tokenade/plugins/*/` (handler conversions) |
| 9 | `tokenade/cli/session_export.py`, `tokenade/cli/handlers/browser_ops.py`, `tokenade/cli/__init__.py` |
| 10 | `tokenade/tui/app.py` |
| 11 | `docs/`, `examples/plugins/`, `README.md`, `CONTRIBUTING.md`, `ARCHITECTURE.md`, `CHANGELOG.md` |

---

## Testing Strategy

| Phase | Test Focus |
|-------|-----------|
| 0 | Research only, no tests |
| 1 | Event bus unit tests |
| 2 | Shared context unit tests |
| 3 | Plugin wiring integration tests |
| 4 | Registry system unit tests |
| 5 | Plugin lifecycle unit tests |
| 6 | Dependency resolution unit tests |
| 7 | Plugin configuration unit tests |
| 8 | Handler conversion integration tests |
| 9 | CLI command tests |
| 10 | TUI screen tests |
| 11 | Example tests, documentation tests |

---

## Commit Strategy

- **One commit per phase** (or per major task within a phase)
- **All tests must pass before commit**
- **No commits until verification steps complete**
- **Descriptive commit messages** following repo conventions

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Breaking existing tests | Run full test suite before each commit |
| Breaking existing plugins | Backward compatible changes only |
| Event bus performance | Async handlers, thread pool, non-blocking |
| Shared context thread safety | Lock all operations |
| Dependency resolution complexity | Topological sort, depth limit, circular detection |
| Registry cache staleness | TTL-based cache, manual refresh option |
| Plugin security | Trust model (user installs), no sandboxing |
| Documentation drift | Documentation updated in Phase 11, tested |

---

## Success Criteria

- [ ] All 5216+ tests pass
- [ ] Event bus works without plugins
- [ ] Shared context works without plugins
- [ ] Plugins run by default, `--no-plugin` to exclude
- [ ] Multiple registries with priority ordering
- [ ] Plugin lifecycle is deterministic
- [ ] Dependency resolution works (topological sort, depth limit, circular detection)
- [ ] Plugin configuration works (schema, storage, CLI)
- [ ] Built-in handlers converted to plugins
- [ ] CLI updated with all commands
- [ ] TUI updated with registry management
- [ ] Documentation is comprehensive
- [ ] Examples work
