# Changelog

All notable changes to Tokenade will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
