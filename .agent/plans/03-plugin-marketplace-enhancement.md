# Phase 48: Plugin Marketplace Enhancement

## Goal
Expand the plugin marketplace from 10 official plugins to a comprehensive ecosystem with new plugin types and improved discovery.

## Context
The user pivoted from session marketplace (risky — identity impersonation) to plugin marketplace (safe — extensible functionality). We already have:
- 10 official plugins in `mihir0209/tokenade-plugins`
- Plugin registry, loader, verifier, search, marketplace HTML
- 16 CLI subcommands for plugin management

## New Plugin Types Needed

### 48.1 — Stealth Plugin Type
**Effort:** 2-3 days
**File:** `tokenade/plugin/base.py`, `tokenade/core/integration/plugin_loader.py`

- [ ] Create `StealthPlugin` abstract base class
- [ ] Methods: `get_patches()`, `get_js_injections()`, `get_tls_config()`
- [ ] Auto-discover in loader (class `StealthPatch`)
- [ ] Apply stealth patches on browser launch
- [ ] Add tests

### 48.2 — Proxy Plugin Type
**Effort:** 1-2 days
**File:** `tokenade/plugin/base.py`, `tokenade/core/integration/plugin_loader.py`

- [ ] Create `ProxyPlugin` abstract base class
- [ ] Methods: `get_proxy()`, `rotate()`, `check_health()`
- [ ] Auto-discover in loader (class `ProxyProvider`)
- [ ] Integrate with existing `ProxyRotator`
- [ ] Add tests

### 48.3 — CAPTCHA Plugin Type
**Effort:** 2-3 days
**File:** `tokenade/plugin/base.py`, `tokenade/core/integration/plugin_loader.py`

- [ ] Create `CaptchaPlugin` abstract base class
- [ ] Methods: `detect_captcha(page)`, `solve_captcha(page, captcha_type)`
- [ ] Auto-discover in loader (class `CaptchaSolver`)
- [ ] Integrate with session refresh flow
- [ ] Add tests

### 48.4 — New Official Plugins
**Effort:** 3-4 days
**File:** `~/Projects/tokenade-plugins/`

Create new plugins in the plugins repo:
- [ ] `stealth-basic` — Basic JS patches (navigator.webdriver, plugins, chrome)
- [ ] `stealth-advanced` — Advanced patches (canvas, WebGL, audio)
- [ ] `proxy-socks5` — SOCKS5 proxy support
- [ ] `captcha-2captcha` — 2Captcha API integration
- [ ] `captcha-capsolver` — CapSolver API integration
- [ ] `export-curl` — Export as curl commands
- [ ] `export-python` — Export as Python requests
- [ ] `export-postman` — Export as Postman collection
- [ ] `validate-fingerprint` — Validate browser fingerprint consistency
- [ ] `session-monitor` — Monitor session health in background

### 48.5 — Plugin Marketplace Improvements
**Effort:** 2-3 days
**File:** `tokenade/cli/__init__.py`, `tokenade/core/integration/plugin_browser.py`

- [ ] Add plugin screenshots/icons support
- [ ] Add plugin documentation links
- [ ] Add "trending" sort option (downloads in last 7 days)
- [ ] Add plugin dependency resolution during install
- [ ] Add plugin compatibility check (min_version)
- [ ] Improve HTML marketplace page design
- [ ] Add tests

### 48.6 — Plugin Testing Framework
**Effort:** 2-3 days
**File:** `tokenade/plugin/testing.py`

- [ ] Create `PluginTestRunner` class
- [ ] Test plugin loading/unloading
- [ ] Test plugin hooks (before/after browser launch)
- [ ] Test plugin configuration
- [ ] Add `tokenade plugin test <name>` CLI command
- [ ] Add tests

## Plugin Ecosystem Architecture
```
tokenade-plugins/
├── marketplace.json          # Marketplace metadata
├── plugins.json              # Registry of all plugins
├── README.md                 # Documentation
├── stealth-basic/            # Basic stealth patches
├── stealth-advanced/         # Advanced stealth patches
├── proxy-socks5/             # SOCKS5 proxy support
├── captcha-2captcha/         # 2Captcha integration
├── captcha-capsolver/        # CapSolver integration
├── export-curl/              # Export as curl
├── export-python/            # Export as Python
├── export-postman/           # Export as Postman
├── validate-fingerprint/     # Fingerprint validation
├── session-monitor/          # Session health monitor
├── oauth2/                   # Existing
├── webhook-notify/           # Existing
├── session-health/           # Existing
├── cookie-export/            # Existing
├── proxy-rotate/             # Existing
├── multi-account/            # Existing
├── session-encrypt/          # Existing
├── browser-stealth/          # Existing (enhance)
├── session-share/            # Existing
└── auto-refresh/             # Existing
```

## Verification
1. `tokenade plugin search stealth` — shows stealth plugins
2. `tokenade plugin install stealth-basic` — installs and loads
3. `tokenade plugin test stealth-basic` — passes all tests
4. `tokenade plugin browse` — shows all plugins with icons

## Dependencies
- Phase 46 (Enhanced Stealth) — for stealth plugin implementation
- Phase 47 (Cloudflare/Akamai) — for CAPTCHA plugin implementation
