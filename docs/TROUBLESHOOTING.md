# Troubleshooting Guide

## Common Issues

### "No browser profiles found"

**Cause:** Tokenade can't find browser profile directories.

**Fix:**
```bash
# List discovered profiles
tokenade export --list-profiles

# If no profiles found, specify the path manually
tokenade export --browser-path /path/to/profile

# Common profile locations:
# Chrome:   ~/.config/google-chrome/Default
# Firefox:  ~/.mozilla/firefox/*.default
# Brave:    ~/.config/BraveSoftware/Brave-Browser/Default
# Edge:     ~/.config/microsoft-edge/Default
```

---

### "Failed to launch browser"

**Cause:** Playwright browser not installed.

**Fix:**
```bash
pip install playwright
playwright install chromium
```

If the error mentions "timeout" or "address in use":
```bash
# Kill existing Chrome/Chromium processes
pkill -f chromium
pkill -f chrome

# Or use a different port
tokenade proxy -s session.tokenade --port 9223
```

---

### "Database is locked"

**Cause:** Browser is running and has locked the cookies database.

**Fix:** Close the browser before exporting cookies, or use the built-in copy mechanism:
```bash
# Tokenade automatically copies the database, but if it fails:
# 1. Close the browser completely
# 2. Try again

# Or use profile injection instead (works while browser is running)
tokenade inject-profile -s session.tokenade --browser firefox --profile "default"
```

---

### "Decryption failed"

**Cause:** Cookie encryption key not available.

**Fix:**
```bash
# On Linux, install keyring support
pip install secretstorage

# Or check if the encryption key is accessible
python3 -c "
from tokenade.core.crypto.cookie_crypto import CookieCryptoFactory
crypto = CookieCryptoFactory.create()
key = crypto.get_encryption_key('/path/to/browser/profile')
print(f'Key found: {key is not None}')
"
```

---

### "CONNECT failed / 502 Bad Gateway"

**Cause:** Proxy can't establish HTTPS tunnel.

**Fix:**
```bash
# Check DNS resolution
nslookup target-domain.com

# Check if target port is reachable
nc -zv target-domain.com 443

# Try with verbose logging
tokenade proxy -s session.tokenade -v
```

---

### "Session validation failed: logged out"

**Cause:** The loaded session doesn't have valid authentication cookies.

**Fix:**
```bash
# Check which cookies are present
python3 -c "
import json
with open('session.tokenade') as f:
    s = json.load(f)
print(f'Cookies: {len(s[\"cookies\"])}')
print(f'Auth: {s.get(\"auth_status\")}')
for c in s['cookies']:
    print(f'  {c[\"name\"]}: {c[\"domain\"]}')
"
```

Common causes:
- Exported from wrong profile
- Cookies expired since export
- Browser was in incognito/private mode

---

### "Permission denied"

**Cause:** Insufficient permissions to read browser profile.

**Fix:**
```bash
# Check file permissions
ls -la ~/.config/BraveSoftware/Brave-Browser/Default/Cookies

# Fix permissions if needed
chmod 644 ~/.config/BraveSoftware/Brave-Browser/Default/Cookies

# Or run with sudo (not recommended for production)
sudo tokenade export --browser-name brave
```

---

### "Playwright not installed"

**Cause:** The `playwright` package is not installed.

**Fix:**
```bash
pip install playwright
playwright install chromium
```

---

### localStorage injection fails

**Cause:** localStorage is origin-bound; you must navigate to the origin first.

**Fix:**
```bash
# Specify the origin for localStorage injection
tokenade export --browser-name chrome \
  --extract-local-storage \
  --local-storage-origin "https://web.telegram.org"
```

---

## Debug Mode

Enable verbose logging for detailed output:

```bash
tokenade -v export --browser-name brave
tokenade -v proxy -s session.tokenade
```

Or set the environment variable:

```bash
export TOKENADE_LOG_LEVEL=DEBUG
tokenade export --browser-name brave
```

## Getting Help

```bash
tokenade --help
tokenade export --help
tokenade proxy --help
```

Report issues at: https://github.com/mihir0209/Tokenade/issues
