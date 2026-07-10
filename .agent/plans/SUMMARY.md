# Plans — consolidated summary
**Date:** 2026-07-10
**Source:** all prior files in `.agent/plans/` (archived into this single document).

## North star
Tokenade = portable browser sessions (export/inject/proxy) with stealth, plugins, and multi-account ops. Pivot: **plugin marketplace** (not session marketplace). Prefer honesty about what works (Google: non-Chrome).

## Phase themes (historical → current)
| Era | Themes | Status note |
|-----|--------|-------------|
| Core (early 2026) | Package restructure, browser managers, export/import, site configs | Largely shipped |
| Crypto / injection | Encrypted .tokenade, direct profile inject, multi-site batch, session refresh | Shipped / partial |
| Runtime / proxy | JA3/TLS matching, local fingerprint proxy, CloakBrowser | Partial; Cloak optional |
| Stealth 46–50 | Enhanced stealth, CF/Akamai, marketplace, competitor parity, stealth CI | Ongoing quality |
| Infra 55–63 | Forensics, TUI, plugin integration, CloakBrowser | Mixed; verify claims vs code |
| Polish / honesty | Docs, deferred claims, code audit, plugin API v1.1 site handlers | Active |

## Individual plan index (drastic)
| File | Title | One-line |
|------|-------|----------|
| `00-roadmap-summary.md` | Tokenade Development Roadmap — Phases 46-50 | User insights led to strategic pivot: |
| `01-enhanced-stealth.md` | Phase 46: Enhanced Browser Stealth | Make tokenade's browser automation pass modern bot detection systems (Cloudflare, Akamai, PerimeterX, DataDome). |
| `02-cloudflare-akamai-bypass.md` | Phase 47: Cloudflare & Akamai Bypass | Enable tokenade to bypass Cloudflare and Akamai anti-bot protections, which protect ~40% of top websites. |
| `03-plugin-marketplace-enhancement.md` | Phase 48: Plugin Marketplace Enhancement | Expand the plugin marketplace from 10 official plugins to a comprehensive ecosystem with new plugin types and improved discovery. |
| `04-competitor-feature-parity.md` | Phase 49: Competitor Feature Parity | Match key features from competitors (AdsPower, Multilogin, GoLogin, Dolphin Anty) while maintaining tokenade's unique position as a session portability tool. |
| `05-stealth-testing-validation.md` | Phase 50: Stealth Testing & Validation | Create automated stealth testing infrastructure to validate that tokenade passes bot detection systems. |
| `06-next-roadmap.md` | Next Roadmap — Post Phase 50 | - **4449+ tests passing** across Python 3.10/3.11/3.12 |
| `07-next-roadmap.md` | Phase 55-58 Roadmap — Infrastructure, Forensics, TUI | `tokenade ci run` reads a `tokenade.yml` file from the current working directory and executes session operations locally — no GitHub Actions, no external CI service, just a local r |
| `08-next-roadmap.md` | Phase 59-62 Roadmap — Plugin Integration, Polish, Scale | 1. **Plugin install doesn't refresh TUI** — After install, marketplace cards don't update button state without manual refresh |
| `09-cloakbrowser-integration.md` | Phase 63 — CloakBrowser Integration | A custom-built Chromium binary with **58 source-level C++ patches** — canvas, WebGL, audio, fonts, GPU, screen, WebRTC, network timing, automation signals, CDP input behavior. Not  |
| `2026-06-01-additional-site-handlers.md` | Additional Site Handlers Expansion | The handler pattern has been proven with Google and GitHub implementations. |
| `2026-06-01-architecture-design.md` | Tokenade Architecture Plan | Transform the existing ad-hoc token extraction scripts into a production-grade, |
| `2026-06-01-datestamp-convention-benefits.md` | Datestamp Naming Convention - Benefits and Rationale | All plans, reviews, and documentation files use the format: |
| `2026-06-01-distributed-session-management.md` | Distributed Session Management | For enterprise or multi-device scenarios, sessions need to be synchronized |
| `2026-06-01-fingerprint-spoofing-runtime.md` | Implementation Plan: Fingerprint Spoofing Runtime | Build a comprehensive fingerprint spoofing runtime that intercepts and overrides ALL JavaScript fingerprinting APIs with stealth wrappers, making the target browser indistinguishab |
| `2026-06-01-implementation-roadmap.md` | Implementation Roadmap | As discussed, we start with simpler sites and incrementally tackle Google: |
| `2026-06-01-ja3-tls-fingerprint-matching.md` | Runtime Engine Enhancement: JA3 Fingerprint Matching | The current RuntimeEngine matches HTTP headers but not TLS fingerprints. |
| `2026-06-01-next-phase-testing-coverage.md` | Next Phase: Comprehensive Test Coverage | The current test suite covers crypto and fingerprint modules (2/6 core modules). |
| `2026-06-01-session-import-from-existing-browsers.md` | Session Import/Export from Existing Browsers | - **Donor Device**: The device/browser that already has logged-in sessions. We *export* cookies from here. |
| `2026-06-01-web-dashboard-rest-api.md` | Web Dashboard and REST API Server | Currently Tokenade is CLI-only. This plan adds a web dashboard and REST API |
| `2026-06-05-direct-profile-injection.md` | Direct Profile Injection CLI Command | Currently, injecting cookies into a real browser profile requires manual SQLite manipulation (as we did for Brave testing). This should be a proper CLI command with error handling, |
| `2026-06-05-encrypted-tokenade-files.md` | Encrypted .tokenade Files | `.tokenade` files contain sensitive session cookies in plaintext. If intercepted, attackers gain full account access. |
| `2026-06-05-ja3-tls-fingerprint-matching.md` | JA3/TLS Fingerprint Matching | Cloudflare and similar anti-bot services check TLS fingerprints (JA3/JA4). When cookies are injected via Playwright/Chromium, the TLS fingerprint doesn't match the source browser ( |
| `2026-06-05-local-fingerprint-proxy.md` | Local Fingerprint Proxy Server — Core Architecture | Instead of injecting cookies into a target browser and hoping the fingerprint matches, we run a **local proxy server** that: |
| `2026-06-05-multi-site-batch.md` | Multi-Site Batch Export/Load | Currently, users must export and load sites one at a time. For users with many accounts (social media, banking, work), this is tedious. |
| `2026-06-05-session-refresh-mechanism.md` | Session Refresh Mechanism | Sessions expire. Currently, users must manually re-export from the source browser when cookies expire. This breaks automation workflows. |
| `2026-06-05-web-dashboard.md` | Web Dashboard for Session Monitoring | Managing multiple sessions across multiple accounts requires checking each one individually. No unified view of session health. |
| `2026-06-14-v4-implementation-plan.md` | Tokenade v4.0 Implementation Plan — 2026-06-14 | - **Version**: 3.0.0 |
| `2026-06-15-v4-implementation-plan.md` | Tokenade v4.0 Implementation Plan — 2026-06-15 | - **Version**: 3.5.0 (published to PyPI) |
| `2026-07-04-polish-docs-ecosystem.md` | Phase 64-67 Roadmap — Polish, Docs, Ecosystem, Browser Extension | - Session injection E2E (63.10) — needs real browser |
| `2026-07-05-code-audit-refactoring.md` | Phase 68-70 — Code Audit, Refactoring, and PyPI Release | 1. **PyPI is stale** — Local is 6.2.0, PyPI is 6.1.6. All Phase 55-67 work is unpublished. |
| `2026-07-05-code-slimming-extension-perf.md` | Phase 71-74 — Code Slimming, Browser Extension, Plugin Polish, Performance | 49,616 lines of core code is a lot for a CLI tool. The largest files are: |
| `2026-07-05-full-ecosystem-transfer.md` | Phase 75-77 — Full Ecosystem Transfer, Encryption, Plugin-First Architecture | Tokenade currently transfers **only cookies**. Modern web apps use localStorage, sessionStorage, IndexedDB, and service workers for authentication and state. A cookie-only transfer |
| `2026-07-05-integration-testing-release.md` | Phase 78-80 — Integration, Testing, and Release | Phases 75-77 created the code for full ecosystem transfer, encryption, and plugin-first export. But the code is **not wired into the CLI**: |
| `2026-07-05-plugin-api-maturation.md` | Phase 78-80 — Plugin API Maturation, Integration & Release | If AnyIP or BrightData wants to write a proxy plugin: |
| `2026-07-06-plugin-api-v1.1-site-handlers.md` | Phase 82-Extended — Plugin API v1.1: Login Verification, Export Specification, Site Handlers | The plugin API v1.0 is missing critical capabilities that the existing `handlers/` already have: |
| `2026-07-06-plugin-sdk-site-handlers.md` | Phase 81-83 — Plugin SDK, Reference Implementations, Site Handlers | Phase 79 migrated all 20 plugins in the `tokenade-plugins` repo to API v1.0. But the **local copies** at `~/.tokenade/plugins/` are still the old versions: |
| `2026-07-06-proxy-architecture.md` | Phase 82 — Proxy Architecture | Tokenade uses proxies in 3 commands, all via `--proxy` flag passed to browser: |
| `2026-07-09-p0-honesty-deferred-claims.md` | P0 Honesty — Deferred Claims (make true later) | export → package (.tokenade) → transfer → proxy\|launch → use without invalidation |
| `feature-roadmap.md` | Tokenade Feature Plans — Updated 2026-06-14 (v3.4.0) | - `html.escape()` applied to all GUI HTML values in `cdp_proxy.py` and `server.py` |
| `full-plan.md` | Tokenade — Full Plan | Development on `main`, commit directly. Version bumps only when explicitly requested. |
| `next-steps.md` | Tokenade — Next Steps (Updated) | - ✅ Forward proxy HTTPS CONNECT tunneling (fixed) |
| `phase12-implementation-plan.md` | Tokenade v5.1.0 — Implementation Plan | - **Version:** 5.0.0 (released on PyPI) |
| `phase6-plan.md` | Tokenade — Phase 6: Quality, Refactor, Dashboard, Docs | No releases until battle-tested with positive real-world results. Development on `main`. |
| `phase7-plan.md` | Tokenade — Phase 7: Coverage Push to 90%+ | No releases or tags per feature. Development on `main`. Only after battle-tested positive results. |
| `v4.1-plan.md` | Tokenade v4.1 Plan | - Improve test coverage to 80%+ |

## Active plan (2026-07-10)

See **`2026-07-10-next-natural-plan.md`** — post README/1.0.0 sequencing.

### Sprint 0 — DONE
Plugin-owned **`site_config.json`** only. Root `site_configs/` removed.

### Sprint A — DONE
Google recipe productized: launch clean-profile default for session inject,
Chrome-family warning, export locked-DB messaging, plugin tips; getting-started
tutorial rewritten (Gmail→Brave + Windows).

### Sprint B — DONE (2026-07-11)
- Installer (`PluginRegistry._download_plugin`) now always fetches
  `site_config.json` alongside `plugin.json` + `plugin.py`; optional,
  not required (so utility plugins install cleanly).
- `chatgpt-handler` / `github-handler` deepened in `tokenade-plugins`:
  validate(), _matches_domain(), critical_present extraction,
  config-driven verify_login fallback.
- Focus: site configs travel with plugins; the ecosystem stays
  dirt-free.

### Sprint D — DONE (2026-07-11)
Behavioral regression tests, not coverage padding:
- Plugin-match precedence: first-wins by sorted path, fuzzy
  substring fallback (forward + backward), multi-key indexing
  (`site_name` + `name` + plugin stem), no-suffix inference.
- `PluginExporter.find_handler`: specific beats generic; name
  tiebreak when two specific handlers match.
- Install→discover round-trip: `_download_plugin` →
  `discover_plugin_site_configs` → `get_site_config`.
- Fix: pre-existing test bugs (MagicMock().name TypeError in
  tie-break loop; tests subscripts `PluginResult` correctly).

### Sprint E — DONE (2026-07-11)
Secondary docs honesty sweep:
- USE-CASES.md: anti-detection → best-effort; RBAC/LDAP/audit
  → "code present"; antidetect replacement framing removed;
  "bypass Cloudflare" → "results vary by site".
- competitor-comparison.md: "site-agnostic" → "plugin-first";
  "TLS bypass" → "TLS matching".
- TUTORIALS.md: Python 3.9 → 3.10; `.runtime` extra removed
  (curl-cffi is core); "bypass Cloudflare/DataDome" softened.
- PLUGIN_DEVELOPMENT.md: `min_version: 6.0.0 → 1.0.0`.

### Remaining
1. **Sprint C (P1b):** Vivaldi CDP + macOS matrix (deprioritized in plan; browser-side flake, stock launch mostly OK).

Done: README; LICENSE + **MiHiR**; PyPI 1.0.0; Sprint 0, A, B, D, E.

## Still relevant open work (from plans + 2026-07-10 + 2026-07-11)
1. Google portability productization (non-Chrome recipe, messaging) — **proven in battle; productized (Sprint A)**
2. Plugin override correctness (specific > generic) — **fixed 2026-07-10**, behavioral tests added (Sprint D)
3. More base classes for non-site plugins — **deferred (YAGNI until needed)**
4. Broader site handlers — **ChatGPT/GitHub deepened (Sprint B)**
5. Stealth/CF claims: keep evidence-based — **honesty sweep done (Sprint E)**
6. macOS Google matrix — **not verified (deprioritized)**
7. Vivaldi CDP harden — **not done (deprioritized; browser-side flake, stock launch mostly OK)**

## Explicitly deprecated plan noise
- Duplicate JA3 plans (2026-06-01 + 2026-06-05) → one TLS/proxy story
- Multiple “next-roadmap” files (06/07/08) → see phase table above
- Session marketplace ideas → replaced by plugin marketplace
