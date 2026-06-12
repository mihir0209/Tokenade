# Implementation Roadmap

## Phase 1: Core Infrastructure ✅ (COMPLETED)

### Browser Management
- [x] `BrowserManager` ABC with lifecycle methods
- [x] `PlaywrightBrowserManager` implementation
- [x] `BrowserConfig` dataclass with anti-detection defaults
- [x] `BrowserFactory` with auto-detection

### Cryptography
- [x] `CookieCrypto` ABC
- [x] `WindowsCookieCrypto` (DPAPI + AES-256-GCM)
- [x] `LinuxCookieCrypto` (libsecret + "peanuts" fallback)
- [x] `DecryptedCookie` standardized format
- [x] `CookieCryptoFactory` platform detection

### Fingerprinting
- [x] `BrowserFingerprint` dataclass
- [x] `FingerprintCollector` (browser + system)
- [x] `FingerprintManager` storage/retrieval

## Phase 2: Site Handlers ✅ (COMPLETED)

### Base Framework
- [x] `SiteHandler` ABC with auth, extract, inject, validate
- [x] `HandlerRegistry` for discovery
- [x] `SessionData`, `ExtractedToken`, `AuthStatus`, `TokenType`

### Google Handler
- [x] Auth status check via Labs API
- [x] OAuth token extraction
- [x] Cookie extraction and filtering
- [x] Session validation (critical cookies)
- [x] Session injection via Playwright
- [x] Automated login flow
- [x] API testing (Whisk image generation)

## Phase 3: Testing Framework ✅ (COMPLETED)

- [x] `PortabilityTester` class
- [x] `PortabilityTest` result dataclass
- [x] Session transfer testing
- [x] Fingerprint variation testing
- [x] Report generation (text + JSON)

## Phase 4: CLI & Packaging ✅ (COMPLETED)

- [x] `tokenade setup` - Account setup
- [x] `tokenade extract` - Token extraction
- [x] `tokenade transfer` - Session transfer
- [x] `tokenade test` - Portability testing
- [x] `tokenade fingerprint` - Fingerprint management
- [x] `tokenade validate` - Session validation
- [x] `setup.py` with entry points
- [x] `requirements.txt`

## Phase 5: Documentation & Cleanup (IN PROGRESS)

### Documentation
- [ ] Update README.md
- [ ] Create docs/usage.md
- [ ] Create docs/api.md
- [ ] Create docs/development.md

### Cleanup Plan
- [ ] Identify redundant scripts
- [ ] Move debug scripts to archive/
- [ ] Update .gitignore
- [ ] Create migration guide

## Phase 6: Future Enhancements (PLANNED)

### Additional Handlers
- [ ] GitHub handler
- [ ] Twitter/X handler
- [ ] Generic OAuth2 handler

### Advanced Features
- [ ] REST API server mode
- [ ] Web dashboard
- [ ] Docker support
- [ ] CI/CD integration
- [ ] Custom runtime engine for fingerprint injection

### Security Improvements
- [ ] Encrypt stored credentials
- [ ] Secure token storage (keyring integration)
- [ ] Audit logging
- [ ] Rate limiting

## Incremental Site Support Strategy

As discussed, we start with simpler sites and incrementally tackle Google:

1. **Level 1 - Simple Cookie Sites**: Sites with basic session cookies
   - Generic handler with minimal anti-bot
   
2. **Level 2 - OAuth Sites**: Standard OAuth2 flows
   - GitHub, GitLab, etc.
   
3. **Level 3 - Advanced Anti-Bot**: Fingerprint-sensitive
   - Google (current focus)
   - Netflix, etc.

4. **Level 4 - Enterprise**: Custom SSO, MFA
   - SAML, OIDC handlers
