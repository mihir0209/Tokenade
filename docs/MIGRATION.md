# Migration Guide: v1 → v2

## Overview

Tokenade v2.0 is a complete restructure from the original ad-hoc scripts to a
production-grade Python package. This guide helps you migrate your existing
workflows.

## What's Changed

### Before (v1)
- Multiple standalone scripts in root directory
- No abstractions or modularity
- Duplicated code across scripts
- Hardcoded paths and configurations
- No testing framework

### After (v2)
- Structured Python package (`tokenade/`)
- Clean abstractions (Browser, Crypto, Fingerprint, Handlers)
- Single CLI entry point (`tokenade`)
- Portability testing framework
- Proper logging and error handling

## Command Mapping

| v1 Script | v2 Command | Notes |
|-----------|-----------|-------|
| `python setup_accounts.py` | `tokenade setup` | Interactive setup |
| `python collect_all_cookies.py` | `tokenade extract` | Headless extraction |
| `python collect_cookies_headless.py` | `tokenade extract` | Same functionality |
| `python decrypt_cookies_windows.py` | Built into extract | Automatic decryption |
| `python inject_cookies_linux.py` | `tokenade transfer` | With fingerprint matching |
| `python inject_cookies_via_playwright.py` | `tokenade transfer` | Recommended approach |
| `python browser_fingerprint_diagnostic.py` | `tokenade fingerprint collect` | Collect fingerprints |
| `python token_check_by_img_gen.py` | `tokenade test --test-api` | API testing |
| `python manage_accounts.py` | Manual (edit accounts.json) | Account management |
| `python clear_session.py` | `rm -rf browser_data/` | Clear sessions |

## Data Migration

### Accounts
Your `accounts.json` is compatible - same format:
```json
[
  {
    "number": 1,
    "email": "user@example.com",
    "password": "...",
    "profile_dir": "browser_data/1"
  }
]
```

### Browser Data
Your `browser_data/` directories are fully compatible:
```
browser_data/
├── 1/           # Account 1 profile
├── 2/           # Account 2 profile
└── ...
```

### Tokens
v1 saved tokens to `tokens/` directory. v2 saves to `sessions/`:

**v1 format:**
```json
{
  "access_token": "ya29...",
  "expires": "2024-01-01T00:00:00Z",
  "user": {"email": "...", "name": "..."}
}
```

**v2 format:**
```json
{
  "site_name": "google",
  "auth_status": "logged_in",
  "tokens": [...],
  "cookies": [...],
  "fingerprint": {...},
  "extracted_at": "2024-01-01T00:00:00"
}
```

To migrate old tokens, run:
```bash
tokenade extract  # Re-extracts from browser_data/
```

## New Features in v2

### 1. Fingerprint Management
```bash
# Collect fingerprint from your PC
tokenade fingerprint collect -n my_pc

# Use it for transfers
tokenade transfer -s session.json -f my_pc
```

### 2. Portability Testing
```bash
# Test if session works on different fingerprint
tokenade test -s session.json --target-fp my_vps

# Test multiple variations
tokenade test -s session.json --variations
```

### 3. Session Validation
```bash
# Validate all stored sessions
tokenade validate -d sessions/
```

### 4. Programmatic API
```python
from tokenade import BrowserFactory, BrowserConfig
from tokenade.handlers.google import GoogleHandler

config = BrowserConfig(headless=True)
browser = BrowserFactory.create(**config.__dict__)
browser.launch()

handler = GoogleHandler(browser)
session = handler.get_session()

# Save session
handler.save_session("sessions/my_session.json")

# Load and inject
handler.load_session("sessions/my_session.json")
handler.inject_session(handler._session_data)

browser.close()
```

## Removed Scripts

The following scripts are no longer needed and have been archived:

- `analyze_*.py` - Debug/analysis scripts
- `debug_*.py` - Debug scripts
- `check_*.py` - Validation scripts (replaced by `tokenade validate`)
- `collect_gmail_*.py` - Gmail collection (integrated into handler)
- `create_*.py` - Profile creation (handled by BrowserFactory)
- `decrypt_*.py` - Decryption (built into crypto module)
- `find_*.py` - File finding (not needed)
- `inject_*.py` - Injection (replaced by `tokenade transfer`)
- `setup_*.py` - Setup scripts (replaced by `tokenade setup`)

## Troubleshooting

### "Module not found"
```bash
pip install -e .  # Install package in development mode
```

### "Playwright not found"
```bash
playwright install chromium
```

### "Windows crypto not working"
```bash
pip install pywin32
```

### "Linux keyring not working"
```bash
pip install secretstorage
# Or use fallback 'peanuts' key (automatic)
```

## Getting Help

- Read the full README: `README.md`
- Check architecture docs: `.agent/plans/`
- Review code: `.agent/reviews/`
- Open an issue: https://codeberg.org/mihir0209/tokenade/issues
