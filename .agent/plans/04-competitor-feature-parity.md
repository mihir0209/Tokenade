# Phase 49: Competitor Feature Parity

## Goal
Match key features from competitors (AdsPower, Multilogin, GoLogin, Dolphin Anty) while maintaining tokenade's unique position as a session portability tool.

## Competitor Analysis Summary

### AdsPower (9M+ users)
- Dual browser engines (Chromium + Firefox)
- Full fingerprint masking (20+ parameters)
- Built-in RPA (visual drag-and-drop)
- Multi-window synchronizer
- Team collaboration
- Cloud sync
- Local API (Selenium/Puppeteer/Playwright)

### Multilogin (€29-199/mo)
- Premium fingerprinting
- Cloud profiles
- API-first design

### GoLogin ($24-99/mo)
- Cloud profiles
- Mobile fingerprints
- Free tier

### Tokenade's Unique Position
- NOT an antidetect browser — extracts REAL sessions
- Free and open source
- Self-hosted (no cloud dependency)
- TLS fingerprint matching (unique)

## Tasks

### 49.1 — Browser Profile Management
**Effort:** 3-4 days
**File:** `tokenade/core/browser/profiles.py`

- [ ] Create `BrowserProfile` dataclass (name, fingerprint, proxies, cookies)
- [ ] Create `ProfileManager` class
- [ ] Store profiles in `~/.tokenade/profiles/`
- [ ] Each profile has unique fingerprint
- [ ] CLI: `tokenade profile create|list|delete|use|export|import`
- [ ] Add tests

### 49.2 — Fingerprint Generation
**Effort:** 3-4 days
**File:** `tokenade/core/browser/fingerprint.py`

- [ ] Create `FingerprintGenerator` class
- [ ] Generate random but consistent fingerprints
- [ ] Device profile templates (Windows/Mac/Linux)
- [ ] Hardware-specific profiles (GPU, CPU, screen)
- [ ] Canvas, WebGL, audio fingerprint generation
- [ ] Font enumeration consistency
- [ ] Add tests

### 49.3 — Multi-Window Synchronizer
**Effort:** 2-3 days
**File:** `tokenade/core/browser/synchronizer.py`

- [ ] Create `WindowSynchronizer` class
- [ ] Run same actions across multiple profiles simultaneously
- [ ] CLI: `tokenade sync --profiles "p1,p2,p3" --action "navigate,url"`
- [ ] Add tests

### 49.4 — Session Import from Competitors
**Effort:** 2-3 days
**File:** `tokenade/core/importer/competitor_import.py`

- [ ] Create `CompetitorImporter` class
- [ ] Import from AdsPower (JSON export)
- [ ] Import from Multilogin (cookie export)
- [ ] Import from GoLogin (profile export)
- [ ] CLI: `tokenade import --from adspower|multilogin|gologin <file>`
- [ ] Add tests

### 49.5 — Cloud Profile Sync
**Effort:** 3-4 days
**File:** `tokenade/core/cloud/sync.py`

- [ ] Create `CloudSync` class
- [ ] Sync profiles across devices (encrypted)
- [ ] Support local server (self-hosted)
- [ ] Support GitHub Gist as backend
- [ ] CLI: `tokenade cloud sync|pull|push|status`
- [ ] Add tests

### 49.6 — API Server
**Effort:** 3-4 days
**File:** `tokenade/core/api/server.py`

- [ ] Create REST API server (Flask/FastAPI)
- [ ] Endpoints: profiles, sessions, browser control
- [ ] API key authentication
- [ ] OpenAPI/Swagger documentation
- [ ] CLI: `tokenade serve --port 8080`
- [ ] Add tests

## Verification
1. `tokenade profile create --name "test" --os windows` — creates profile
2. `tokenade profile list` — shows all profiles
3. `tokenade sync --profiles "p1,p2" --action "navigate,url=https://example.com"` — opens both
4. `tokenade import --from adspower export.json` — imports profiles
5. `tokenade serve` — starts API server
6. API call `GET /api/profiles` — returns profile list

## Dependencies
- Phase 46 (Enhanced Stealth) — for fingerprint generation
- Phase 47 (Cloudflare/Akamai) — for proxy support
