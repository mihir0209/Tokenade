# Feature Testing Report — Tokenade core loop

**Date:** 2026-07-09  
**Env:** Linux, tokenade 6.4.0, local Firefox + Brave profiles  
**Scope:** Product-facing CLI paths (not unit-test theater)

## Summary

| Area | Result | Notes |
|------|--------|-------|
| CLI version / deps | **PASS** | v6.4.0; 17/22 system packages; 5 GTK/audio libs missing (Cloak/playwright risk) |
| Session file inspect | **PASS** | 5 on-disk `.tokenade` files (github/gmail/chatgpt/telegram/whatsapp) |
| `health` | **PASS** | Heuristic scores; stale repo sessions correctly UNHEALTHY |
| `accounts list/status` | **PASS** | 5 sessions / 186 cookies; status shows logged_in metadata |
| `encrypt` / `decrypt` / `rekey` | **PASS** (after fix) | Round-trip bytes match |
| Wrong-password decrypt exit code | **FIXED** | Was exit 0 → now exit 1 |
| `export --list-profiles` | **PASS** | Firefox + Brave discovered |
| Live export Firefox→github | **PASS** | 9 cookies, auth=logged_in, **health 100%** |
| Live export Brave→google | **PASS** | 80 cookies, 28 critical, auth=logged_in (2 expired → health 97.5%) |
| `validate` | **FIXED** | Was 0 sessions (only `*.json`); now scans `.tokenade` + accepts `auth_state` |
| `diff` | **PASS** | Cookie-only-in-A/B + metadata |
| `validate-session` | **PASS*** | Correct fail on expired cookies; noisy ERROR open('') in health path |
| `autopsy` | **PASS** | NATURAL_EXPIRY on stale github; critical cookies identified |
| Plugins list/search | **PASS** | 22 installed; search github → handler + oauth2 |
| Site configs | **PASS** | 14 sites; JSON overlay still works |
| `curl-cffi` / TLSMatcher | **PASS** | curl_cffi 0.15.0 importable |
| `launch` headless inject | **BLOCKED** | Chrome profile locked (browser already running); need free profile or CDP attach |

\* See open issues.

## Commands exercised

```bash
tokenade --version
tokenade deps check
tokenade health -s <session>
tokenade accounts list|status -d .
tokenade encrypt|decrypt|rekey ...
tokenade export --list-profiles
tokenade export --browser-name firefox --domains github.com -o ...
tokenade export --browser-name brave --domains google.com -o ...
tokenade validate -d .
tokenade validate-session -s github.tokenade
tokenade autopsy -s github.tokenade
tokenade diff github.tokenade gmail.tokenade
tokenade plugin list|search|categories
tokenade launch -s <fresh> -u https://github.com --headless  # blocked by profile lock
```

## Bugs found & fixed this session

### P1 — `encrypt`/`decrypt`/`rekey` success masking (CLI)

**Symptom:** Wrong password on decrypt printed an error but **exited 0** (breaks CI/scripts).  
**Fix:** `tokenade/cli/security.py` raises `SystemExit(1)` on all failure paths (not found, mismatch, crypto error).  
**Tests:** `test_cli_security_coverage.py` updated for fail-closed.

### P1 — `tokenade validate` ignored product files

**Symptom:** `validate -d .` reported `0 valid, 0 invalid` next to five `.tokenade` files.  
**Cause:** Only globbed `*.json`; also required `auth_status` while many packages use `auth_state`.  
**Fix:** `cmd_validate` scans `*.tokenade` + `*.json` and normalizes `auth_state` → `auth_status`.

## Open issues (not fixed this pass)

| ID | Severity | Issue |
|----|----------|-------|
| O1 | Med | `validate-session` logs `Failed to check session health: [Errno 2] No such file or directory: ''` — empty path somewhere in health pipeline (report still useful) |
| O2 | Low | `health` marks sessions UNHEALTHY if `auth_status` missing even when `auth_state=logged_in` / cookies look fine (heuristic inconsistency vs accounts) |
| O3 | Env | Launch/proxy inject needs unlocked browser profile or dedicated temp profile for unattended E2E |
| O4 | Env | Missing apt packages for full Cloak/Playwright stack (`libgtk-3-0`, atk, asound, cups) |
| O5 | Manual | Cross-device transfer, live Gmail/ChatGPT proxy inject, detection sites — need human + unlocked browsers |

## Fresh export health (strong signal)

| Export | Cookies | Critical | Health |
|--------|--------:|---------:|--------|
| Firefox → github | 9 | 2 | **100% HEALTHY** |
| Brave → google | 80 | 28 | 97.5% (2 expired) |

Repo-root `.tokenade` samples are **stale** (June ages / expired criticals) — expected; autopsy correctly says re-export.

## Recommended next feature tests (manual)

1. Close Chrome, re-run:  
   `tokenade launch -s /tmp/tokenade-feature-test/export-ff-github.tokenade -u https://github.com --headless`  
   Confirm logged-in avatar / `logged_in` cookie still set post-load.
2. CDP proxy:  
   `tokenade proxy -s /tmp/tokenade-feature-test/export-brave-google.tokenade --fingerprint --no-open-browser`  
   curl via proxy to accounts.google.com (expect TLS match).
3. Encrypt pipeline: export → encrypt → transfer → decrypt → launch.
4. Plugin contract: `tokenade plugin test` on official set (CI already gates contracts).

## Conclusion

**Core loop works on this machine for export → package → health → crypto → autopsy → accounts.**  
Two real product bugs were found and fixed during testing. Inject/launch E2E needs a free browser profile (or temp profile-dir) before claiming live inject battle results today.
