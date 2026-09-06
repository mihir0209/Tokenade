# Changelog

All notable changes to Tokenade will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed
- **Gateway TUI coherence** (`.agent/gateway/tui-ux.md` slice):
  - Action labels now name Active vs Dropdown Selected targets (`Select Dropdown Session`, `Open Active Session`, `Route Next and Open`, `Select Dropdown and Open`, `Lease Active or Selected`, `Release Active Lease`, `Cleanup Inactive Contexts`) plus a separate advanced `Force Cleanup` (`{"force": true}`).
  - State panel shows request file, base URL, dropdown-selected vs Gateway-active Session, routing strategy/scope/window policy, active context, and per-context page/lease detail; Lease button flips between `Lease Selected` / `Lease Active`.
  - `Open Active Session` is blocked with a warning when no active Session exists; Lease/Release fall back to the active Session instead of demanding a dropdown selection.
  - New `tokenade/tests/test_tui_gateway_coherence.py` (11 tests) pins labels, guards, and drain payloads.
- **Gateway Playwright backend**: `browser_type="playwright"` (as sent by `BrowserManagerContextFactory`) now resolves to the Playwright `chromium` backend instead of raising `AttributeError: 'Playwright' object has no attribute 'playwright'`. Verified headless on Windows with stock Playwright Chromium.

### Fixed (Windows hardening — verified on Windows, `python -m tokenade`)
- **Extension in CloakBrowser**: unpacked `extension/` loads in CloakBrowser 146 (service worker registers, `window.Tokenade` bridge injects, `getCookies` returns HttpOnly cookies, popup renders, packager round-trips). First-load service-worker cold start needs one page reload (same as stock Chromium).
- **cp1252 crashes**: UTF-8 forced for CI workflow writes (`workflow_generator`), stealth HTML/JSON reports (`browser/dashboard`), key-file reads (`encryptor.load_key_from_file`), TUI background CLI logs, and TUI screenshot saves in tests. CLI entry (`main()`) reconfigures stdout/stderr to UTF-8 on Windows.
- **`os.kill(pid, 0)` PID checks**: replaced with a Win32 OpenProcess/GetExitCodeProcess check (`core/utils/process.py`) in artifact lock reclaim (`artifacts/manager`) and daemon liveness (`daemon/session_daemon`). Dead restore locks are now reclaimed on Windows; previously they blocked restores forever.
- **Stale `C:\nonexistent` assumption**: tests using hardcoded `/nonexistent/...` paths (resolves to creatable `C:\nonexistent` on Windows) now use tmp-dir or blocker-file paths (`base_handler`, `batch`, `cli_session`, `session_sync`).
- **SQLite handle leaks**: `db_utils.copy_db` and `local_storage_extractor.extract_firefox` now close connections on every path and own temp-copy modes (0o600); fixes WinError 32 cleanup failures and hardens temp cookie copies.
- **HOME-aware paths**: new `core/utils/paths.py` (`tokenade_home()`, `expand_user()`) honors an exported `HOME` on Windows for Tokenade data dirs and `~` CLI args; wired into completions install, vault store, and sync peer sessions/config dirs. Browser-profile discovery paths intentionally still use the OS home.
- **Test isolation**: POSIX-only tests (permission bits, exec bit, `fork`, X11 paths, pywin32-absence) get `win32` skip markers; temp-file tests close handles before unlink; `echo` subprocess replaced with `sys.executable`; version-ordering made deterministic via monotonic `created_at`.
- **Marketplace drift guards**: site-handler and site-URL tests skip when the installed `generic-handler` revision ships no site catalog instead of failing on upstream plugin changes.
- **Repo hygiene**: `.gitignore` `artifacts/` rules rooted (`/artifacts/...`) — they previously shadowed the `tokenade/core/artifacts/` source package.

## [1.4.0] - 2026-08-21

### Added
- **Browser Extension Overhaul (v1.4)**:
  - **520px Sidebar Workspace UI**: Re-engineered popup with 4 dedicated navigation tabs: **Export (📤)**, **Inject (📥)**, **Inspect (🔍)**, and **Settings (⚙️)**.
  - **Bidirectional Session Injection**: Direct import and injection of `.tokenade`, Cookie-Editor JSON, and Netscape cookie files into active browser tabs with optional clean domain clearing and auto-reload.
  - **Native WebCrypto AES-256-GCM Encryption**: PBKDF2-HMAC-SHA256 (600,000 iterations) and AES-256-GCM encryption/decryption matching Python `TokenadeEncryptor` binary specification (password export & password-prompt import).
  - **Live Cookie Inspector**: Searchable and filterable cookie table for the active domain with security tags (`SEC`, `HTTP`, `SameSite`), expiration indicators, and clipboard export.
  - **Multi-Origin Web Storage Scraping**: Gathers `localStorage` and `sessionStorage` across declared site handler domains (Google, Discord, Telegram Web, X/Twitter, GitHub, ChatGPT).
  - **Proxy Gateway Bridge**: `SEND_TO_PROXY` bridge integration to push active browser sessions directly to local Tokenade Proxy Gateway (`http://127.0.0.1:9222`).
  - **WCAG AA Compliance & Theming**: Polished Dark and Light themes with WCAG AA compliant contrast ratios (>= 4.5:1) and custom styled scrollbars.
  - **Autonomous Visual Testing Harness**: Pixel-level screenshot validator (`scripts/inspect_screenshot_pixels.py`), automated layout & contrast validator (`scripts/validate_extension_ui.py`), and real-session E2E validation (`scripts/verify_extension_real_sessions.py`).
- **Plugin Architecture Refactor (CR-10)**:
  - Consolidated redundant plugin type mapping dicts into canonical `PLUGIN_TYPE_BASE_CLASSES` and `PLUGIN_TYPE_REQUIRED_METHODS` in `tokenade/plugin/base.py`.

---

## [1.3.0] - 2026-08-19

### Added
- **Anti-Bot Challenge Subsystem**:
  - `ChallengeDetectorPlugin` base with built-in Cloudflare, Akamai, and DataDome detectors.
  - `ChallengeSolverPlugin` base, `CloakBrowserAutoSolver` (stealth automated solve), and external fallback plugins (`TwoCaptchaSolverPlugin`, `CapSolverSolverPlugin`).
  - `ChallengeSolver` orchestrator for multi-tier solving (stealth-first with external fallback and post-solve verification).
  - `ChallengeGuard` for transparent navigation wrapping with automatic detect-solve-retry mitigation loops.
  - Automatic challenge mitigation wired into `PlaywrightBrowserManager.navigate()` and `OAuthAutomationPlugin`.
  - `SolvedSessionCapturer` to persist solved challenge artifacts (`cf_clearance`, Turnstile tokens, browser fingerprint) into reusable `.tokenade` session files with clearance cookie filtering and unencrypted warnings.
  - CLI flags for `tokenade load`: `--no-auto-solve`, `--capture-session`, and `--capture-dir`.
  - Comprehensive live solver and detector witness suites with artifact capturing and headless/headed modes.
- **OAuth Automation**:
  - `tokenade oauth automate` CLI for third-party authentication using donor provider sessions (Google/GitHub).
- **Extension Store Bundler**:
  - `tokenade extension bundle` CLI to package Chrome Web Store (`.zip`) and Firefox AMO (`.xpi`) distribution bundles.
- **Security & Secret Redaction**:
  - `tokenade plugin info`, `tokenade plugin configure --show`, and `tokenade config` redact sensitive secrets (`api_key`, `password`, `token`, `secret`, `encryption_password`, `supabase_anon_key`) in both human-readable and `--json` outputs.
  - `SecurityValidator.sanitize_plugin_path` applied to `PluginRegistry._install_plugin_dir` to enforce path traversal safety.
- **Shell Completions**:
  - Dynamic `tokenade completion` generation for `bash`, `zsh`, and `fish` synchronized with all visible CLI commands.
- **Plugin dependency loading**:
  - `PluginLoader` loads declared `dependencies` before their dependents — recursively and cycle-safe — for both `load_by_name` and dependency-ordered `load_all` (prerequisite plugin instances are bound before `on_load` runs).
- **Plugin CLI polish**:
  - `tokenade plugin deps <name>` prints an annotated dependency tree (version + `[OK]` / `[X] missing`), with a new `--json` cycle-safe machine-readable mode.
  - `tokenade plugin info <name>` surfaces API version, entry class, category, icon, tags, and runnable methods with the exact `tokenade run --request` invocation for run-enabled plugins.
  - `tokenade plugin list` shows runnable methods and dependency statuses in both installed and `--available` modes.
- **Marketplace** (tokenade-plugins):
  - 23 plugins across handlers, solvers, detectors, refreshers, notifications, and export formats.
  - `challenge-detectors`, `twocaptcha-solver`, `capsolver-solver`, `protected-portal-handler`, and `nowsecure-handler` plugins.
  - `generic-handler` twitter/X site catalog (`twitter.json`) and improved scoring logic.
  - Offline mock captcha API (`tokenade-plugins/tests/mock_captcha_server.py`) for free solver-path integration testing.

---

## [1.2.0] - 2026-08-10

### Added
- Transactional keyring-backed Session Vault with portable encrypted backups.
- Hash-based local/strict-SSH peer Sync with persisted three-way conflict state.
- End-to-end Vault and Sync CLI/TUI workflows.

### Removed
- Analytics collection, storage, CLI, TUI, and Python APIs.
- Unsafe mtime conflict resolution and fail-open Vault crypto.

---

## [1.1.94] - 2026-08-10

### Changed
- Moved canonical source and issue URLs to Codeberg.
- Release validation now follows each branch's configured Git upstream.

### Fixed
- Plugin integrity registration ignores generated bytecode and refreshes after updates.

---

## [1.1.93] - 2026-08-10

### Added
- First-class versioned profile artifacts with safe inspection and transactional restore.
- Core access modes: clone, exclusive move, single use, and relink required.
- `tokenade inspect` for redacted Session capability and policy reporting.
- Fail-closed cross-repository release orchestration with Cloudflare preview validation.

### Security
- Gateway, proxy, SDK, load, launch, and runtime paths now reject unsupported restricted artifacts.
- Mixed legacy/current artifact payloads fail closed.

---

## [1.1.92] - 2026-08-09

### Security
- Retracted concurrent WhatsApp linked-device cloning after outbound Signal/call state divergence was observed.
- WhatsApp profile transfer now requires an explicit exclusive-move acknowledgement and rejects legacy clone payloads.

### Fixed
- Native profile storage is no longer rewritten after browser startup, avoiding stale mutex/queue restoration.

---

## [1.1.91] - 2026-08-09

### Added
- Required Plugin metadata and fail-closed pre-launch checks for portable Sessions.
- Runtime Python/system dependency declarations and CLI readiness reporting.
- Cross-platform restoration hooks used by WhatsApp's browser-native localStorage payload.

### Fixed
- Windows WhatsApp replay no longer requires the Linux-only `plyvel` package.
- Sessions missing required Site Handlers no longer launch a browser and silently skip profile restoration.

---

## [1.1.90] - 2026-08-09

### Added
- Site Handler hooks for packaging and restoring origin-specific browser profile data.
- Pre-launch restoration used by the WhatsApp Web handler for Chromium IndexedDB and localStorage.
- Cloudflare Pages as the default plugin marketplace registry.

### Fixed
- Chromium localStorage decoding now handles its UTF-8/UTF-16 type markers.
- Web Storage is initialized before first navigation for storage-backed applications.

---

## [1.1.65] - 2026-07-20

### Added
- **Session Sync**: Synchronize sessions across machines
  - `SessionSyncer` class with push/pull/bidirectional sync
  - SSH/SCP and rsync transport backends
  - Conflict resolution (newest, oldest, local, remote)
  - File hashing for change detection
  - `sync` CLI command (hidden)
- **Session Sharing**: Share sessions via encrypted URLs and QR codes
  - `SessionSharer` class with AES-256 encryption
  - Token-based access control with expiration
  - Password protection support
  - QR code generation
  - `share` CLI command (hidden)
- **Session Vault**: Encrypted session storage with key rotation
  - `SessionVault` class with AES-256-GCM encryption
  - Automatic key rotation
  - Backup and restore
  - Integrity verification
  - `vault` CLI command (hidden)
- **Monitoring Dashboard**: Web UI for session monitoring
  - `DashboardServer` class with real-time status
  - Auto-refresh browser UI
  - Session management endpoints
  - `dashboard` CLI command (hidden)
- **Enterprise Features**: RBAC and audit logging
  - `RBACManager` with role and permission management
  - `AuditLogger` with comprehensive action tracking
  - Hierarchical roles
  - User-role assignments

### Changed
- Fixed batch operations import error (`BatchRefresher` → `ParallelBatchRefresher`)
- Added `vault` and `dashboard` commands to CLI

---

## [1.1.64] - 2026-07-20

### Added
- **google-flow-handler v1.1.0**: Multi-account OAuth support
  - `target_email` parameter for specific account selection
  - `account_index` fallback for multi-account sessions
  - `max_retries` with automatic retry logic
- **Batch operations**: Parallel batch export, load, and refresh
  - `ParallelBatchExporter` — export from multiple browsers in parallel
  - `ParallelBatchLoader` — load multiple sessions in parallel
  - `ParallelBatchRefresher` — refresh multiple sessions in parallel
- **Container support**: Docker integration
  - `Dockerfile` for building Tokenade image
  - `docker-compose.yml` for multi-service deployment
  - `container` command for Docker management
- **TUI promoted**: Terminal UI now visible in default CLI

### Changed
- Default CLI surface expanded with TUI command

---

## [1.1.63] - 2026-07-20

### Added
- **Gateway rate limiting**: `gateway.rate_limit` config with per-IP sliding window
  - `requests_per_minute` (default 60) — max requests per IP per minute
  - `burst` (default 10) — burst allowance
  - Returns `429 Too Many Requests` with `Retry-After` header when exceeded
- **Gateway docs updated**: request shape now includes `rate_limit`, `webhooks`, `state_file`

### Changed
- Gateway maturity complete: all 5 phases implemented (auto-rotation, health monitoring, persistence, webhooks, rate limiting)

---

## [1.1.62] - 2026-07-19

### Added
- Launch profile selection: `--profile NAME`, `--copy-profile`, `--use-original-profile`, `--refresh-profiles`
- Browser profile cache at `~/.tokenade/browser_paths.json` with signature-based discovery
- `TOKENADE_VERIFY_INSTALL_CLOAK=1` option for PyPI verification with CloakBrowser binary install
- Request framework examples in README (`run`, `gateway`, `proxy resolve`)
- Privacy statement for gateway output (metadata only, never cookies/storage)

### Changed
- Default safety behavior: discovered profiles copied to temp directory (not mutated)
- `.agent/` cleanup: removed stale documentation files

### Fixed
- Profile copy handles lock files gracefully
- Case-insensitive profile name matching

---

## [1.1.61] - 2026-07-18

### Added
- **Gateway control plane**: `tokenade gateway --request request.json`
  - `/status`, `/sessions`, `/route/next`, `/route/select` endpoints
  - `/contexts`, `/contexts/prewarm`, `/contexts/drain`, `/tabs/new` endpoints
  - Isolated browser contexts per session (CloakBrowser/Playwright)
- **Nested request framework**: `tokenade run --request request.json`
  - Ordered plugin execution with `roles.run`
  - Plugin config pass-through
  - Missing required plugin fail-closed with install suggestions
- **SessionRouter core**: routing strategies (round-robin, random, health-weighted, sticky)
  - Sanitized session records (no cookies/storage in output)
  - `switch_interval_seconds >= 5` enforcement
- **Source network stamp**: privacy-conscious opt-in metadata capture
- **Proxy provider resolver**: upstream proxy integration with credential redaction
- **CLI surface alignment**: `gateway` and `proxy` promoted to visible commands
- **Browser profile discovery**: signature-based detection (Firefox `cookies.sqlite`, Chromium `Preferences`)

### Changed
- `proxy` command reassigned to upstream proxy tooling (`proxy resolve --request`)
- Legacy local/CDP proxy moved to hidden `proxy legacy`
- Gateway rotation model: isolated contexts, not in-place mutation

### Fixed
- Gateway HTTP server uses single-threaded `HTTPServer` (avoids Playwright cross-thread errors)
- Gateway `/tabs/new` no longer mistakes URL for session selector

---

## [1.1.60] - 2026-07-18

### Added
- Site Handler export metadata in `.tokenade` files
- Plugin-declared storage origins for Discord/Telegram export
- `recommend()` module for site/plugin/browser suggestions
- CloakBrowser as default automation backend
- Browser profile cache for faster discovery

### Changed
- Marketplace witness scripts use env-var overrides
- Telegram witness uses strict neutral-chat URL (`https://web.telegram.org/a/#777000`)

### Fixed
- Google Flow single-account limitation documented
- Firefox Snap profile export works with running browser


## [1.0.0] - 2026-07-12

### Added
- Health-weighted session rotation (`core/refresh/session_rotator.py`)
- CI job timeouts (5 min lint/build, 10 min tests)
- Python 3.12 test matrix (Python 3.10 dropped from CI due to async CDP deadlocks)

### Fixed
- All flake8 lint errors across 9 files
- Environment-dependent tests skipped in CI (missing plugins, textual)
- Test suite: 0 failures (was 302), 71s (was 124s)

### Changed
- Consolidated session rotation/refresher into `core/refresh/`
- Renamed `stealth_test.py` to `stealth_validation.py` (production module, not test)
- Agent docs cleanup: removed 21 stale test doc files

### Removed
- Dead code: `core/antidetection/`, `core/integration/webhooks.py`
- Stale agent docs: `.agent/tests/` (19 files), `.agent/testing-reports/` (2 files)

## [1.0.0-rc] - 2026-07-09

### Added
- P0 Honesty pass: removed fake plugin metrics, corrected stealth claims
- Plugin contract CI, verified badge policy
- Handler resolve, typed injection, proxy fail-closed
- Fingerprint wrapper, test rename, mutation testing path

### Changed
- CLI split: `management.py` from 3379 to 67 lines
- curl-cffi fail-closed behavior
- Core-duplicate plugins as wrappers

## [0.9.0] - 2026-07-07

### Added
- CloakBrowser integration (stealth Chromium backend)
- Session forensics (autopsy module)
- TUI marketplace, session management views
- Plugin integration: loader, registry, browser, search, testing, verifier
- Docker/Kubernetes fleet management

### Changed
- Plugin system overhaul: `SiteHandlerPlugin` base class
- Site configs moved to plugin-owned `site_config.json`

## [0.8.0] - 2026-07-05

### Added
- Browser extension bridge (WebSocket)
- Multi-site proxy with shared connection pool
- Forward proxy (HTTP/HTTPS CONNECT tunnel)
- Session sync daemon (mtime-based change detection)
- Session health monitoring and scoring

### Changed
- CDP proxy: orchestrator pattern with specialized sub-modules
- TLS fingerprint matching via `curl-cffi`

## [0.7.0] - 2026-07-01

### Added
- AES-256-GCM session encryption (`encrypt` / `export --encrypt-password`)
- Platform-specific cookie decryption (Windows/Linux/macOS)
- Session vault (encrypted local storage)
- Batch operations (export, refresh, validate)

### Changed
- Session format v2.0 (added `tls_profile`, `fingerprint`, `metadata`)

## [0.6.0] - 2026-06-25

### Added
- CDP proxy (Playwright + curl-cffi TLS impersonation)
- Stealth scripts (WebDriver bypass, fingerprint spoofing)
- SSRF protection (private network blocking)
- Legacy proxy (aiohttp + service worker)

## [0.5.0] - 2026-06-20

### Added
- Cookie extraction from Chrome, Firefox, Brave, Edge
- `.tokenade` file format (JSON-based session packaging)
- `launch` command (system browser + session inject)
- `proxy` command (CDP reverse proxy)

## [0.1.0] - 2026-06-10

### Added
- Initial release
- Basic cookie export/import
- CLI framework
