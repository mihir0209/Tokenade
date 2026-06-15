# Tokenade — Full Plan

## Release Policy
**No releases or tags until features are battle-tested with positive real-world results.**
Development on `main`, commit directly. Version bumps only when explicitly requested.

---

## What's Done

### Battle-Tested (confirmed working with real sites)
| Site | Browser | Cookies | Feature | Date |
|------|---------|---------|---------|------|
| ChatGPT | Firefox | 68 | CDP proxy, confirmed user | 2026-06-11 |
| Gmail | Firefox | 149 | CDP proxy, confirmed user, 5/5 persistence | 2026-06-11 |
| Brave (all) | Brave | 111 | Export, 34 critical, auth=logged_in | 2026-06-15 |
| GitHub | Firefox | 15 | Export → Load E2E, auth=logged_in | 2026-06-15 |
| Reddit | Firefox | 10 | Export → Load E2E, auth=logged_in | 2026-06-15 |

### Bugs Fixed This Session
- Forward proxy HTTPS CONNECT tunneling (was HTTP only)
- Multi-site proxy `_run_async()` → `start()` crash
- Auto-refresh config timing (config after start)
- Session sharing encryption (AES-256-GCM, was base64)

### Code Quality
- 1383 tests passing, 10 skipped, 0 failures
- 81% test coverage

---

## What's Next — In Order

### Phase 1: Battle-Test Core Features (This Session)

These are features that exist but have NEVER been tested with real browsers/sites.

#### 1.1 Forward Proxy HTTPS
- **What:** The HTTPS CONNECT tunnel was just implemented but not tested
- **How:** `export HTTP_PROXY=http://127.0.0.1:9223` then `curl https://example.com`
- **File:** `tokenade/core/proxy/forward_proxy.py`
- **Success:** HTTPS sites load through the proxy with cookies injected

#### 1.2 Multi-Site Proxy
- **What:** The `_run_async` bug was just fixed but not tested
- **How:** Create 2+ .tokenade files, run `tokenade proxy --all -d ./sessions/`
- **File:** `tokenade/core/proxy/multi_site_proxy.py`
- **Success:** Both sites load in separate tabs, cookies injected per-site

#### 1.3 Session Refresh
- **What:** Re-exports cookies from source browser while proxy is running
- **How:** Start proxy with `--auto-refresh`, then browse. Wait for refresh cycle.
- **File:** `tokenade/core/refresh/session_refresher.py`
- **Success:** Cookies updated without restarting proxy

#### 1.4 Profile Injection
- **What:** Writes cookies directly into browser profile SQLite
- **How:** `tokenade inject-profile -s session.tokenade --browser firefox --profile /path/to/profile`
- **File:** `tokenade/core/injector/profile_manager.py`
- **Success:** Open browser normally, already logged in

#### 1.5 Health Check
- **What:** Checks cookie expiry, auth status, generates report
- **How:** `tokenade health -s session.tokenade`
- **File:** `tokenade/core/refresh/health_checker.py`
- **Success:** Shows accurate expiry times, recommendations

#### 1.6 Session Merge/Rotate
- **What:** Merge multiple sessions, rotate between them
- **How:** `tokenade sessions merge -d ./sessions/` then `tokenade sessions rotate`
- **File:** `tokenade/core/importer/session_manager.py`
- **Success:** Merged session has all cookies, rotation cycles through sessions

### Phase 2: Fix Remaining Issues

#### 2.1 Chrome Cookie Decryption Validation
- **What:** After extraction, validate decrypted values are readable text
- **Why:** Chrome encrypts with OS keychain; decryption may silently return encrypted bytes
- **File:** `tokenade/core/importer/cookie_extractor.py`
- **Fix:** Add post-extraction check: if value is bytes, try utf-8 decode, warn if fails

#### 2.2 Site Configs
- **What:** Add site-specific configurations for commonly used sites
- **Why:** Currently only `chatgpt.json` exists; need GitHub, Discord, Reddit, Twitter
- **Dir:** `site_configs/`
- **Each needs:** domains, critical_cookies, auth_indicator_css, validate_url

#### 2.3 Session Loader Cleanup
- **What:** Browser process leaks if load fails midway
- **Why:** `close()` only called by CLI, not in error paths
- **File:** `tokenade/core/importer/session_loader.py`
- **Fix:** Add `try/finally` around browser launch to ensure cleanup

### Phase 3: Feature Improvements

#### 3.1 Better Error Messages
- **What:** When things fail, tell the user exactly what to do
- **Why:** Current errors are generic ("Extraction failed — check browser profile is accessible")
- **Files:** All CLI modules
- **Fix:** Add specific error messages:
  - "Chrome not found at expected path. Install Chrome or use --browser-path"
  - "Cookies encrypted but pycryptodome not installed. Run: pip install pycryptodome"
  - "Browser is running. Close Chrome before exporting cookies."

#### 3.2 Session Export Progress
- **What:** Show progress during long operations
- **Why:** Large cookie exports (3000+) take several seconds with no feedback
- **File:** `tokenade/core/importer/cookie_extractor.py`
- **Fix:** Add tqdm progress bar or simple counter output

#### 3.3 Config File Support
- **What:** `~/.tokenade/config.json` with defaults
- **Why:** Users shouldn't have to specify `--browser-name firefox` every time
- **File:** `tokenade/cli/__init__.py`
- **Fix:** Load config on startup, use as defaults for CLI flags

### Phase 4: Documentation & Polish

#### 4.1 README Update
- **What:** Update README with current features, battle-tested sites, installation
- **Why:** README is outdated (references v2.5.0 features)
- **File:** `README.md`

#### 4.2 Site Config Docs
- **What:** Document how to create site configs for new sites
- **Why:** Users need to know how to add support for sites not in the default list
- **File:** `docs/SITE_CONFIGS.md`

#### 4.3 Troubleshooting Guide
- **What:** Common errors and solutions
- **Why:** Users will hit issues; need clear guidance
- **File:** `docs/TROUBLESHOOTING.md`

### Phase 5: Advanced Features (Future)

#### 5.1 Safari Decryption
- **What:** Actually decrypt Safari cookies (currently a no-op)
- **Why:** macOS users can't export from Safari
- **File:** `tokenade/core/importer/safari_extractor.py`
- **Complexity:** High — needs AES-CBC with Keychain key

#### 5.2 Extension Bridge Wiring
- **What:** Connect browser extension to CDP proxy via WebSocket
- **Why:** Real-time cookie updates without restarting proxy
- **Files:** `tokenade/core/proxy/extension_bridge.py`, `tokenade/core/proxy/cdp_proxy.py`
- **Complexity:** Medium

#### 5.3 Advanced Validation Rules
- **What:** Test JS/screenshot/API validation rules
- **Why:** Verify sessions actually work before sharing
- **File:** `tokenade/core/importer/advanced_validator.py`
- **Complexity:** Medium — needs Playwright

#### 5.4 Format Export/Import
- **What:** Convert to Playwright storageState, Puppeteer, Netscape formats
- **Why:** Interoperability with other tools
- **File:** `tokenade/core/importer/format_exporter.py`, `format_importer.py`
- **Complexity:** Low

#### 5.5 Plugin System
- **What:** Load third-party plugins from GitHub registry
- **Why:** Extensibility without modifying core
- **Files:** `tokenade/core/integration/plugin_loader.py`, `plugin_registry.py`
- **Complexity:** Medium — needs real plugins to test

---

## Implementation Order (Next Session)

1. Battle-test forward proxy HTTPS (1.1)
2. Battle-test multi-site proxy (1.2)
3. Battle-test session refresh (1.3)
4. Battle-test profile injection (1.4)
5. Battle-test health check (1.5)
6. Battle-test session merge/rotate (1.6)
7. Fix Chrome cookie validation (2.1)
8. Add site configs (2.2)
9. Fix session loader cleanup (2.3)
10. Better error messages (3.1)
11. Session export progress (3.2)
12. Config file support (3.3)
13. README update (4.1)
14. Site config docs (4.2)
15. Troubleshooting guide (4.3)

## Success Criteria
- All Phase 1 features battle-tested with real sites
- All Phase 2 issues fixed
- Phase 3 improvements implemented
- Phase 4 documentation complete
- No regressions (1383+ tests still passing)

## Notes
- All testing with real browsers and real sites
- Document results in `.agent/working.md`
- No version bumps or releases until features confirmed working
- Commit directly to `main` for each fix/test
