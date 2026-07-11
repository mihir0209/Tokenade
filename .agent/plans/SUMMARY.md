# Plans — consolidated summary
**Date:** 2026-07-12  
**Source:** all prior files in `.agent/plans/` (archived into this single document).

## North star
Tokenade = portable browser sessions (export/inject/proxy) with stealth, plugins, and multi-account ops. Pivot: **plugin marketplace** (not session marketplace). Prefer honesty about what works (Google: non-Chrome).

## Phase themes (historical → current)
| Era | Themes | Status note |
|-----|--------|-------------|
| Core (early 2026) | Package restructure, browser managers, export/import, site configs | Shipped |
| Crypto / injection | Encrypted .tokenade, direct profile inject, multi-site batch, session refresh | Shipped |
| Runtime / proxy | JA3/TLS matching, local fingerprint proxy, CloakBrowser | Partial; Cloak optional |
| Stealth 46–50 | Enhanced stealth, CF/Akamai, marketplace, competitor parity, stealth CI | Quality ongoing |
| Infra 55–63 | Forensics, TUI, plugin integration, CloakBrowser | Shipped |
| Honesty P0-P6 | Docs, deferred claims, code audit, plugin API, handler resolution | Shipped |
| Slimming 71-72 | Dead code removal, session consolidation, test optimization | Shipped (2026-07-12) |

## Sprint status (current)
| Sprint | Focus | Status |
|--------|--------|--------|
| **0** | Plugin-owned `site_config.json`; delete root catalog | **DONE** |
| **A** | Productize Google recipe (CLI + tutorial) | **DONE** |
| **B** | ChatGPT / GitHub handler depth; packaging ships `site_config.json` | **DONE** |
| **C** | Vivaldi CDP + macOS matrix | **Pending (deprioritized)** |
| **D** | Behavioral regression tests | **DONE** |
| **E** | Secondary docs honesty sweep | **DONE** |
| **71** | Code audit & dead code removal | **DONE** |
| **72** | Test suite optimization for CI speed | **DONE** |

## Individual plan index (selected — see `plans/` for full list)
| File | Title | Status |
|------|-------|--------|
| `2026-07-10-next-natural-plan.md` | Post README/1.0.0 sequencing | Superseded by Sprint 71-72 |
| `2026-07-05-code-slimming-extension-perf.md` | Phase 71-74 roadmap | **DONE** (71-72 complete) |
| `2026-07-09-p0-honesty-deferred-claims.md` | P0 Honesty deferred claims | **DONE** |

## Still relevant open work
1. **Sprint C:** Vivaldi CDP + macOS matrix (deprioritized; browser-side flake)
2. More site handlers beyond Google/GitHub/ChatGPT
3. Non-site plugin bases (refresh, export-format, health) — deferred YAGNI

## Explicitly deprecated plan noise
- Duplicate JA3 plans (2026-06-01 + 2026-06-05) → one TLS/proxy story
- Multiple "next-roadmap" files (06/07/08) → see phase table
- Session marketplace ideas → replaced by plugin marketplace
