# Phase 47: Cloudflare & Akamai Bypass

## Goal
Enable tokenade to bypass Cloudflare and Akamai anti-bot protections, which protect ~40% of top websites.

## Context
Cloudflare and Akamai use multiple detection layers:
1. IP Reputation — datacenter IPs instantly flagged
2. TLS/JA4 Fingerprinting — cipher suites, extensions, ordering
3. Canvas Fingerprint Correlation (Cloudflare May 2025) — hashes canvas output, compares to JA4
4. Session-Lifetime Heuristics (Cloudflare Oct 2025) — fresh sessions fail
5. JavaScript Challenges — browser behavior verification
6. Turnstile CAPTCHA — invisible fingerprinting + behavioral analysis

## Success Rates (Production Data)
| Defense | Tool | Success Rate |
|---------|------|-------------|
| No defense | Plain HTTP | 99%+ |
| Bot Fight Mode | curl_cffi `impersonate="chrome131"` | 94% |
| Managed Challenge | Stealth Playwright + residential proxy | 78% |
| "I'm Under Attack" | Camoufox + residential + CAPTCHA solver | 62% |

## Tasks

### 47.1 — cf_clearance Cookie Extraction
**Effort:** 2 days
**File:** `tokenade/core/browser/cloudflare.py`

- [ ] Create `CloudflareBypass` class
- [ ] Detect Cloudflare challenge pages (check for `cf_clearance` cookie)
- [ ] Extract `cf_clearance` from real browser session
- [ ] Include in session package (already handled by cookie export)
- [ ] Auto-detect Cloudflare protection on navigation
- [ ] Add tests

### 47.2 — Session Aging Implementation
**Effort:** 1-2 days
**File:** `tokenade/core/browser/stealth.py`

- [ ] Track session creation timestamp in session metadata
- [ ] Calculate session age before navigation
- [ ] If session < 5 minutes old, navigate to neutral page first
- [ ] Add configurable aging delay
- [ ] Add tests

### 47.3 — Residential Proxy Support
**Effort:** 2-3 days
**File:** `tokenade/core/proxy/residential.py`

- [ ] Create `ResidentialProxy` class (extends existing `ProxyRotator`)
- [ ] Support HTTP, HTTPS, SOCKS5 proxy protocols
- [ ] Geo-match proxy to session timezone/locale
- [ ] Add proxy health checking (already exists in `ProxyRotator`)
- [ ] Add `--residential-proxy` CLI flag
- [ ] Add tests

### 47.4 — Canvas Fingerprint Consistency
**Effort:** 1 day
**File:** `tokenade/core/browser/stealth.py`

- [ ] Generate consistent canvas hash per session
- [ ] Persist canvas seed across page loads
- [ ] Match claimed device profile (timezone, screen, GPU)
- [ ] Add tests

### 47.5 — TLS Fingerprint Matching
**Effort:** 2-3 days
**File:** `tokenade/core/browser/tls_fingerprint.py`

(Duplicate of 46.3 — included here for completeness)
- [ ] curl-cffi integration for Chrome/Firefox impersonation
- [ ] Auto-detect best target from session data
- [ ] Add tests

### 47.6 — CAPTCHA Solving Integration (Plugin)
**Effort:** 2-3 days
**File:** `~/Projects/tokenade-plugins/captcha-solve/`

- [ ] Create plugin interface for CAPTCHA solving
- [ ] Support 2Captcha, CapSolver APIs
- [ ] Auto-detect CAPTCHA presence
- [ ] Solve before session extraction
- [ ] Add to plugin marketplace

## Detection Test Sites
- https://nowsecure.nl/ — Cloudflare Turnstile
- https://www.cloudflare.com/ — Cloudflare challenge
- https://Akamai.com/ — Akamai protection
- https://www.nike.com/ — Cloudflare + Akamai
- https://www.adidas.com/ — Cloudflare

## Verification
1. Import Google cookies + search — no CAPTCHA
2. Navigate to nowsecure.nl — passes Turnstile
3. Navigate to nike.com — passes protection
4. `cf_clearance` cookie extracted and included in session export

## Dependencies
- Phase 46 (Enhanced Stealth) — must be completed first
- `curl-cffi` (optional)
