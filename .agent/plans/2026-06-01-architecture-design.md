# Tokenade Architecture Plan

## Overview
Transform the existing ad-hoc token extraction scripts into a production-grade,
modular token shifting tool with proper abstractions, testing, and extensibility.

## Core Architecture

### 1. Browser Management Layer (`tokenade/core/browser/`)
- **BrowserManager (ABC)**: Abstract interface for browser automation
- **PlaywrightBrowserManager**: Playwright implementation with resource management
- **BrowserConfig**: Dataclass for browser launch configuration
- **BrowserFactory**: Factory pattern for creating browser instances

### 2. Cryptography Layer (`tokenade/core/crypto/`)
- **CookieCrypto (ABC)**: Platform-specific cookie encryption/decryption
- **WindowsCookieCrypto**: DPAPI + AES-256-GCM for Windows Chrome
- **LinuxCookieCrypto**: libsecret/keyring or "peanuts" fallback for Linux
- **DecryptedCookie**: Standardized cookie representation
- **CookieCryptoFactory**: Factory for platform detection

### 3. Fingerprint Management (`tokenade/core/fingerprint/`)
- **BrowserFingerprint**: Complete fingerprint dataclass
- **FingerprintCollector**: Collects fingerprints from browsers/system
- **FingerprintManager**: Storage, retrieval, and application of fingerprints

### 4. Site Handlers (`tokenade/handlers/`)
- **SiteHandler (ABC)**: Base class for all site handlers
- **HandlerRegistry**: Registry pattern for handler discovery
- **GoogleHandler**: Google Labs/Whisk/Gmail handler
- Extensible: Add GitHub, Twitter, etc. handlers

### 5. Testing Framework (`tokenade/tests/`)
- **PortabilityTester**: Tests cookie transfer across fingerprints
- **PortabilityTest**: Test result dataclass
- Fingerprint variation testing
- Session validation testing

## Data Flow

```
Source Device:
  Browser (with session) → BrowserManager → SiteHandler
  → extract_tokens() → extract_cookies() → SessionData
  → FingerprintCollector → BrowserFingerprint
  → Save to sessions/ and .fingerprints/

Target Device:
  Load SessionData + BrowserFingerprint
  → BrowserFactory.create(with fingerprint)
  → SiteHandler.inject_session()
  → PortabilityTester.validate()
  → API test if applicable
```

## Key Design Decisions

1. **Playwright as primary backend**: Most mature, handles encryption automatically
2. **Handler pattern**: Each site has unique auth flows, cookies, anti-bot measures
3. **Fingerprint matching**: Critical for Google; optional for simpler sites
4. **SessionData as interchange format**: JSON-serializable, platform-agnostic
5. **CLI-first**: Simple commands for common workflows

## Future Extensions

- Selenium backend support
- Additional site handlers (GitHub, Twitter, etc.)
- REST API server mode
- Docker containerization
- Custom runtime engine for fingerprint injection
