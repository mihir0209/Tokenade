# Phase 46: Enhanced Browser Stealth

## Goal
Make tokenade's browser automation pass modern bot detection systems (Cloudflare, Akamai, PerimeterX, DataDome).

## Context
Current `playwright-stealth` Python package patches ~12 JS properties. Modern detection checks 40+ properties. We need to close the gap.

## Detection Layers (2026)
| Layer | What It Checks | Status |
|-------|---------------|--------|
| IP Reputation | ASN type, datacenter range | ❌ Not handled |
| Browser Fingerprint | Canvas, WebGL, audio, fonts | ⚠️ Partial (12/40+ properties) |
| Behavioral Analysis | Mouse curves, scroll, timing | ❌ Not handled |
| TLS Fingerprinting | JA3/JA4 hash, cipher order | ❌ Not handled |
| Active Challenges | CAPTCHA, JS puzzles, Turnstile | ❌ Not handled |

## Tasks

### 46.1 — Integrate `playwright-stealth` Python Package
**Effort:** 1 day
**File:** `tokenade/core/browser/stealth.py`

- [ ] Add `playwright-stealth` as optional dependency in `pyproject.toml`
- [ ] Create `BrowserStealth` class that wraps the library
- [ ] Apply stealth patches in CDP proxy startup
- [ ] Make it configurable (enable/disable individual patches)
- [ ] Add tests

### 46.2 — Critical JS Patches (7 patches that matter in 2026)
**Effort:** 2-3 days
**File:** `tokenade/core/browser/stealth.py`

Patches to add beyond `playwright-stealth`:
- [ ] `window.chrome.loadTimes()` and `window.chrome.csi()` methods
- [ ] WebGL2 rendering context support
- [ ] `iframe.contentWindow` consistency
- [ ] Worker scope consistency (Web Workers see same patched values)
- [ ] `Function.prototype.toString` integrity
- [ ] Canvas fingerprint consistency within session
- [ ] `navigator.permissions.query` fix for notification permission

### 46.3 — TLS Fingerprint Matching via curl-cffi
**Effort:** 2-3 days
**File:** `tokenade/core/browser/tls_fingerprint.py`

- [ ] Add `curl-cffi` as optional dependency
- [ ] Create `TLSFingerprint` class
- [ ] Support Chrome 131+ and Firefox 128+ impersonation targets
- [ ] Auto-detect best target from session data
- [ ] Apply TLS fingerprint to Playwright browser context
- [ ] Add tests

### 46.4 — System Dependency Installer
**Effort:** 1-2 days
**File:** `tokenade/core/browser/dependencies.py`

- [ ] Create `check_system_dependencies()` function
- [ ] Detect missing packages on Linux (libgtk-3-0, libnspr4, libpango-1.0-0, etc.)
- [ ] Create `install_dependencies()` with sudo support
- [ ] Add `tokenade deps check` and `tokenade deps install` CLI commands
- [ ] Auto-check before browser launch
- [ ] Add tests

### 46.5 — Canvas Fingerprint Consistency
**Effort:** 1 day
**File:** `tokenade/core/browser/stealth.py`

- [ ] Generate consistent canvas hash per session
- [ ] Persist canvas seed across page loads
- [ ] Match claimed device profile (timezone, screen, GPU)
- [ ] Add tests

### 46.6 — Session Aging
**Effort:** 1 day
**File:** `tokenade/core/browser/stealth.py`

- [ ] Track session creation time
- [ ] Simulate aged session behavior (don't solve challenges instantly)
- [ ] Pre-navigate to neutral pages before challenge
- [ ] Add tests

## Detection Test Sites
- https://bot.sannysoft.com/
- https://pixelscan.net/
- https://browserleaks.com/
- https://abrahamjuliot.github.io/creepjs/

## Verification
1. `tokenade launch --headless` + navigate to bot.sannysoft.com — all green
2. `tokenade launch --headless` + navigate to pixelscan.net — score > 80%
3. Google cookie import + search — passes without CAPTCHA
4. Cloudflare-protected site — passes managed challenge

## Dependencies
- `playwright-stealth` (optional)
- `curl-cffi` (optional)
