# Manual Test Report — Cookie Extraction

**Date:** 2026-06-14
**Version:** v3.4.0
**Tester:** Automated (opencode)

## Setup

- **OS:** Linux (Ubuntu)
- **Firefox:** Snap package with default profile at `~/.snap/firefox/common/.mozilla/firefox/nj40lj6y.default`
- **Brave:** Installed at `~/.config/BraveSoftware/Brave-Browser/Default`
- **Cookies:** Both browsers have logged-in sessions with 3000+ cookies (Firefox) and 100+ cookies (Brave)

## Test 1: Firefox Cookie Extraction

### Command
```bash
cd /home/ghostrider/Projects/tokenade
python -c "
from tokenade.core.importer.cookie_extractor import CookieExtractor
extractor = CookieExtractor('/home/ghostrider/snap/firefox/common/.mozilla/firefox/nj40lj6y.default', browser='firefox')
cookies = extractor.extract()
print(f'Total cookies: {len(cookies)}')
"
```

### Result
- **Status:** PASS
- **Output:** `Total cookies: 3043`
- **Notes:** Successfully extracted all cookies from Firefox Snap profile

## Test 2: Brave Cookie Extraction

### Command
```bash
python -c "
from tokenade.core.importer.cookie_extractor import CookieExtractor
extractor = CookieExtractor('/home/ghostrider/.config/BraveSoftware/Brave-Browser/Default', browser='chrome')
cookies = extractor.extract()
print(f'Total cookies: {len(cookies)}')
"
```

### Result
- **Status:** PASS
- **Output:** `Total cookies: 105`
- **Notes:** Brave uses Chromium format, extracted with `browser='chrome'`

## Test 3: Domain-Filtered Extraction

### Command
```bash
python -c "
from tokenade.core.importer.cookie_extractor import CookieExtractor
extractor = CookieExtractor('/home/ghostrider/snap/firefox/common/.mozilla/firefox/nj40lj6y.default', browser='firefox')
all_cookies = extractor.extract()
google_cookies = [c for c in all_cookies if 'google' in c.get('domain', '')]
print(f'Google cookies: {len(google_cookies)}')
"
```

### Result
- **Status:** PASS
- **Output:** `Google cookies: 166`
- **Notes:** Manual domain filtering works correctly

## Test 4: CLI Export with Domain Filter

### Command
```bash
python -m tokenade.cli export --browser-name firefox --domains "github.com" -o test_sessions/github.tokenade
```

### Result
- **Status:** PASS
- **Output:**
  ```
  Total cookies: 3103
  Filtered to 9 cookies for domains: github.com
  Site: github
  Auth: logged_in
  Cookies: 9
  Critical: 2
  ```
- **Notes:** CLI export correctly filters, detects site, infers auth status, and counts critical cookies

## Test 5: Browser Profile Discovery

### Command
```bash
python -m tokenade.cli export --list-profiles
```

### Result
- **Status:** PASS
- **Output:** Lists Firefox (1 profile) and Brave (1 profile) with paths
- **Notes:** Profile discovery works for both Snap Firefox and standard Brave installation
