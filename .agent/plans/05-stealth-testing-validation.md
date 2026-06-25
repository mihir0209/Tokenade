# Phase 50: Stealth Testing & Validation

## Goal
Create automated stealth testing infrastructure to validate that tokenade passes bot detection systems.

## Context
We need to verify our stealth improvements work against real detection systems. Manual testing is unreliable; we need automated CI/CD checks.

## Detection Test Sites
| Site | What It Tests | Difficulty |
|------|--------------|------------|
| bot.sannysoft.com | Basic JS properties | Easy |
| pixelscan.net | Advanced fingerprinting | Medium |
| browserleaks.com | IP/TLS/WebRTC leaks | Medium |
| creepjs | Deep fingerprint analysis | Hard |
| nowsecure.nl | Cloudflare Turnstile | Hard |
| cloudflare.com | Cloudflare challenge | Hard |

## Tasks

### 50.1 — Stealth Test Framework
**Effort:** 2-3 days
**File:** `tokenade/tests/test_stealth.py`

- [ ] Create `StealthTestSuite` class
- [ ] Test against bot.sannysoft.com (basic checks)
- [ ] Test against pixelscan.net (advanced checks)
- [ ] Test against browserleaks.com (leak detection)
- [ ] Score calculation (0-100)
- [ ] Add tests for the framework itself

### 50.2 — Automated Detection Testing
**Effort:** 2-3 days
**File:** `tokenade/tests/test_detection.py`

- [ ] Create `DetectionTestSuite` class
- [ ] Test Cloudflare bypass (nowsecure.nl)
- [ ] Test Akamai bypass (if available)
- [ ] Test Google cookie import (search without CAPTCHA)
- [ ] Test session persistence across page loads
- [ ] Add tests

### 50.3 — Fingerprint Consistency Tests
**Effort:** 1-2 days
**File:** `tokenade/tests/test_fingerprint.py`

- [ ] Test canvas fingerprint consistency
- [ ] Test WebGL fingerprint consistency
- [ ] Test audio fingerprint consistency
- [ ] Test font enumeration consistency
- [ ] Test navigator properties consistency
- [ ] Add tests

### 50.4 — CI/CD Integration
**Effort:** 1-2 days
**File:** `.github/workflows/stealth.yml`

- [ ] Create GitHub Actions workflow
- [ ] Run stealth tests on push/PR
- [ ] Report detection scores
- [ ] Fail PR if score drops below threshold
- [ ] Add badge to README

### 50.5 — Detection Score Dashboard
**Effort:** 2-3 days
**File:** `tokenade/core/browser/dashboard.py`

- [ ] Create `DetectionDashboard` class
- [ ] Run all detection tests
- [ ] Generate HTML report
- [ ] Show score breakdown by category
- [ ] CLI: `tokenade stealth test` and `tokenade stealth report`
- [ ] Add tests

## Detection Score Categories
| Category | Weight | Tests |
|----------|--------|-------|
| JS Properties | 25% | webdriver, plugins, chrome, permissions |
| Canvas | 20% | consistency, hash stability |
| WebGL | 20% | vendor, renderer, consistency |
| TLS | 15% | JA3/JA4 fingerprint |
| IP | 10% | ASN type, reputation |
| Behavioral | 10% | mouse, scroll, timing |

## Verification
1. `tokenade stealth test` — shows score breakdown
2. `tokenade stealth report` — generates HTML report
3. CI passes with score > 80%
4. Google cookie import + search — no CAPTCHA

## Dependencies
- Phase 46 (Enhanced Stealth) — for stealth patches
- Phase 47 (Cloudflare/Akamai) — for bypass implementation
