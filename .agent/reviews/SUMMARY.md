# Reviews — consolidated summary
**Date:** 2026-07-10
**Source:** all prior files in `.agent/reviews/`.

## Cross-cutting findings
1. **Honesty over hype** — competitive docs and CLI must match real behavior (brutal review 2026-07-09).
2. **Test quality** — prefer unique behavioral tests + mutation testing over coverage theater.
3. **Architecture** — modular package direction (2026-06) was right; keep deep modules at seams (export, launch, plugins, crypto).
4. **Proxy/TLS** — fingerprint matching is a differentiator; keep claims evidence-backed.
5. **Plugins** — site handlers must override defaults; generic must not steal google/github matches.
6. **Google portability** — earlier “impossible” conclusions were process bugs; 2026-07-10 proves non-Chrome multi-device works; Chrome fails.

## Per-review index
| File | Title | Lines | One-line |
|------|-------|------:|----------|
| `2026-06-01-code-review.md` | Code Review: Tokenade v2.0 Restructure | 103 | Successfully restructured the ad-hoc token extraction scripts into a production-grade, |
| `2026-07-09-brutal-code-review-tokenade-ecosystem.md` | Brutal Code Review: Tokenade + tokenade-plugins | 510 | Tokenade is **not** primarily an anti-detect browser competitor (AdsPower / Multilogin / GoLogin). Those sell fingerprint isolation as a product. |
| `2026-07-09-coverage-test-uniqueness-analysis.md` | Coverage Test Uniqueness Analysis | 142 | For each `*_coverage*.py` file: |
| `code-review-2025-06-12.md` | Tokenade Code Review — 2025-06-12 | 197 | Full codebase review: proxy architecture, importer/runtime, CLI, crypto, tests. |
| `competitor-analysis.md` | Tokenade Competitor Analysis | 193 | *Generated: June 2026* |

## Actionable leftovers (condensed)
- Strip dead/misleading user-facing claims (partially done on launch Google tips).
- Keep mutation/uniqueness policy for tests.
- Competitor comparison: session portability + non-Chrome Google is a real wedge.
- Ecosystem review: plugins repo vs core version skew (api 1.0 vs 1.1 warnings) — clean up when packaging plugins.
