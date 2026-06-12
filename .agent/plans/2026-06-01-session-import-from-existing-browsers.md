# Session Import/Export from Existing Browsers

**Date:** 2026-06-01
**Status:** Planned
**Priority:** High
**Owner:** Tokenade Team

## Terminology

- **Donor Device**: The device/browser that already has logged-in sessions. We *export* cookies from here.
- **Receiver Device**: The device where we want to *inject* cookies and maintain the session. We *load* cookies into here.
- **Session Package**: A `.tokenade` file containing site-specific cookies, tokens, and fingerprint data.

## Problem Statement

Currently, Tokenade requires users to log in through the tool itself (`tokenade setup`). This creates friction:
- Users already have logged-in browsers (Chrome, Firefox, Edge)
- Re-authenticating through Tokenade is redundant and time-consuming
- 2FA flows are painful to automate
- Users want to transfer sessions they *already have*

**Goal:** Allow users to export existing logged-in sessions from their browsers (donor), create a portable `.tokenade` package, and load/inject it on another device (receiver) with fingerprint matching.

## Feature Overview

### `tokenade export` (Donor Device)
1. **Discover** browser profiles automatically across platforms
2. **Extract** cookies from browser SQLite databases (with decryption)
3. **Filter** by specific site(s) — user only exports what they need
4. **Detect** auth status based on critical cookies
5. **Collect** the source browser's fingerprint for matching
6. **Package** into a portable `.tokenade` file

### `tokenade load` (Receiver Device)
1. **Read** a `.tokenade` session package
2. **Apply** target fingerprint with stealth spoofing
3. **Inject** cookies into a fresh browser context
4. **Validate** that the session is active
5. **Optionally** load into RuntimeEngine for API use

## Architecture

```
tokenade/core/importer/
├── __init__.py
├── browser_discovery.py      # Auto-detect browser profiles
├── cookie_extractor.py         # Read/decrypt cookies from browser DBs
├── session_packager.py         # Package into .tokenade format
├── session_loader.py           # Load .tokenade and inject into browser
└── formats.py                  # Cookie file format parsers (netscape, json, curl)
```

## The `.tokenade` File Format

A `.tokenade` file is a JSON file with the following structure:

```json
{
  "version": "2.0",
  "created_at": "2026-06-01T12:00:00Z",
  "source_device": {
    "browser": "chrome",
    "profile": "Default",
    "platform": "Linux",
    "hostname": "donor-pc"
  },
  "site_name": "google",
  "auth_status": "logged_in",
  "cookies": [
    {
      "name": "SID",
      "value": "...",
      "domain": ".google.com",
      "path": "/",
      "secure": true,
      "httpOnly": false,
      "sameSite": "Lax",
      "expires": 1750000000
    }
  ],
  "tokens": [],
  "fingerprint": {
    "user_agent": "Mozilla/5.0 ...",
    "screen_width": 1920,
    "screen_height": 1080,
    "platform": "Linux x86_64",
    "language": "en-US",
    "hardware_concurrency": 8,
    "device_memory": 8,
    "webgl_vendor": "Intel Inc.",
    "webgl_renderer": "Intel Iris Xe"
  },
  "metadata": {
    "extraction_method": "sqlite_direct",
    "cookie_count": 42,
    "critical_cookie_count": 5
  }
}
```

## CLI Commands

### `tokenade export` (Donor)

```bash
# List available browser profiles
tokenade export --list-profiles

# Export all logged-in sites from Chrome
tokenade export --browser-name chrome

# Export only Google session
tokenade export --browser-name chrome --site google

# Export multiple specific sites
tokenade export --browser-name chrome --site google --site github

# Export from custom browser path
tokenade export --browser-path ~/.config/google-chrome/Default

# Export from a cookies file (Netscape/JSON)
tokenade export --file-path ./cookies.txt --format netscape --site google

# Export with fingerprint collection
tokenade export --browser-name chrome --site google --collect-fingerprint

# Export to specific output file
tokenade export --browser-name chrome --site google --output google_session.tokenade
```

### `tokenade load` (Receiver)

```bash
# Load a .tokenade file into browser
tokenade load --file google_session.tokenade

# Load and validate session
tokenade load --file google_session.tokenade --validate

# Load with specific target fingerprint
tokenade load --file google_session.tokenade --fingerprint my_vps

# Load and use RuntimeEngine
tokenade load --file google_session.tokenade --runtime

# Load with custom stealth level
tokenade load --file google_session.tokenade --stealth-level maximum

# Load and test API
tokenade load --file google_session.tokenade --test-api
```

### CLI Flags Reference

#### `export` Flags

| Flag | Description | Example |
|------|-------------|---------|
| `--browser-name` | Browser name: chrome, firefox, edge, safari | `--browser-name chrome` |
| `--browser-path` | Custom path to browser profile | `--browser-path /path/to/profile` |
| `--profile` | Profile name within browser | `--profile "Profile 1"` |
| `--site` | Filter by site (repeatable) | `--site google --site github` |
| `--file-path` | Export from cookies file | `--file-path cookies.json` |
| `--format` | File format: netscape, json, curl | `--format netscape` |
| `--collect-fingerprint` | Collect source browser fingerprint | `--collect-fingerprint` |
| `--output` | Output .tokenade file path | `--output session.tokenade` |
| `--list-profiles` | List available profiles | `--list-profiles` |
| `--decrypt` | Decrypt cookies (auto-detected) | `--decrypt` |

#### `load` Flags

| Flag | Description | Example |
|------|-------------|---------|
| `--file` | Path to .tokenade file | `--file session.tokenade` |
| `--fingerprint` | Target fingerprint name | `--fingerprint my_vps` |
| `--stealth-level` | Stealth level: basic, advanced, maximum | `--stealth-level maximum` |
| `--validate` | Validate session after injection | `--validate` |
| `--runtime` | Load into RuntimeEngine | `--runtime` |
| `--test-api` | Test API after loading | `--test-api` |
| `--visible` | Show browser window | `--visible` |
| `--profile-dir` | Browser profile directory | `--profile-dir browser_data/loaded` |

## Implementation Phases

Each phase has its own test file and must pass end-to-end before proceeding.

---

### Phase 1: Browser Profile Discovery (Day 1-2)

**Component:** `tokenade/core/importer/browser_discovery.py`

**Tasks:**
- [ ] Implement `BrowserProfileDiscovery` class
- [ ] Auto-detect Chrome profiles on Windows/Linux/macOS
- [ ] Auto-detect Firefox profiles (profiles.ini parsing)
- [ ] Auto-detect Edge profiles
- [ ] Profile metadata extraction (name, path, last used)
- [ ] CLI `--list-profiles` implementation for `export`

**Test File:** `tokenade/tests/test_browser_discovery.py`

**Test Cases:**
```python
def test_discover_chrome_profiles_linux(mock_fs):
    """Test Chrome profile discovery on Linux."""
    
def test_discover_firefox_profiles_linux(mock_fs):
    """Test Firefox profile discovery on Linux."""
    
def test_discover_no_profiles():
    """Test graceful handling when no browsers found."""
    
def test_profile_metadata_extraction():
    """Test extraction of profile name, path, last used."""
    
def test_list_profiles_cli():
    """Test CLI --list-profiles output format."""
```

**Success Criteria:**
- `tokenade export --list-profiles` shows all available profiles
- All tests pass

---

### Phase 2: Site-Specific Cookie Extraction (Day 2-3)

**Component:** `tokenade/core/importer/cookie_extractor.py`

**Tasks:**
- [ ] Implement `CookieExtractor` base class with site filtering
- [ ] Chrome: Read `Cookies` SQLite database
- [ ] Chrome: Decrypt cookies using existing `CookieCrypto`
- [ ] Firefox: Read `cookies.sqlite` (plain text)
- [ ] Edge: Reuse Chrome logic
- [ ] Filter cookies by site/domain (critical for site-specific export)
- [ ] Netscape format parser
- [ ] JSON format parser

**Test File:** `tokenade/tests/test_cookie_extractor.py`

**Test Cases:**
```python
def test_extract_chrome_cookies(mock_db, mock_crypto):
    """Test Chrome cookie extraction with decryption."""
    
def test_extract_firefox_cookies(mock_db):
    """Test Firefox cookie extraction (no decryption)."""
    
def test_filter_by_site_google():
    """Test filtering cookies for google.com only."""
    
def test_filter_by_site_github():
    """Test filtering cookies for github.com only."""
    
def test_filter_multiple_sites():
    """Test filtering for multiple sites."""
    
def test_extract_no_matching_site():
    """Test graceful handling when site not found."""
    
def test_parse_netscape_format():
    """Test Netscape cookies.txt parsing."""
    
def test_parse_json_format():
    """Test JSON cookie file parsing."""
```

**Success Criteria:**
- Extract cookies from Chrome with decryption
- Filter by specific site(s)
- All tests pass

---

### Phase 3: Session Export / Packaging (Day 3-4)

**Component:** `tokenade/core/importer/session_packager.py`

**Tasks:**
- [ ] Implement `SessionPackager` class
- [ ] Site detection from cookies (match critical cookies to handlers)
- [ ] Auth status inference
- [ ] Fingerprint collection from source browser (optional)
- [ ] Package into `.tokenade` format
- [ ] Save to output path
- [ ] CLI `cmd_export()` implementation

**Test File:** `tokenade/tests/test_session_packager.py`

**Test Cases:**
```python
def test_detect_google_from_cookies():
    """Test Google site detection from critical cookies."""
    
def test_detect_github_from_cookies():
    """Test GitHub site detection from critical cookies."""
    
def test_package_google_session():
    """Test packaging Google session into .tokenade format."""
    
def test_package_with_fingerprint():
    """Test packaging with fingerprint data."""
    
def test_package_file_format():
    """Test .tokenade file structure and required fields."""
    
def test_export_cli(mock_browser, mock_extractor):
    """Test CLI export command end-to-end."""
```

**Success Criteria:**
- `.tokenade` file created with correct format
- Site detection works for Google, GitHub, Discord, Reddit
- All tests pass

---

### Phase 4: Session Load / Injection (Day 4-5)

**Component:** `tokenade/core/importer/session_loader.py`

**Tasks:**
- [ ] Implement `SessionLoader` class
- [ ] Read `.tokenade` file
- [ ] Apply target fingerprint with stealth spoofing
- [ ] Inject cookies into browser context
- [ ] Validate session (check auth status)
- [ ] Load into RuntimeEngine (optional)
- [ ] CLI `cmd_load()` implementation

**Test File:** `tokenade/tests/test_session_loader.py`

**Test Cases:**
```python
def test_load_tokenade_file():
    """Test reading .tokenade file."""
    
def test_inject_cookies_into_browser(mock_browser):
    """Test cookie injection into browser."""
    
def test_apply_target_fingerprint():
    """Test applying target fingerprint with stealth."""
    
def test_validate_session_after_injection(mock_browser):
    """Test session validation after injection."""
    
def test_load_into_runtime(mock_engine):
    """Test loading into RuntimeEngine."""
    
def test_load_cli(mock_browser_factory):
    """Test CLI load command end-to-end."""
```

**Success Criteria:**
- `.tokenade` file loaded and cookies injected
- Session validated after injection
- All tests pass

---

### Phase 5: End-to-End Integration (Day 5-6)

**Tasks:**
- [ ] Full donor → receiver workflow test
- [ ] `tokenade export --site google` → `tokenade load --file` pipeline
- [ ] Add `cmd_export()` and `cmd_load()` to `tokenade/cli.py`
- [ ] Update README.md with export/load documentation
- [ ] Update `tokenade/__init__.py` exports
- [ ] Integration tests

**Test File:** `tokenade/tests/test_importer_integration.py`

**Test Cases:**
```python
def test_export_load_roundtrip():
    """Test full export → load roundtrip."""
    
def test_export_site_specific_only():
    """Test that only specified site cookies are exported."""
    
def test_load_with_fingerprint_spoofing():
    """Test load with fingerprint matching and stealth."""
    
def test_export_load_cli_integration():
    """Test CLI export and load commands together."""
```

**Success Criteria:**
- Full donor → receiver workflow works
- Site-specific export only includes requested site cookies
- All tests pass (target: 220+ total)

## Technical Details

### Cookie Decryption Strategy

| Browser | Platform | Encryption | Approach |
|---------|----------|------------|----------|
| Chrome | Windows | DPAPI + AES-GCM | Reuse `WindowsCookieCrypto` |
| Chrome | Linux | AES-GCM ("peanuts" or libsecret) | Reuse `LinuxCookieCrypto` |
| Chrome | macOS | Keychain + AES-GCM | Extend `CookieCrypto` for macOS |
| Firefox | All | None (plain text) | Direct SQLite read |
| Edge | Windows | DPAPI + AES-GCM | Same as Chrome |

### Site Detection Logic

```python
SITE_DETECTION = {
    "google": {
        "domains": ["google.com", "accounts.google.com", "mail.google.com", "labs.google.com"],
        "critical_cookies": ["SID", "SSID", "APISID", "SAPISID", "HSID", "__Secure-1PSID"],
    },
    "github": {
        "domains": ["github.com", ".github.com"],
        "critical_cookies": ["user_session", "__Host-user_session_same_site"],
    },
    "discord": {
        "domains": ["discord.com", "discordapp.com"],
        "critical_cookies": ["__dcfduid", "__sdcfduid", "authorization"],
    },
    "reddit": {
        "domains": ["reddit.com", "www.reddit.com"],
        "critical_cookies": ["reddit_session", "token"],
    },
}
```

## User Experience Flow

### Donor Device: Export
```bash
# User has Chrome with logged-in Google account
$ tokenade export --browser-name chrome --site google
🔍 Discovering Chrome profiles...
📁 Found 3 profiles: Default, Profile 1, Profile 2
🍪 Extracting cookies from "Default"...
🔓 Decrypting 247 cookies...
🎯 Filtering for site: google
📦 Found 42 Google cookies (5 critical)
🔍 Collecting browser fingerprint...
💾 Exported: google_session.tokenade
   Site: google
   Cookies: 42
   Fingerprint: collected
```

### Receiver Device: Load
```bash
$ tokenade load --file google_session.tokenade --fingerprint my_vps
📂 Loading session package...
🛡️  Applying fingerprint "my_vps" with stealth level: maximum
🚀 Launching browser...
✅ Stealth injection verified
🍪 Injecting 42 cookies...
🔍 Validating session...
✅ Session valid: user@example.com
💾 Profile saved to: browser_data/loaded
```

### Receiver Device: Runtime
```bash
$ tokenade load --file google_session.tokenade --runtime
📂 Loading session package...
⚡ Loading into RuntimeEngine...
🔍 Validating session via API...
✅ Session valid: user@example.com
🚀 RuntimeEngine ready for API calls
```

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Browser DB locked while running | High | Copy DB to temp file before reading |
| Cookie decryption fails | High | Graceful fallback, report which cookies failed |
| Wrong site detection | Medium | Allow manual override with `--site` |
| Profile path variations | Medium | Extensive path list, user override via `--browser-path` |
| macOS Keychain permissions | Medium | Document permission grant, fallback to "peanuts" |
| Exported cookies expire | Low | Include expiry info, warn user |

## Success Criteria

- [ ] `tokenade export --list-profiles` works on Windows/Linux/macOS
- [ ] `tokenade export --site google` exports only Google cookies
- [ ] Chrome cookie extraction with decryption on all platforms
- [ ] Firefox cookie extraction on all platforms
- [ ] Automatic site detection for Google, GitHub, Discord, Reddit
- [ ] `.tokenade` file format is valid and portable
- [ ] `tokenade load --file` injects cookies successfully
- [ ] `tokenade load --file --fingerprint` applies stealth spoofing
- [ ] `tokenade load --file --runtime` creates working RuntimeEngine
- [ ] Full donor → receiver workflow tested end-to-end
- [ ] >80% test coverage for importer module
- [ ] Documentation updated in README.md
- [ ] All tests passing (target: 220+ tests)

## Estimated Effort

- **Phase 1 (Discovery):** 2 days
- **Phase 2 (Extraction):** 2 days
- **Phase 3 (Export/Packaging):** 2 days
- **Phase 4 (Load/Injection):** 2 days
- **Phase 5 (Integration):** 2 days
- **Total:** 10 days

## Notes

- Start with Chrome on Linux (easiest path, existing crypto)
- Firefox has no encryption, so it's the simplest to implement
- The `--site` filter is critical — users should never export all cookies
- `.tokenade` files should be treated as sensitive (contain session data)
- Consider adding encryption for `.tokenade` files in future
