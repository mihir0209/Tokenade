# Phase 0: Pre-Planning & Research

**Objective:** Understand current codebase state, identify all files that need changes, validate design assumptions.

**Status:** NOT STARTED
**Dependencies:** None
**Blocks:** All subsequent phases

---

## Scope

### IN
- Audit current plugin system files
- Audit current event/notification infrastructure
- Audit current scheduler/cron infrastructure
- Audit current session management flow
- Audit current CLI plugin commands
- Audit current TUI plugin integration
- Document all call sites that need modification
- Validate design assumptions against actual code

### OUT
- No code changes in this phase
- No new files created
- No commits

---

## Strict Rules

1. **No code changes** — This phase is research only
2. **Document everything** — Every finding goes into `.agent/phases/0-research-findings.md`
3. **Be exhaustive** — Search for ALL call sites, not just obvious ones
4. **Include file:line references** — Every finding must have exact location
5. **Validate assumptions** — If design assumption is wrong, document it

---

## Detailed Tasks

### T0.1: Audit Plugin System Files
- Read `tokenade/plugin/base.py` — Document all base classes, methods, signatures
- Read `tokenade/plugin/api.py` — Document all API types
- Read `tokenade/plugin/__init__.py` — Document exports
- Read `tokenade/plugin/oauth2/plugin.py` — Document OAuth2Plugin (standalone, not PluginBase)

### T0.2: Audit Plugin Infrastructure
- Read `tokenade/core/integration/plugin_loader.py` — Document loader, type registries, getters
- Read `tokenade/core/integration/plugin_registry.py` — Document registry, search, install
- Read `tokenade/core/integration/plugin_verifier.py` — Document verification
- Read `tokenade/core/integration/plugin_search.py` — Document search index
- Read `tokenade/core/integration/plugin_browser.py` — Document marketplace HTML
- Read `tokenade/core/integration/plugin_export.py` — Document export integration
- Read `tokenade/core/integration/plugin_testing.py` — Document contract tests

### T0.3: Audit Current Event/Notification Infrastructure
- Search for `webhook`, `notify`, `notification` across codebase
- Read `tokenade/core/daemon/session_daemon.py` — Document webhook implementation
- Read `tokenade/core/health/health_reporter.py` — Document health notification
- Read `tokenade/core/integration/webhooks.py` — Document if it exists (may be deleted)
- Document all ad-hoc notification implementations

### T0.4: Audit Current Scheduler/Cron Infrastructure
- Search for `cron`, `scheduler`, `schedule`, `timer` across codebase
- Read `tokenade/core/cicd/workflow_generator.py` — Document CI/CD generation
- Read `tokenade/core/daemon/session_daemon.py` — Document daemon polling
- Document all scheduling-related code

### T0.5: Audit Current Session Management Flow
- Read `tokenade/core/operations/session_ops.py` — Document refresh flow
- Read `tokenade/cli/handlers/browser_ops.py` — Document CLI refresh commands
- Read `tokenade/cli/session_export.py` — Document export flow
- Document all call sites where plugins are used

### T0.6: Audit Current CLI Plugin Commands
- Read `tokenade/cli/__init__.py` — Document all plugin subcommands
- Document all `--plugin` flags
- Document all `--no-plugin` flags (if any)
- Document all plugin-related CLI options

### T0.7: Audit Current TUI Plugin Integration
- Read `tokenade/tui/app.py` — Document TUI plugin screens
- Document marketplace view, installed view, detail view
- Document TUI registry management

### T0.8: Identify All Files Needing Changes
- Compile list of all files that need modification
- For each file, document what changes are needed
- Identify dependencies between files

---

## Files to Read (Exhaustive List)

| File | Purpose |
|------|---------|
| `tokenade/plugin/base.py` | Base classes |
| `tokenade/plugin/api.py` | API types |
| `tokenade/plugin/__init__.py` | Exports |
| `tokenade/plugin/oauth2/plugin.py` | OAuth2Plugin |
| `tokenade/core/integration/plugin_loader.py` | Loader |
| `tokenade/core/integration/plugin_registry.py` | Registry |
| `tokenade/core/integration/plugin_verifier.py` | Verifier |
| `tokenade/core/integration/plugin_search.py` | Search |
| `tokenade/core/integration/plugin_browser.py` | Marketplace |
| `tokenade/core/integration/plugin_export.py` | Export |
| `tokenade/core/integration/plugin_testing.py` | Testing |
| `tokenade/core/operations/session_ops.py` | Session ops |
| `tokenade/cli/handlers/browser_ops.py` | CLI browser ops |
| `tokenade/cli/session_export.py` | CLI export |
| `tokenade/cli/__init__.py` | CLI commands |
| `tokenade/tui/app.py` | TUI |
| `tokenade/core/daemon/session_daemon.py` | Daemon |
| `tokenade/core/health/health_reporter.py` | Health |
| `tokenade/core/cicd/workflow_generator.py` | CI/CD |
| `tokenade/core/browser/captcha.py` | Captcha |
| `tokenade/core/browser/stealth/manager.py` | Stealth |
| `tokenade/core/proxy/manager.py` | Proxy |

---

## Verification

- [ ] All files read and documented
- [ ] All call sites identified
- [ ] All design assumptions validated
- [ ] Research findings written to `.agent/phases/0-research-findings.md`
- [ ] No code changes made
