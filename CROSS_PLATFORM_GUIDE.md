# Cross-Platform Browser Session Guide

## Overview

This guide explains how to use browser sessions across different operating systems (Windows → Linux VPS).

## The Challenge

**Browser profiles are OS-specific due to:**
- Cookie encryption (Windows DPAPI vs Linux keyring)
- Platform-specific security features
- Different file system paths
- Browser-specific data formats

## Solution: Use Google Chrome on Both Platforms

The best approach for cross-platform compatibility is to use **Google Chrome** on both Windows and Linux:

1. **Setup on Windows** with Chrome
2. **Copy `browser_data/` to Linux VPS**
3. **Use Chrome on Linux** to read the sessions

### Why Chrome?
- Most consistent across platforms
- Better cookie compatibility
- Same codebase on Windows/Linux/Mac
- Better chance of session portability

---

## Step-by-Step Guide

### 1️⃣ Setup on Windows (One-Time)

```powershell
# Install Google Chrome (if not installed)
# Download from: https://www.google.com/chrome/

# Run setup script
python setup_accounts.py

# Select option 3 (Google Chrome 64-bit)
# Login to your Google accounts manually
```

This creates `browser_data/1/`, `browser_data/2/`, etc.

---

### 2️⃣ Copy to Linux VPS

```bash
# On Windows (PowerShell)
scp -r browser_data user@vps:/path/to/Tokenade/

# OR use rsync
rsync -avz browser_data/ user@vps:/path/to/Tokenade/browser_data/
```

---

### 3️⃣ Setup on Linux VPS

```bash
# Install Google Chrome on Linux
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install ./google-chrome-stable_current_amd64.deb

# Install Playwright
pip install playwright
playwright install chromium

# Install dependencies
sudo apt install -y \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2
```

---

### 4️⃣ Test Portability on Linux

```bash
# Test if browser_data works on Linux
python test_portability.py
```

**Expected results:**

✅ **SUCCESS**: Gmail inbox shows → Sessions are portable!
❌ **FAILURE**: Login page shows → Sessions are NOT portable

---

## What If It Doesn't Work?

If browser sessions from Windows don't work on Linux:

### Option A: Fresh Login on Linux

```bash
# Re-run setup on Linux
python setup_accounts.py

# Select Google Chrome
# Login to accounts again
```

This creates fresh Linux-native browser profiles.

### Option B: Use Cookies Only

Instead of copying full `browser_data/`, extract just the access tokens:

```powershell
# On Windows
python quick_collect_tokens.py

# Copy tokens/ directory instead
scp -r tokens/ user@vps:/path/to/Tokenade/
```

Then use the tokens directly in your API calls (no browser needed).

---

## Platform-Specific Notes

### Windows
- Chrome location: `C:\Program Files\Google\Chrome\Application\chrome.exe`
- Cookie encryption: Windows DPAPI
- Profile location: `browser_data/N/`

### Linux
- Chrome location: `/usr/bin/google-chrome`
- Cookie encryption: Linux keyring (libsecret)
- Profile location: `browser_data/N/`

### macOS
- Chrome location: `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
- Cookie encryption: macOS Keychain
- Profile location: `browser_data/N/`

---

## Recommended Workflow

### For Production VPS Deployment:

1. **Development (Windows)**
   - Use `setup_accounts.py` with Chrome
   - Test with `collect_all_cookies.py`
   - Generate images with `token_check_by_img_gen.py`

2. **Test Portability**
   - Copy `browser_data/` to a Linux test environment
   - Run `python test_portability.py`
   - Verify sessions work

3. **Production (Linux VPS)**
   - If portable: Copy `browser_data/` and use `collect_all_cookies.py`
   - If NOT portable: Re-run `setup_accounts.py` on Linux
   - Use `quick_collect_tokens.py` for token extraction

---

## Troubleshooting

### Issue: "Browser may not be secure" error
**Solution**: Use real Chrome, not Playwright Chromium

### Issue: "Target page has been closed"
**Solution**: Browser profile incompatibility - use same browser on both platforms

### Issue: "Redirected to login page"
**Solution**: Cookie encryption mismatch - re-login on target platform

### Issue: Chrome not found on Linux
**Solution**: Install with:
```bash
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install ./google-chrome-stable_current_amd64.deb
```

---

## Summary

| Scenario | Portability | Recommendation |
|----------|-------------|----------------|
| Windows Chrome → Linux Chrome | ⚠️ **Maybe** | Test with `test_portability.py` |
| Windows Edge → Linux Chrome | ❌ **No** | Re-login on Linux |
| Windows Chrome → Windows Chrome | ✅ **Yes** | Works perfectly |
| Same OS, same browser | ✅ **Yes** | Always works |

**Best practice**: Use Google Chrome on all platforms for maximum compatibility.
