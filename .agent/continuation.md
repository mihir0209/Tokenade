# Tokenade — Agent Handoff / Continuation

**Date:** 2026-07-12  
**Audience:** New agent with zero prior context  
**Repo:** `/home/ghostrider/Projects/tokenade`  
**Related plugins repo:** `/home/ghostrider/Projects/tokenade-plugins`  
**Author / copyright:** **MiHiR** (styling exact — not "Mihir" / not "Tokenade Team")  
**Version:** `1.0.0` (PyPI rebaselined; only release on PyPI after wipe)  
**Branch:** `main`

This file is the single entrypoint to continue work. Read it fully before coding.

---

## 1. What this project is

**Tokenade** = **browser session portability**, not Multilogin/AdsPower.

Core loop:

```text
donor browser (logged in)
  → tokenade export  (+ site-handler plugin)
  → .tokenade file (cookies ± storage, optional encrypt)
  → tokenade launch | tokenade proxy
  → target browser / CDP proxy (session replay)
```

**North star:** export → package → transfer → inject/proxy → use without invalidation (where the site allows).

**Not the product:** full anti-detect browser suite, fake "Grade A" stealth, session marketplace, Multilogin parity marketing.

**Honesty policy:** docs/CLI must separate **battle-tested** from **code exists**. No fake plugin downloads/ratings. Stealth is measured, not marketed as undetectable.

---

## 2. Where you are (status)

| Area | State |
|------|--------|
| PyPI | `tokenade==1.0.0` only |
| Version | `1.0.0` (`pyproject.toml` + `__init__.py`) |
| LICENSE | MIT, Copyright (c) 2026 MiHiR |
| Tests | **5216 passed, 0 failed, 9 skipped** in ~109s |
| CI | GitHub Actions (passes) |
| Official plugins | 22 (`verified=false` until contract review) |
| Core Lines | ~51k |
| Honesty | P0 pass complete; no fake metrics/claims |

### Sprint Status

| Sprint | Focus | Status |
|--------|--------|--------|
| **0** | Plugin-owned `site_config.json`; delete root catalog | **DONE** |
| **A** | Productize Google recipe (CLI + tutorial) | **DONE** |
| **B** | ChatGPT / GitHub handler depth; packaging ships `site_config.json` | **DONE** |
| **C** | Vivaldi CDP + macOS matrix | **Pending (deprioritized)** |
| **D** | Behavioral regression tests (not coverage theater) | **DONE** |
| **E** | Secondary docs honesty sweep | **DONE** |
| **71** | Code audit & dead code removal | **DONE** |
| **72** | Test suite optimization for CI speed | **DONE** |
| **65** | Documentation overhaul + structural cleanup | **DONE** |
| **C** | Vivaldi profile discovery + macOS CI matrix | **DONE** |

### What changed recently (Phases 71-72, 65)

- **Dead code removed:** `tokenade/core/antidetection/`, `tokenade/core/integration/webhooks.py`
- **Session management consolidated:** `session_rotator.py` → `core/refresh/rotator.py` + `core/refresh/session_rotator.py`; `session_refresher.py` → `core/refresh/`
- **Test suite optimized:** 302 failures → 0; 124s → 109s. Module-level `time.sleep` replacement in conftest.py, reduced stress test loops, fixed import paths.
- **Markers:** `asyncio` marker registered in `pyproject.toml`; `pytest-asyncio` + `pytest-aiohttp` installed.
- **Phase 65 — Documentation overhaul:** ARCHITECTURE.md module tree rewritten, CONTRIBUTING.md phantom dirs fixed, TUTORIALS.md extension paths corrected, CHANGELOG.md created, `stealth_test.py` → `stealth_validation.py`, `session.py` split (945→532 lines, `cmd_export` → `session_export.py`).

---

## 3. Critical architecture decision (Sprint 0)

> **Behavior + declarative site metadata live in site-handler plugins.**  
> Core only **resolves** configs from installed plugins.  
> **No** growing root `site_configs/` catalog.

### Plugin layout (canonical)

```text
~/.tokenade/plugins/google-handler/
├── plugin.json          # manifest (type: "handler")
├── plugin.py            # extract / inject / verify
└── site_config.json     # domains, critical_cookies, URLs  ← REQUIRED for product sites
```

### Core resolution

| API | Role |
|-----|------|
| `tokenade.core.importer.site_configs.get_site_config(name)` | Load from plugins' `site_config.json` |
| `SiteHandlerPlugin` (`tokenade/plugin/base.py`) | Loads `site_config.json` on `set_plugin_dir()` |
| `PluginLoader` (`tokenade/core/integration/plugin_loader.py`) | Calls `set_plugin_dir()`; registers handlers |

**Do not:** re-add root `site_configs/`, re-add a mega `SITE_CONFIGS` dict, or put new site domain lists in core Python.

---

## 4. Proven recipes (battle evidence)

### Google (2026-07-10)

| Claim | Result |
|-------|--------|
| FF export → Brave clean | **Works** (Inbox, real account) |
| Same jar multi-browser / multi-device (non-Chrome) | **Works** |
| Chrome / Chromium target | **Fails** (accountchooser / signed out) |

**Recipe:**
```bash
tokenade export --browser-name firefox --plugin google-handler -o gmail.tokenade
tokenade launch --browser brave --session gmail.tokenade --plugin google-handler \
  --url "https://mail.google.com/mail/u/0/#inbox" \
  --profile-dir /tmp/tokenade-brave-clean --port 9223 --visible
```

### GitHub

```bash
tokenade export --browser-name firefox --plugin github-handler -o github.tokenade
tokenade launch --browser brave --session github.tokenade --plugin github-handler \
  --url "https://github.com" --profile-dir /tmp/tokenade-gh-brave --port 9224 --visible
```

---

## 5. Key paths (code & docs)

### Core

| Path | Why |
|------|-----|
| `tokenade/core/importer/site_configs.py` | Plugin-backed `get_site_config` / discovery |
| `tokenade/core/refresh/` | Session rotation, refresh, health scoring |
| `tokenade/core/crypto/encryptor.py` | AES-256-GCM encryption (PBKDF2 600k) |
| `tokenade/core/proxy/cdp_proxy.py` | CDP proxy (TLS fingerprint matching) |
| `tokenade/plugin/base.py` | `SiteHandlerPlugin` + site_config load |
| `tokenade/handlers/resolve.py` | Site-driven handler resolution |
| `tokenade/cli/` | CLI (modular handlers/) |
| `pyproject.toml` | version `1.0.0`, dev deps, mutmut config |

### Docs (user-facing)

| Path | Why |
|------|-----|
| `README.md` | Front door |
| `docs/TUTORIAL_GETTING_STARTED.md` | Gmail→Brave golden path |
| `docs/SITE_CONFIGS.md` | Plugin site_config schema |
| `docs/PLUGIN_DEVELOPMENT.md` | Plugin authoring |

### Agent notes / evidence

| Path | Why |
|------|-----|
| `.agent/continuation.md` | **This handoff** |
| `.agent/working.md` | Honesty + release policy |
| `.agent/phases.md` | All phase tracking |
| `.agent/plans/SUMMARY.md` | Plan index |
| `.agent/results/` | Battle-verified evidence |

### Plugins

| Path | Why |
|------|-----|
| `../tokenade-plugins/plugins/*-handler/` | Source of truth |
| `~/.tokenade/plugins/` | Runtime install dir |

---

## 6. Dev / test commands

```bash
cd /home/ghostrider/Projects/tokenade

# Install dev deps
pip install -e ".[dev]"   # or .venv/bin/pip install -e ".[dev]"

# Full test suite
pytest -q --tb=short --timeout=60

# Targeted tests
pytest tokenade/tests/test_session_rotator.py -q
pytest tokenade/tests/test_plugin_system.py -q

# Mutation testing
make test-mut
```

---

## 7. Constraints & user preferences

1. **Author string:** always **MiHiR**
2. **No premature PyPI / tags** without explicit ask
3. **Honesty over hype** in any user-facing text
4. **Plugins for sites**, not monorepo JSON dumps
5. Prefer specialized tools; keep changes scoped to the sprint
6. Do not invent commits/PRs unless asked

---

## 8. Suggested first actions for the next agent

1. `git status` to see uncommitted work
2. Read `.agent/phases.md` for full phase history
3. Read `.agent/plans/SUMMARY.md` for active plans
4. Confirm `pytest -q` passes clean (5216 tests)
5. Start next work per user direction

---

**End of handoff.**
