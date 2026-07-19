# Plans Summary

## Active Plans

### Gateway & Request Framework (2026-07-18)

**Status:** Complete ✅

Six-phase implementation to separate gateway (local multi-session control plane) from proxy (upstream network egress) and build a nested request framework.

**Deliverables:**
- `tokenade run --request request.json` — nested plugin execution
- `tokenade gateway --request request.json` — local session control plane
- `tokenade proxy resolve --request request.json` — upstream proxy provider tooling

**Shipped in:** tokenade 1.1.61

---

### Post-1.1.60 Continuation (2026-07-18 → 2026-07-19)

**Status:** Complete ✅

Follow-up work after 1.1.60 release to improve marketplace witness reliability, strengthen browser profile discovery, and implement safer launch profile selection.

**Deliverables:**
- Witness script env-var overrides (marketplace `9c8c39b`)
- Telegram strict neutral-chat witness (`https://web.telegram.org/a/#777000`)
- Fresh Telegram export from Firefox Snap profile
- Google Flow single-account limitation documented (marketplace `68c574d`)
- `TOKENADE_VERIFY_INSTALL_CLOAK=1` option in PyPI verification
- Request framework examples in README
- Launch profile selection (`--profile`, `--copy-profile`, `--use-original-profile`)
- Browser profile cache at `~/.tokenade/browser_paths.json`

**Shipped in:** tokenade 1.1.62

---

## Deferred Work

| Item | Reason | Future Enhancement |
|------|--------|-------------------|
| Google Flow multi-account selection | Single-account workaround documented | `target_email` config + account-chooser automation |

---

## Release History

| Version | Date | Key Features |
|---------|------|-------------|
| 1.1.62 | 2026-07-19 | Launch profile selection, request docs, verify cloak option |
| 1.1.61 | 2026-07-18 | Gateway, request framework, proxy resolver, browser cache |
| 1.1.60 | 2026-07-18 | Baseline release |
