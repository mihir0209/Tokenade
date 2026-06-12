# Tokenade Feature Plans — 2025-06-12

## Priority 1 — Security Hardening (v2.1)

### 1.1 HTML Escaping in All GUI Responses
- Add `html.escape()` to all user-controlled values in HTML f-strings
- Affects: `cdp_proxy.py` (_handle_gui, _handle_page), `server.py` (_handle_gui)
- Effort: Small (1-2 hours)

### 1.2 SSRF Protection
- Add URL validation in `_handle_browse_post` and `_build_target_url`
- Block private IP ranges (10.x, 172.16-31.x, 192.168.x, 169.254.x)
- Block localhost, metadata endpoints
- Add `--allow-internal` flag for power users who need it
- Effort: Medium (3-4 hours)

### 1.3 Remove Plaintext Password Storage
- Replace `accounts.json` with `CredentialManager` (keyring-based)
- Remove `--password` CLI flags
- Use `getpass.getpass()` for interactive password input
- Add `chmod 0600` to all sensitive file writes
- Effort: Medium (4-5 hours)

### 1.4 Fix Double-Cookie Bug in TLS Path
- Remove `cookies=` parameter from `RuntimeEngine.request()` call
- Keep only the header-based cookie injection
- Add integration test to verify single cookie delivery
- Effort: Small (1 hour)

### 1.5 Remove Redundant HMAC in Encryptor
- Remove HMAC computation and verification
- Rely solely on AES-GCM authentication tag
- Maintain backward compatibility: detect HMAC in old files, strip it
- Effort: Small (2 hours)

---

## Priority 2 — Core Improvements (v2.2)

### 2.1 Page Lifecycle Management
- Add TTL to pages in `self._pages` (auto-close after 30 min idle)
- Add max page count (default: 10)
- Listen for Playwright `page.on("close")` to clean up `self._pages`
- Effort: Medium (3-4 hours)

### 2.2 Session-Aware aiohttp Client
- Create `self._http_session` with `asyncio.Lock` for thread-safe init
- Use connection pooling with proper `TCPConnector` limits
- Add session health check and reconnection logic
- Effort: Small (2 hours)

### 2.3 LocalStorage Auto-Detection
- When exporting, auto-detect which origins have localStorage data
- Prompt user: "Found localStorage for web.telegram.org. Include? [y/n]"
- Auto-set `--extract-local-storage` when localStorage is detected
- Effort: Medium (3-4 hours)

### 2.4 Proxy Auto-Detection of Session Needs
- Before navigating, check if session has `local_storage`
- If yes, inform user: "This session requires localStorage injection"
- Automatically inject and reload without user intervention
- Effort: Small (2 hours)

### 2.5 Consolidate `_copy_db` Utility
- Extract `_copy_db` to a shared utility module
- Fix WAL/SHM cleanup in `finally` block
- Use in both `cookie_extractor.py` and `local_storage_extractor.py`
- Effort: Small (1 hour)

### 2.6 Fix `infer_auth_status` False Positives
- Don't count analytics cookies (`_ga`, `_gid`, `__cf_bm`) as session cookies
- Add a blocklist of known non-auth cookies with secure+httpOnly flags
- Effort: Small (1 hour)

---

## Priority 3 — New Features (v2.3)

### 3.1 Telegram Desktop Session Export
- Extract Telegram Desktop session from `tdata/` directory
- Support both `tdata/auth_key` (old) and `tdata/user_key` (new) formats
- Export as `.tokenade` with cookies + localStorage + IndexedDB
- Effort: Large (8-10 hours)

### 3.2 Multi-Site Session Bundler
- Export multiple sites in one `.tokenade` file (already partially supported)
- Add `tokenade proxy --all` to serve all sessions simultaneously
- Each site gets its own Playwright page/context
- GUI shows tabs for each active site
- Effort: Large (10-12 hours)

### 3.3 Session Refresh/Rotation
- When cookies expire, auto-refresh by re-exporting from source browser
- Add `tokenade refresh --session telegram.tokenade --source firefox`
- Detect expiry via health check, prompt for refresh
- Effort: Medium (5-6 hours)

### 3.4 Headless Mode with Screenshots
- Already implemented (screenshot viewer)
- Add `--save-screenshots` flag to save periodically
- Add screenshot comparison to detect page state changes
- Effort: Small (2 hours)

### 3.5 HTTP Forward Proxy Mode
- Currently the proxy only works as a GUI or reverse proxy
- Add `tokenade proxy --mode forward` to act as HTTP_PROXY
- Configure browser: `HTTP_PROXY=http://127.0.0.1:9222`
- All browser traffic goes through curl-cffi with donor TLS
- Effort: Large (8-10 hours)

### 3.6 Session Comparison Tool
- `tokenade diff session1.tokenade session2.tokenade`
- Show cookie differences, localStorage differences
- Useful for debugging why a session stopped working
- Effort: Medium (3-4 hours)

### 3.7 Browser Extension
- Chrome/Firefox extension that reads cookies from the current tab
- Sends them to the Tokenade proxy server
- Eliminates need for manual export
- Effort: Very Large (20+ hours)

---

## Priority 4 — Polish & DX (v2.4)

### 4.1 Comprehensive Test Coverage
- Add encrypt/decrypt round-trip tests
- Add CLI end-to-end tests (using `click.testing.CliRunner` pattern)
- Add proxy integration tests with real Playwright
- Add SSRF protection tests
- Target: 500+ tests

### 4.2 Add `--version` Flag
- Simple `argparse` addition
- Effort: Trivial

### 4.3 Fix `_get_site_url` TLD Assumption
- Support `.co.uk`, `.com.au`, `.org`, etc.
- Use a TLD list or just return the site name without TLD
- Effort: Small

### 4.4 macOS CookieCrypto
- Implement `MacCookieCrypto` using `subprocess` to call `security find-generic-password`
- Or document limitation: "macOS export requires Chrome-based browsers only"
- Effort: Medium (4-5 hours)

### 4.5 Improve Error Messages
- Replace all `f"Error: {e}"` with user-friendly messages
- Add error codes for programmatic handling
- Effort: Medium (3-4 hours)

### 4.6 Documentation
- Architecture diagram
- API reference for programmatic usage
- Security considerations document
- Contributing guide
- Effort: Medium (4-5 hours)

---

## Implementation Order

```
v2.1 (Security)
  ├── 1.1 HTML escaping
  ├── 1.2 SSRF protection
  ├── 1.3 Remove plaintext passwords
  ├── 1.4 Fix double-cookie bug
  └── 1.5 Remove redundant HMAC

v2.2 (Core)
  ├── 2.1 Page lifecycle management
  ├── 2.2 Session-aware aiohttp
  ├── 2.3 LocalStorage auto-detection
  ├── 2.4 Proxy auto-detection
  ├── 2.5 Consolidate _copy_db
  └── 2.6 Fix auth status false positives

v2.3 (Features)
  ├── 3.1 Telegram Desktop export
  ├── 3.2 Multi-site bundler
  ├── 3.3 Session refresh
  ├── 3.4 Headless screenshots
  ├── 3.5 HTTP forward proxy
  ├── 3.6 Session comparison
  └── 3.7 Browser extension

v2.4 (Polish)
  ├── 4.1 Test coverage
  ├── 4.2 --version flag
  ├── 4.3 Fix TLD assumption
  ├── 4.4 macOS CookieCrypto
  ├── 4.5 Error messages
  └── 4.6 Documentation
```
