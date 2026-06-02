# Tokenade v2.0 - Production-Grade Token Shifting Tool

A secure, modular tool for extracting, transferring, and testing browser sessions
and authentication tokens across devices with fingerprint matching.

## Features

- **Multi-Account Support**: Manage up to 26 accounts per site
- **Cross-Platform**: Windows, Linux, macOS support
- **Session Import/Export**: Extract sessions from existing browsers into portable `.tokenade` format
- **Fingerprint Matching**: Maintain session continuity across devices
- **Fingerprint Spoofing Runtime**: JavaScript injection to spoof browser fingerprints at runtime
- **Site Handlers**: Extensible architecture for different sites
- **Portability Testing**: Validate if sessions work on target devices
- **Production-Grade**: Proper logging, error handling, resource management

## Architecture

```
tokenade/
├── core/
│   ├── browser/          # Browser automation abstractions
│   │   └── manager.py    # BrowserManager, BrowserConfig, BrowserFactory
│   ├── crypto/           # Cross-platform cookie encryption
│   │   └── cookie_crypto.py  # Windows/Linux crypto handlers
│   ├── fingerprint/      # Browser fingerprint management
│   │   └── manager.py    # Fingerprint collection and matching
│   ├── importer/         # Session import/export (NEW in v2.0)
│   │   ├── browser_discovery.py  # Discover browser profiles
│   │   ├── cookie_extractor.py   # Extract cookies from browsers
│   │   ├── session_packager.py   # Package into .tokenade format
│   │   └── session_loader.py     # Load .tokenade into browser
│   └── extractor/        # Token extraction utilities
├── handlers/             # Site-specific handlers
│   ├── base.py           # SiteHandler ABC and registry
│   └── google.py         # Google Labs/Whisk/Gmail handler
├── tests/                # Testing framework
│   └── portability.py    # Portability testing
├── cli.py                # Main CLI entry point
└── __init__.py           # Package exports
```

## Installation

```bash
# Clone repository
git clone https://github.com/mihir0209/tokenade.git
cd tokenade

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Install package
pip install -e .
```

### Platform-Specific Dependencies

**Windows:**
```bash
pip install pywin32
```

**Linux:**
```bash
pip install secretstorage
```

## Quick Start

### 1. Setup Accounts

```bash
tokenade setup
```

This will:
- Launch a visible browser for manual login
- Save session to `browser_data/{account_number}/`
- Store account info in `accounts.json`

### 2. Extract Tokens

```bash
# Headless extraction
tokenade extract

# Visible browser
tokenade extract --visible
```

Extracts:
- OAuth access tokens
- Session cookies
- Saves to `sessions/` directory

### 3. Test Portability

```bash
# Test with specific fingerprint
tokenade test -s sessions/google_1.json --target-fp my_vps

# Test fingerprint variations
tokenade test -s sessions/google_1.json --variations

# Test with API call
tokenade test -s sessions/google_1.json --test-api
```

### 4. Transfer Session

```bash
tokenade transfer -s sessions/google_1.json -f my_vps -p browser_data/transfer
```

### 5. Export Session from Existing Browser (NEW)

```bash
# List available browser profiles
tokenade export --list-profiles

# Export from Chrome
tokenade export --browser-name chrome --site google --output google_session.tokenade

# Export from specific profile
tokenade export --browser-name chrome --profile "Profile 1" --site google

# Export from cookies file
tokenade export --file-path cookies.txt --format netscape --site google
```

### 6. Load Session into Browser (NEW)

```bash
# Basic load
tokenade load --file google_session.tokenade

# Load with fingerprint matching
tokenade load --file google_session.tokenade --fingerprint my_vps

# Load with validation
tokenade load --file google_session.tokenade --validate

# Load with visible browser
tokenade load --file google_session.tokenade --visible
```

### 7. Manage Fingerprints

```bash
# List fingerprints
tokenade fingerprint list

# Collect from current browser
tokenade fingerprint collect -n my_pc

# Show details
tokenade fingerprint show -n my_pc
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `tokenade setup` | Setup accounts with initial login |
| `tokenade extract` | Extract tokens from saved sessions |
| `tokenade transfer` | Transfer session to another device |
| `tokenade test` | Test session portability |
| `tokenade fingerprint` | Manage browser fingerprints |
| `tokenade validate` | Validate stored sessions |
| `tokenade export` | Export session from existing browser to `.tokenade` |
| `tokenade load` | Load `.tokenade` file into browser |

## Site Handlers

### Google Handler

Handles Google Labs/Whisk API tokens and Gmail sessions.

```python
from tokenade import BrowserFactory, BrowserConfig
from tokenade.handlers.google import GoogleHandler

config = BrowserConfig(headless=True, user_data_dir="browser_data/1")
browser = BrowserFactory.create(**config.__dict__)
browser.launch()

handler = GoogleHandler(browser)
session = handler.get_session()

print(f"Auth status: {session.auth_status}")
print(f"Tokens: {len(session.tokens)}")
print(f"Cookies: {len(session.cookies)}")

browser.close()
```

### Creating Custom Handlers

```python
from tokenade.handlers.base import SiteHandler, AuthStatus, TokenType, ExtractedToken

class MySiteHandler(SiteHandler):
    SITE_NAME = "mysite"
    DOMAINS = ["mysite.com"]
    LOGIN_URL = "https://mysite.com/login"
    
    def check_auth_status(self):
        # Implementation
        pass
    
    def extract_tokens(self):
        # Implementation
        pass
    
    def extract_cookies(self):
        # Implementation
        pass
    
    def validate_session(self, cookies):
        # Implementation
        pass
    
    def inject_session(self, session_data):
        # Implementation
        pass

# Register handler
from tokenade.handlers.base import HandlerRegistry
HandlerRegistry.register(MySiteHandler)
```

## Session Import/Export (NEW in v2.0)

Tokenade now supports importing sessions from existing browsers and exporting them to a portable `.tokenade` format.

### How It Works

1. **Discover** browser profiles on the source device
2. **Extract** cookies from the browser's cookie database
3. **Package** cookies into `.tokenade` format with metadata
4. **Load** `.tokenade` file into a new browser with optional fingerprint matching

### Programmatic Usage

```python
from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery
from tokenade.core.importer.cookie_extractor import CookieExtractor, SiteFilter
from tokenade.core.importer.session_packager import SessionPackager
from tokenade.core.importer.session_loader import SessionLoader

# 1. Discover browser profiles
discovery = BrowserProfileDiscovery()
profiles = discovery.discover_all()
for p in profiles:
    print(f"{p.browser}: {p.name} at {p.path}")

# 2. Extract cookies
extractor = CookieExtractor()
cookies = extractor.extract_chrome_cookies("/path/to/profile")

# 3. Filter by site
site_filter = SiteFilter(["google"])
google_cookies = site_filter.filter_cookies(cookies)

# 4. Package into .tokenade
packager = SessionPackager()
package = packager.package(
    cookies=google_cookies,
    browser="chrome",
    profile="Default",
)
packager.save(package, "google_session.tokenade")

# 5. Load into browser
loader = SessionLoader()
result = loader.load(
    "google_session.tokenade",
    target_fp_name="my_vps",
    validate=True,
)
print(f"Loaded: {result['cookies_injected']}/{result['cookies_total']} cookies")
loader.close()
```

### .tokenade File Format

The `.tokenade` format is a JSON file with the following structure:

```json
{
  "version": "2.0",
  "created_at": "2026-06-01T12:00:00",
  "source_device": {
    "browser": "chrome",
    "profile": "Default",
    "platform": "linux",
    "hostname": "my-pc"
  },
  "site_name": "google",
  "auth_status": "logged_in",
  "cookies": [
    {"name": "SID", "value": "abc", "domain": ".google.com", "path": "/"}
  ],
  "tokens": [],
  "fingerprint": {"user_agent": "..."},
  "metadata": {
    "extraction_method": "chrome_cookies",
    "cookie_count": 1,
    "critical_cookie_count": 1
  }
}
```

## Portability Testing

The testing framework validates if cookies work across different fingerprints:

```python
from tokenade.tests.portability import PortabilityTester
from tokenade.core.fingerprint.manager import FingerprintManager
from tokenade import BrowserFactory

fp_manager = FingerprintManager()
tester = PortabilityTester(BrowserFactory, fp_manager)

# Test transfer
result = tester.test_session_transfer(
    session_data=session_dict,
    source_fp_name="my_pc",
    target_fp_name="my_vps",
    handler_class=GoogleHandler,
    test_api=True,
)

print(f"Result: {result.result}")
print(f"Cookies accepted: {result.cookies_accepted}/{result.cookies_injected}")

# Generate report
report = tester.generate_report("report.txt")
```

## Fingerprint Spoofing Runtime

Tokenade includes a production-grade fingerprint spoofing system that injects JavaScript into the browser to override fingerprinting APIs, making the browser appear identical to the source device.

### How It Works

1. **Collect** fingerprint data from source device (navigator, screen, WebGL, canvas, etc.)
2. **Build** a stealth injection script that overrides all fingerprinting APIs
3. **Inject** the script via Playwright's `add_init_script()` before page load
4. **Validate** that spoofing is active by checking overridden properties

### Stealth Levels

| Level | APIs Spoofed | Use Case |
|-------|-------------|----------|
| `basic` | Navigator, Screen, WebGL | Simple anti-bot detection |
| `advanced` | + Canvas, Audio, Plugins | Medium fingerprint sensitivity |
| `maximum` | + WebRTC, Battery, Fonts | Maximum anti-detection |

### Usage

```bash
# Transfer with maximum stealth (default)
tokenade transfer -s session.json -f my_pc --stealth-level maximum

# Transfer with validation
tokenade transfer -s session.json -f my_pc --validate-stealth

# Test with specific stealth level
tokenade test -s session.json --target-fp my_pc --stealth-level advanced --validate-stealth
```

### Programmatic Usage

```python
from tokenade.core.browser.manager import BrowserFactory, BrowserConfig
from tokenade.core.fingerprint.manager import BrowserFingerprint

# Create fingerprint
fp = BrowserFingerprint(
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    platform="Win32",
    screen_width=1920,
    screen_height=1080,
    webgl_vendor="Intel Inc.",
    webgl_renderer="Intel Iris Xe",
    canvas_fingerprint="data:image/png;base64,...",
)

# Launch browser with spoofing
config = BrowserConfig(
    headless=True,
    fingerprint=fp.to_dict(),
    stealth_level="maximum",
)

browser = BrowserFactory.create(**config.__dict__)
browser.launch()  # Stealth script auto-injected

# Validate injection
from tokenade.core.fingerprint.injector import validate_injection
result = validate_injection(browser)
print(f"Spoofing active: {result['valid']}")
print(f"User Agent: {result['user_agent']}")
print(f"Webdriver hidden: {result['webdriver_undefined']}")
```

### Architecture

```
tokenade/core/fingerprint/
├── collectors/           # Modular fingerprint collectors
│   ├── navigator.py      # User agent, platform, hardware
│   ├── screen.py         # Screen dimensions, viewport
│   ├── webgl.py          # WebGL vendor, renderer
│   ├── canvas.py         # Canvas 2D fingerprint
│   ├── audio.py          # AudioContext properties
│   ├── plugins.py        # Plugin/MIME types
│   ├── webrtc.py         # WebRTC local IPs
│   └── battery.py        # Battery API
├── stealth.py            # StealthScriptBuilder
├── injector.py           # Injection and validation
└── manager.py            # Fingerprint storage/retrieval
```

### What Gets Spoofed

- **Navigator**: `userAgent`, `platform`, `language`, `hardwareConcurrency`, `deviceMemory`, `maxTouchPoints`
- **Screen**: `width`, `height`, `colorDepth`, `devicePixelRatio`
- **WebGL**: `vendor`, `renderer` via `getParameter()`
- **Canvas**: `toDataURL()` returns pre-computed pixel data
- **Audio**: `AudioContext` sample rate and frequency data
- **Plugins**: `navigator.plugins` array with realistic entries
- **WebRTC**: Local IPs hidden (replaced with `0.0.0.0`)
- **Battery**: Charging status and level
- **Automation Cleanup**: `navigator.webdriver`, CDC props, `chrome.runtime`

## Security

- **Credential Storage**: Use system keyring when available
- **Session Encryption**: Encrypt session files with user password
- **Audit Logging**: All token operations are logged
- **Resource Cleanup**: Proper browser cleanup on errors

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black tokenade/

# Type check
mypy tokenade/
```

## License

MIT License - See LICENSE file

## Contributing

1. Fork the repository
2. Create a feature branch
3. Write tests for new functionality
4. Submit a pull request

## Support

- Issues: https://github.com/mihir0209/tokenade/issues
- Discussions: https://github.com/mihir0209/tokenade/discussions
