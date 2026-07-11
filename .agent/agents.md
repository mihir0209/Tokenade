# Tokenade Agent Rules

**Last updated:** 2026-07-12

## Project Structure

```
.agent/
  ├── agents.md          # This file — project rules and workflow
  ├── phases.md          # All phases tracked (status, dates, outputs)
  ├── plans/             # Drafted plans (date-stamped markdown)
  ├── reviews/           # Code reviews and quality inspections
  ├── results/           # Battle-verified evidence
  └── working.md         # Current state and release policy
```

## Plan Drafting Workflow

When work on a phase/task is completed, **draft the next plan** by:

1. **Check remaining items** from the current plan
2. **Check deferred items** — respect deferral dates, note impact
3. **Check previously remaining tasks** from older plans
4. **Research** if nothing found — look at the codebase, issues, user needs
5. **Draft the plan** following project conventions

### Plan Naming Convention

```
YYYY-MM-DD-title-slug.md
```

Examples:
- `2026-07-04-phase-61-site-handlers.md`
- `2026-07-04-cloakbrowser-integration.md`

### Plan Structure

Each plan should include:
- **Goal** — what we're building and why
- **Current state** — what exists, what's broken
- **Implementation** — step-by-step tasks
- **Dependencies** — what must be done first
- **Testing** — how to verify each step
- **Deferred items** — if deferring, note: what, why, impact, when to revisit

## Phase Completion Rules

When a phase is completed end-to-end:

1. **Update phases.md** — mark as ✅, add date, outputs, verification
2. **Add testing instructions** to the phase section in phases.md
   - Include CLI commands to verify
   - Include expected outputs
   - Include what to check manually (for E2E tests that can't be automated)
3. **Draft the next plan** — follow the plan drafting workflow above
4. **Commit** — with phase number and description

## Testing Instructions Format

Add to each completed phase in phases.md:

```markdown
### Testing (Manual Verification)

Commands:
\`\`\`bash
tokenade <command> <args>
\`\`\`

Expected:
- [ ] <what to verify>
- [ ] <what to verify>

Cross-platform:
- [ ] Linux: <test>
- [ ] Mac: <test>
- [ ] Windows: <test>
```

## Honesty Policy (non-negotiable)

- **Never invent metrics** (downloads, ratings, stealth grades, “production-ready”) without measured evidence.
- **README and marketing copy** must separate battle-tested vs code-present. Prefer under-claiming.
- **Plugin registry** must not ship fake `downloads` / `rating`. `verified=true` only after contract tests + human review.
- **One crypto path:** session encryption uses `tokenade.core.crypto.encryptor.TokenadeEncryptor` (PBKDF2 600k). Plugins must not reimplement weaker crypto.
- **Phase complete ≠ product complete.** Consolidation phases must meet line-count / deletion goals or stay open.
- **Deferred overclaims** go in a dated plan under `plans/` so they can be made true later — not left as lies in the README.
- **Plugins repo** is separate: `~/Projects/tokenade-plugins/`

## Conventions

- **Version in pyproject.toml and __init__.py must match**
- **New CLI commands** get parser in `cli/__init__.py`, handler in `cli/management.py`
- **New modules** get `__init__.py` with `__all__`
- **Tests** go in `tokenade/tests/test_<module>.py`
- **Lint before commit** — `ruff check`
- **Full test suite must pass** before commit
- **No comments in code** unless asked

## Key Files

| File | Purpose |
|------|---------|
| `tokenade/core/refresh/` | Session rotation, refresh, health scoring |
| `tokenade/core/browser/cloak.py` | CloakBrowser integration |
| `tokenade/core/browser/session_state.py` | .tokenade ↔ storage_state |
| `tokenade/core/browser/battle.py` | Battle test suite |
| `tokenade/core/browser/stealth.py` | JS stealth patches (fallback) |
| `tokenade/core/forensics/autopsy.py` | Session forensics |
| `tokenade/core/integration/fleet.py` | Fleet management |
| `tokenade/core/cicd/runner.py` | CI runner |
| `tokenade/tui/app.py` | TUI application |
| `tokenade/plugin/base.py` | Plugin base classes |
| `tokenade/core/crypto/encryptor.py` | AES-256-GCM encryption |
| `tokenade/core/proxy/cdp_proxy.py` | CDP proxy |
