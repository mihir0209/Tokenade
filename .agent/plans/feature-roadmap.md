# Tokenade Feature Plans — Updated 2026-06-14 (v3.4.0)

## Priority 1 — Security Hardening (v2.1)

### 1.1 HTML Escaping in All GUI Responses ✅
- `html.escape()` applied to all GUI HTML values in `cdp_proxy.py` and `server.py`

### 1.2 SSRF Protection ✅
- `_is_safe_url()` blocks private IPs, localhost, metadata endpoints
- Applied to both `cdp_proxy.py` and `server.py` browse handlers and reverse proxy catch-all

### 1.3 Remove Plaintext Password Storage
- Replace `accounts.json` with `CredentialManager` (keyring-based)
- Remove `--password` CLI flags
- Use `getpass.getpass()` for interactive password input
- Effort: Medium (4-5 hours)

### 1.4 Fix Double-Cookie Bug in TLS Path ✅
- Removed redundant `cookies=` parameter from `RuntimeEngine.request()`
- Cookies are already injected via the `cookie` header in `_prepare_request()`

### 1.5 Remove Redundant HMAC in Encryptor
- Remove HMAC computation and verification
- Rely solely on AES-GCM authentication tag
- Maintain backward compatibility: detect HMAC in old files, strip it
- Effort: Small (2 hours)

---

## Priority 2 — Core Improvements (v2.2) ✅

### 2.1 Page Lifecycle Management ✅
- TTL (1 hour), max 20 pages, auto-cleanup of expired/oldest pages

### 2.2 Session-Aware aiohttp Client ✅
- `asyncio.Lock()` for thread-safe session creation
- Connection pooling with `TCPConnector` limits

### 2.3 LocalStorage Auto-Detection ✅
- Auto-detect and hint when localStorage exists for cookie domains during export

### 2.4 Proxy Auto-Detection of Session Needs ✅
- Proxy auto-injects localStorage after navigation when session has `local_storage` data

### 2.5 Consolidate `_copy_db` Utility ✅
- Shared `db_utils.copy_db()` used by both extractors
- WAL/SHM cleanup in `finally` blocks

### 2.6 Fix `infer_auth_status` False Positives ✅
- Blocklist of 25+ known non-auth cookies (`_ga`, `_gid`, `__cf_bm`, etc.)

---

## Priority 3 — New Features (v2.3)

### 3.1 ~~Telegram Desktop Session Export~~ — REMOVED
- Removed: site-specific feature, tool is site-agnostic by design

### 3.2 Multi-Site Session Bundler ✅
- `tokenade proxy --all -d ./sessions/` serves multiple sessions with tabbed GUI
- Effort: Large (10-12 hours)

### 3.3 Session Refresh/Rotation ✅
- `tokenade refresh --session X --source-browser firefox` already works
- Uses `SessionRefresher` class for re-export from source browser

### 3.4 Headless Mode with Screenshots ✅
- Screenshot-based page viewer implemented
- Replaces broken srcdoc iframe approach

### 3.5 HTTP Forward Proxy Mode ✅
- `tokenade proxy --mode forward` acts as HTTP_PROXY
- All traffic goes through curl-cffi with donor TLS fingerprint + cookies
- Configure: `HTTP_PROXY=http://127.0.0.1:9223`

### 3.6 Session Comparison Tool ✅
- `tokenade diff file1.tokenade file2.tokenade [-v]`
- Compares cookies, localStorage, metadata
- Shows added/removed/modified items

### 3.7 Browser Extension
- Chrome/Firefox extension that reads cookies from the current tab
- Sends them to the Tokenade proxy server
- Effort: Very Large (20+ hours)

---

## Priority 4 — Polish & DX (v2.4) ✅

### 4.1 Comprehensive Test Coverage ✅
- 1010 tests passing (7 skipped)
- SSRF protection tests added
- CLI end-to-end tests added

### 4.2 Add `--version` Flag ✅
- `tokenade --version` shows current version

### 4.3 Fix `_get_site_url` TLD Assumption ✅
- Infers domain from cookie data instead of hardcoding `.com`

### 4.4 macOS CookieCrypto ✅
- `MacCookieCrypto` using Keychain access
- `b"peanuts"` fallback for unencrypted cookies
- Factory properly detects `sys.platform == "darwin"`

### 4.5 Improve Error Messages ✅
- All `f"Error: {e}"` replaced with generic messages in both proxies
- Exception details logged server-side only

### 4.6 Documentation ✅
- Security considerations document (`docs/SECURITY.md`)
- Competitor comparison (`docs/competitor-comparison.md`)
- Feature roadmap updated

### 4.7 Competitor Research ✅
- Analyzed EditThisCookie, Cookie-Editor, CookieJar, Session Buddy, Flare, Sharrr, Clony
- Created comparison document with market positioning
- Updated README with competitive advantages

---

## Priority 5 — Next Features (v2.5) ✅

### 5.1 Browser Extension ✅
- Chrome/Firefox extension that reads cookies from the current tab
- Sends them to the Tokenade proxy server
- Context menu integration
- `window.Tokenade` API for web pages
- Location: `extension/` directory

### 5.2 Session Auto-Refresh ✅
- `SessionRefresher` monitors cookie expiry during proxy operation
- Logs warnings for expired/expiring cookies
- Auto-refresh from source browser if enabled
- Hot-reload session without restarting proxy
- CLI: `tokenade proxy --auto-refresh --source-browser firefox`
- API: `/session/status`, `/session/refresh`

### 5.3 Session Sharing ✅
- `SessionSharer` creates shareable encrypted links
- Time-limited links (configurable expiry)
- Usage-limited links (optional max uses)
- Password protection (optional)
- QR code generation for mobile transfer
- Self-contained links (no server needed)
- CLI: `tokenade share`, `tokenade unshare`

### 5.4 Advanced Validation Rules ✅
- `AdvancedValidator` with custom validation rules
- JavaScript validation scripts
- Visual regression testing (screenshot comparison)
- API endpoint validation
- Cookie presence/value checks
- URL redirect validation
- DOM element presence checks
- CLI: `tokenade validate-rules`

### 5.5 Multi-Session Management ✅
- `SessionManager` for managing multiple sessions
- `tokenade sessions list` - list all available sessions
- `tokenade sessions merge` - combine multiple sessions
- `tokenade sessions rotate` - rotate between sessions
- `tokenade sessions stats` - show aggregate statistics
- Filter by site, browser, cookie count, etc.

---

## Priority 6 — Future Features (v2.6+)

### 6.1 Session Auto-Refresh Improvements ✅
- WebSocket notifications for real-time expiry alerts
- Multiple source browser fallback
- Session history tracking

### 6.2 Advanced Sharing Features ✅
- Share via email (SMTP integration)
- Share via webhook (Slack, Discord, etc.)
- Session versioning and rollback

### 6.3 Enterprise Features ✅
- Session audit logging (`AuditLogger` — JSONL structured logs, query, rotate)
- Role-based access control (`RoleManager` — admin/editor/viewer, persistent storage)
- LDAP/SSO integration (`LDAPAuthenticator` — bind auth, group membership, graceful fallback)

### 6.4 Performance Optimizations ✅
- Connection pooling for multi-site proxy (`SharedConnectionPool`)
- Session caching with LRU eviction (`SessionPackager` cache)
- Parallel cookie extraction (`ParallelExtractor` with correct API)

### 6.5 Integration Features ✅
- GitHub Actions CI/CD (`ci.yml` — lint, test matrix, security, build)
- Docker build & publish (`docker.yml` — GHCR push with semver tags)
- Release automation (`release.yml` — GitHub releases with artifacts)
- Docker session management (`DockerSessionManager` — container lifecycle, batch, cleanup)
- Kubernetes sidecar mode (`KubernetesManager` — Deployment, Service, ConfigMap, sidecar YAML generation)

### 6.6 Advanced Browser Support ✅
- Safari cookie extraction (`SafariExtractor` — binary cookie parser, Keychain fallback)
- Tor Browser support (`TorExtractor` — cross-platform profile discovery)
- Mobile browser support via ADB (`ADBExtractor` — Chrome/Firefox on Android)

---

## Implementation Order

```
v2.1 (Security) ✅
  ├── 1.1 HTML escaping ✅
  ├── 1.2 SSRF protection ✅
  ├── 1.3 Remove plaintext passwords ✅
  ├── 1.4 Fix double-cookie bug ✅
  └── 1.5 Remove redundant HMAC ✅

v2.2 (Core) ✅
  ├── 2.1 Page lifecycle management ✅
  ├── 2.2 Session-aware aiohttp ✅
  ├── 2.3 LocalStorage auto-detection ✅
  ├── 2.4 Proxy auto-detection ✅
  ├── 2.5 Consolidate _copy_db ✅
  └── 2.6 Fix auth status false positives ✅

v2.3 (Features) ✅
  ├── 3.1 ~~Telegram Desktop export~~ (removed - site-specific)
  ├── 3.2 Multi-site bundler ✅
  ├── 3.3 Session refresh ✅
  ├── 3.4 Headless screenshots ✅
  ├── 3.5 HTTP forward proxy ✅
  ├── 3.6 Session comparison ✅
  └── 3.7 Browser extension ✅

v2.4 (Polish) ✅
  ├── 4.1 Test coverage (406 tests, 2 skipped) ✅
  ├── 4.2 --version flag ✅
  ├── 4.3 Fix TLD assumption ✅
  ├── 4.4 macOS CookieCrypto ✅
  ├── 4.5 Error messages ✅
  └── 4.6 Documentation ✅

v2.5 (Advanced Features) ✅
  ├── 5.1 Browser extension ✅
  ├── 5.2 Session auto-refresh ✅
  ├── 5.3 Session sharing ✅
  ├── 5.4 Advanced validation rules ✅
  └── 5.5 Multi-session management ✅

v2.6+ (Future)
  ├── 6.1 Session auto-refresh improvements ✅
  ├── 6.2 Advanced sharing features ✅
  ├── 6.3 Enterprise features ✅
  ├── 6.4 Performance optimizations ✅
  ├── 6.5 Integration features ✅
  └── 6.6 Advanced browser support ✅

v3.0 (Dev Tooling) ✅
  ├── Version bump to 3.0.0 ✅
  ├── README overhaul ✅
  ├── pyproject.toml migration ✅
  ├── conftest.py shared fixtures ✅
  └── Makefile + dev tooling ✅

v3.1 (Security & Multi-Format) ✅
  ├── Fix XSS in server.py error responses ✅
  ├── Remove dead code in server.py ✅
  ├── Fix BrowserFingerprint.to_dict() ✅
  ├── Fix plaintext password leak in to_dict() ✅
  ├── Sync requirements.txt ✅
  ├── Remove setup.py (migrate to pyproject.toml) ✅
  ├── Fix bare except clauses (5 locations) ✅
  ├── Fix SSL disabled in ConnectionPool ✅
  ├── Replace MD5 with SHA-256 ✅
  ├── Remove hostname from session metadata ✅
  ├── Playwright storageState export ✅
  ├── Puppeteer/CDP cookie export ✅
  ├── Netscape/curl format export ✅
  ├── HTTP cookie header export ✅
  ├── Format auto-detection import ✅
  ├── CDP artifact removal ✅
  ├── Behavioral signal injection ✅
  └── Plugin registry (GitHub raw content) ✅

v3.2 (Session Lifecycle) ✅
  ├── OWASP-based session health scoring ✅
  ├── Session vault (ACLs, versioning, expiry) ✅
  ├── Session rotation (login/logout detection) ✅
  └── Comprehensive tests (883 total) ✅

v3.3 (CLI & Testing) ✅
  ├── CLI refactoring (1800 lines → 9 modules) ✅
  ├── Color output (success/error/warning/info) ✅
  ├── Configuration file (~/.tokenade/config.json) ✅
  ├── Shell completion (bash/zsh/fish) ✅
  ├── Property-based testing (hypothesis) ✅
  ├── Performance benchmarks ✅
  ├── Comprehensive integration tests ✅
  └── 969 tests total ✅

v3.4 (Browser & Ecosystem) ✅
  ├── Safari Keychain decryption ✅
  ├── Chromium fork detection (Arc, Opera, Vivaldi, Brave) ✅
  ├── Mobile extraction (Android ADB, iOS Safari) ✅
  ├── Extension-Proxy WebSocket bridge ✅
  ├── REST API server ✅
  ├── Python SDK ✅
  ├── Enhanced webhooks (Slack, Discord, Teams, Telegram) ✅
  └── 1010 tests total ✅
```
