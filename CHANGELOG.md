# Changelog

All notable changes to Tokenade will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added — Plugin Ecosystem (Phases 0-10)

**Core infrastructure:**
- Event bus (sync/async, priority, thread-safe) -- core/events/
- Shared context (4 namespaces: sessions, plugins, config, runtime + TaskTracker) -- core/context/
- Plugin registry system (GitHub-hosted, multi-registry, priority ordering) -- core/integration/plugin_registry.py
- Plugin loader (DISCOVERED -> LOADED -> CONFIGURED -> ACTIVE -> FAILED lifecycle, hooks, reload w/ config preservation) -- core/integration/plugin_loader.py
- Dependency resolution (topological sort, DFS cycle detection, depth limit 5, semver) -- core/integration/dependency_graph.py, dependency_resolver.py
- Plugin config system (schema validation, env_var constraints, global config merging) -- core/integration/plugin_config.py
- Plugin testing framework (8 contract tests) -- core/integration/plugin_testing.py
- Plugin verifier (checksum-based integrity) -- core/integration/plugin_verifier.py

**5 plugin types:**
- SiteHandlerPlugin -- Override site-specific cookie extraction/injection
- SessionRefreshPlugin -- Refresh sessions via OAuth/browser
- ProxyProviderPlugin -- Provide rotating proxies
- CaptchaPlugin -- Solve CAPTCHAs (image/reCAPTCHA/hCaptcha)
- NotificationPlugin -- Webhook/email alerts for events

**CLI updates:**
- --no-plugin flag on launch, refresh-browser, accounts refresh (opt-out)
- Auto-discovery of handlers/refreshers by default (no flag needed)
- tokenade plugin deps <name> -- Show dependency tree
- tokenade plugin check-deps [name] -- Check missing/circular/depth violations
- tokenade plugin configure <name> -- --show/--set/--reset/--validate
- tokenade plugin test [--verbose] [name] -- Run contract tests
- tokenade plugin list now shows lifecycle state + health
- tokenade plugin info <name> now shows lifecycle, config, health, error

**TUI updates:**
- Registries tab -- Add/remove/enable/disable/prioritize registries
- Plugin health visualization (healthy / unhealthy)
- Plugin config visualization (sensitive values redacted)
- Plugin task visualization (active/recent tasks)
- Reload/Configure buttons on installed plugins
- Plugin detail screen shows lifecycle state + health

**Handler conversions:**
- Google/GitHub/GenericOAuth2 adapters -> SiteHandlerPlugin
- site_config.json files for domain/cookie filtering
- GitHub handler registered with HandlerRegistry
- OAuth2Plugin converted to SessionRefreshPlugin
- PluginCaptchaSolver adapter bridges CaptchaPlugin -> CaptchaSolver

**Documentation:**
- docs/plugin-api.md -- Full API reference (base classes, events, context, types)
- docs/plugin-user-guide.md -- Install, manage, configure, troubleshoot
- 5 example plugins in examples/plugins/ (site-handler, proxy-provider, captcha-solver, notifier, refresh)

### Changed
- System works WITHOUT plugins -- plugins override/extend defaults
- Plugins run by default -- --no-plugin flag to exclude (was opt-in)
- --plugin flag still works for explicit selection (backward compatible)
- Latest version wins for dependency version conflicts (major mismatch = rejected)
- No plugin sandboxing (full trust model)
- Registry management primarily through TUI

### Removed
- ProxyPlugin (replaced by ProxyProviderPlugin)


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
