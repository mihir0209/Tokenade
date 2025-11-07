# Complete Cookie Decryption & Cross-Platform Guide

## 🎯 Goal
Decrypt Windows Chrome cookies and use them on Linux VPS (cross-platform cookie portability).

---

## 📋 Overview

This solution has 3 steps:

1. **Windows**: Decrypt cookies using DPAPI
2. **Transfer**: Copy decrypted JSON files to Linux
3. **Linux**: Inject cookies into Linux Chrome profile

---

## Step 1: Decrypt Cookies on Windows

### 1.1 Install Dependencies

```powershell
# Install required packages
python install_dependencies_windows.py
```

This installs:
- `pywin32` - Windows DPAPI access
- `pycryptodome` - Encryption utilities

### 1.2 Run Cookie Decryption

```powershell
# Decrypt all accounts
python decrypt_cookies_windows.py

# OR decrypt specific account
python decrypt_cookies_windows.py 1
```

**What this does:**
- Reads `browser_data/N/Default/Network/Cookies` (or `Cookies.sqlite`)
- Decrypts each cookie using Windows DPAPI
- Saves decrypted cookies as JSON in `decrypted_cookies/`

**Output:**
```
decrypted_cookies/
├── account_1_cookies.json
├── account_2_cookies.json
└── ...
```

Each JSON file contains:
- Cookie name, value (DECRYPTED), domain, path
- Expiry dates, security flags
- All metadata needed to recreate cookies

---

## Step 2: Transfer to Linux VPS

### 2.1 Copy Decrypted Cookies

```bash
# From Windows (PowerShell)
scp -r decrypted_cookies/ user@vps:/path/to/Tokenade/

# OR use rsync
rsync -avz decrypted_cookies/ user@vps:/path/to/Tokenade/decrypted_cookies/
```

### 2.2 Copy Injection Script

```bash
# Also copy the injection script
scp inject_cookies_linux.py user@vps:/path/to/Tokenade/
```

---

## Step 3: Inject Cookies on Linux

### 3.1 Run Cookie Injection

```bash
# On Linux VPS
cd /path/to/Tokenade

# Inject all accounts
python3 inject_cookies_linux.py

# OR inject specific account
python3 inject_cookies_linux.py 1
```

**What this does:**
- Reads `decrypted_cookies/account_N_cookies.json`
- Creates `browser_data/N/Default/Network/Cookies` database
- Inserts cookies as **plain text** (no encryption needed)
- Linux Chrome will use them directly

**Output:**
```
browser_data/
├── 1/
│   └── Default/
│       └── Network/
│           └── Cookies (SQLite database with injected cookies)
├── 2/
│   └── Default/
│       └── Network/
│           └── Cookies
└── ...
```

---

## Step 4: Use Cookies on Linux

### 4.1 Test with Playwright

```bash
# Use collect_all_cookies.py with injected cookies
python3 collect_all_cookies.py
```

### 4.2 Or Use Directly with Chrome

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir='browser_data/1',
        executable_path='/usr/bin/google-chrome',
        headless=False
    )
    
    page = context.pages[0]
    page.goto('https://mail.google.com')
    
    # You should be logged in!
```

---

## 🔍 How It Works

### Windows Cookie Structure (Before)
```
Cookies SQLite Database
├── Cookie: SID
│   ├── value: "" (empty)
│   └── encrypted_value: b'v10\x91\xc5:...' (DPAPI encrypted)
```

### Decrypted JSON (Transfer Format)
```json
{
  "name": "SID",
  "value": "g.a000qwerty...",  // ← DECRYPTED VALUE
  "host_key": ".google.com",
  "path": "/",
  "is_secure": false,
  "expires_utc": 13392801234567890
}
```

### Linux Cookie Structure (After Injection)
```
Cookies SQLite Database
├── Cookie: SID
│   ├── value: "g.a000qwerty..." (plain text)
│   └── encrypted_value: b'' (empty)
```

Linux Chrome reads the plain text value directly (no decryption needed).

---

## ⚠️ Important Notes

### Cookie Expiration
- Cookies have expiry dates (usually 1-2 years for Google)
- If cookies expire, you'll need to:
  1. Re-login on Windows
  2. Re-decrypt and transfer
  3. Re-inject on Linux

### Security Considerations
- **Decrypted cookies are sensitive!**
- They contain authentication tokens
- Protect `decrypted_cookies/` directory
- Use secure transfer (SCP/rsync over SSH)
- Delete decrypted files after injection

### Automation
```bash
# Create a script to automate the full process

# On Windows (decrypt.ps1)
python decrypt_cookies_windows.py
scp -r decrypted_cookies/ user@vps:/path/to/Tokenade/

# On Linux (inject.sh)
python3 inject_cookies_linux.py
rm -rf decrypted_cookies/  # Clean up sensitive data
```

---

## 🎯 Complete Workflow Example

### Windows
```powershell
# 1. Install dependencies (one-time)
python install_dependencies_windows.py

# 2. Decrypt cookies
python decrypt_cookies_windows.py

# 3. Transfer to Linux
scp -r decrypted_cookies/ user@vps:/home/user/Tokenade/
```

### Linux
```bash
# 4. Inject cookies
cd /home/user/Tokenade
python3 inject_cookies_linux.py

# 5. Test
python3 collect_all_cookies.py

# 6. Clean up
rm -rf decrypted_cookies/
```

### Result
✅ Your Google sessions now work on Linux!
✅ Gmail, Google Labs, all services authenticated
✅ No need to re-login on Linux

---

## 🐛 Troubleshooting

### Issue: "Module 'win32crypt' not found"
```powershell
pip install pywin32
```

### Issue: "Database is locked" on Windows
Close Google Chrome before running decryption.

### Issue: Cookies don't work on Linux
- Check cookie expiry dates
- Verify cookies were injected (check browser_data/N/Default/Network/Cookies exists)
- Try running Chrome with the profile manually

### Issue: "Permission denied" on Linux
```bash
chmod -R 755 browser_data/
```

---

## 📊 Comparison: Before vs After

| Method | Portability | Complexity | Maintenance |
|--------|-------------|------------|-------------|
| **Copy browser_data/** | ❌ Doesn't work | Simple | N/A |
| **Token-based** | ✅ Works | Simple | Manual refresh |
| **Cookie decrypt + inject** | ✅ Works | Medium | Refresh on expiry |
| **Fresh Linux login** | ✅ Works | Complex | One-time setup |

---

## ✅ Success Criteria

After completing this process, you should be able to:

1. ✅ Open Chrome on Linux with injected profile
2. ✅ Navigate to https://mail.google.com → Already logged in
3. ✅ Navigate to https://labs.google → Already logged in
4. ✅ Use `collect_all_cookies.py` to extract access tokens
5. ✅ Use tokens in Whisk API calls

---

## 🎉 Conclusion

You now have **true cross-platform cookie portability**!

- Windows → Decrypt with DPAPI
- Linux → Inject as plain text
- Sessions work seamlessly

This is more robust than token-based approach because:
- Cookies last longer (1-2 years vs hours)
- Full session state preserved
- Works with all Google services

Enjoy your automated multi-account system! 🚀
