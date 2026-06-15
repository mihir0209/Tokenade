# Tokenade — Next Steps Plan

## Release Policy
**No releases or tags until features are battle-tested with positive real-world results.**
Development on `main`, commit directly. Version bumps only when explicitly requested.

## Current Battle-Tested Status
- ChatGPT: 68 cookies, CDP proxy, confirmed logged-in
- Gmail: 149 cookies, CDP proxy, confirmed logged-in, 5/5 persistence
- Firefox extraction: Working
- Everything else: **Untested**

## Priority 1: Fix Broken Things (Critical)

### 1.1 Forward Proxy HTTPS Support
**File:** `tokenade/core/proxy/forward_proxy.py`
- Currently only handles HTTP, not HTTPS CONNECT tunneling
- Any browser with `HTTP_PROXY` sends CONNECT for HTTPS sites → silently fails
- Fix: Implement HTTP CONNECT tunneling in `_handle_request`
- Test: Set `HTTP_PROXY=http://127.0.0.1:9223` in browser, browse https://example.com

### 1.2 Multi-Site Proxy Method Bug
**File:** `tokenade/core/proxy/multi_site_proxy.py`
- Calls `proxy._run_async()` which doesn't exist on CDPProxy
- CDPProxy has `run()` (blocking) and `start()` (async)
- Fix: Change to `proxy.run()` or wrap `proxy.start()` in `asyncio.run()`
- Test: `tokenade proxy --all` with multiple .tokenade files

### 1.3 Auto-Refresh Config Timing
**File:** `tokenade/cli/proxy.py` lines 95-101
- `--auto-refresh` modifies config AFTER `proxy.start()` already called
- Refresher already running with `auto_refresh=False`
- Fix: Set config before calling `from_session_file()` or `start()`
- Test: `tokenade proxy -s session.tokenade --auto-refresh`

## Priority 2: Battle-Test More Sites (High Impact)

### 2.1 Chrome Cookie Extraction
- Test export from Chrome (not just Firefox)
- Verify decryption works (pycryptodome + secretstorage)
- Test: `tokenade export --browser-name chrome --domains "github.com" -o github.tokenade`

### 2.2 Edge/Brave Extraction
- Test export from Edge and Brave browsers
- Both use Chromium-based cookie encryption
- Test: `tokenade export --browser-name brave --domains "reddit.com" -o reddit.tokenade`

### 2.3 More Site Configs
- Add GitHub, Discord, Reddit, Twitter site configs
- Currently only `chatgpt.json` exists
- Each needs: domains, critical cookies, auth selectors

### 2.4 Session Load End-to-End
- Test: export → save → load into browser → verify logged in
- Test: `tokenade load -f session.tokenade --visible`

## Priority 3: Security Fixes (Medium Impact)

### 3.1 Session Sharing Encryption
**File:** `tokenade/core/importer/session_sharer.py`
- Currently base64 encodes (NOT encrypts) session data
- Anyone with the URL can decode all cookies
- Fix: Use AES encryption with password/key derivation
- Test: Share a session, verify decryption works

### 3.2 Chrome Cookie Validation
- After extraction, validate that decrypted values are readable text
- Currently may return encrypted bytes silently
- Fix: Add post-extraction validation in `cookie_extractor.py`

## Priority 4: Core Feature Testing (Medium Impact)

### 4.1 Profile Injection
- Test: `tokenade inject-profile -s session.tokenade --browser chrome --profile /path/to/profile`
- Verify cookies written to correct SQLite location

### 4.2 Health Check
- Test: `tokenade health -s session.tokenade`
- Verify expiry detection, scoring, recommendations

### 4.3 Session Refresh
- Test: `tokenade refresh -s session.tokenade`
- Verify re-export from source browser works

### 4.4 Session Merge/Rotate
- Test: merge two sessions, rotate between them
- Verify deduplication logic works

## Priority 5: Nice-to-Have (Low Impact)

### 5.1 Safari Decryption
- Currently a no-op (returns encrypted values)
- Needs actual AES implementation

### 5.2 Extension Bridge Wiring
- Bridge exists but not connected to CDP proxy
- Need to wire into proxy startup flow

### 5.3 Advanced Validation
- Test JS/screenshot/API validation rules
- Currently untested

### 5.4 Format Export/Import
- Test Playwright, Puppeteer, Netscape format conversion
- Currently untested

## Implementation Order
1. Fix forward proxy HTTPS (1.1)
2. Fix multi-site proxy (1.2)
3. Fix auto-refresh timing (1.3)
4. Test Chrome extraction (2.1)
5. Test more sites (2.2, 2.3)
6. Fix session sharing encryption (3.1)
7. Test profile injection (4.1)
8. Test health check (4.2)
9. Test session refresh (4.3)
10. Test session merge/rotate (4.4)

## Notes
- All testing should be done with real browsers and real sites
- Document results in `.agent/working.md`
- No version bumps or releases until features are confirmed working
- Commit directly to `main` for each fix/test
