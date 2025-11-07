# VPS Deployment Guide - Linux

## ❌ Windows → Linux Portability: NOT SUPPORTED

**Test Result**: Browser profiles from Windows Chrome **cannot** be used on Linux Chrome.

### Why It Doesn't Work:
- Cache format incompatibility
- Cookie encryption differences (Windows DPAPI vs Linux keyring)
- OS-specific browser internals
- Different file structures

---

## ✅ Recommended Approach: Token-Based Deployment

Instead of copying `browser_data/`, copy the **tokens** only:

### Step 1: Extract Tokens on Windows

```powershell
# On Windows
python quick_collect_tokens.py
```

This creates `tokens/account_1.json`, `tokens/account_2.json`, etc.

### Step 2: Copy Tokens to Linux VPS

```bash
# From Windows (PowerShell)
scp -r tokens/ user@vps:/path/to/Tokenade/

# OR use rsync
rsync -avz tokens/ user@vps:/path/to/Tokenade/tokens/
```

### Step 3: Use Tokens on Linux VPS

Create a script to use the tokens directly:

```python
# use_tokens.py on Linux
import json
import glob

# Load all tokens
token_files = glob.glob('tokens/account_*.json')

for token_file in token_files:
    with open(token_file) as f:
        data = json.load(f)
    
    access_token = data['access_token']
    email = data['email']
    
    # Use the token in API requests
    print(f"Account: {email}")
    print(f"Token: {access_token[:60]}...")
    
    # Make API calls with the token
    # headers = {'Authorization': f'Bearer {access_token}'}
```

**Advantages:**
- ✅ No browser needed on VPS
- ✅ Lightweight (just JSON files)
- ✅ Works on any OS
- ✅ Tokens are valid for several hours

**Disadvantages:**
- ⚠ Tokens expire (need to refresh from Windows)
- ⚠ Cannot refresh tokens on Linux without browser

---

## Alternative: Fresh Login on Linux VPS

If you need long-term sessions on Linux, create them directly on Linux:

### Setup on Linux VPS

```bash
# 1. Install Google Chrome
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install ./google-chrome-stable_current_amd64.deb

# 2. Install Python dependencies
pip install playwright
playwright install chromium
playwright install-deps

# 3. Install X Virtual Frame Buffer (for headless GUI)
sudo apt install -y xvfb

# 4. Run setup with virtual display
xvfb-run python setup_accounts.py
```

### For Headless Servers (No Display)

If your VPS has no display, use **virtual display**:

```bash
# Install Xvfb
sudo apt install -y xvfb

# Run with virtual display
xvfb-run -a python setup_accounts.py
```

Or use **headless mode with VNC** for manual login:

```bash
# Install VNC server
sudo apt install -y tightvncserver

# Start VNC
vncserver :1

# Connect with VNC viewer, then run setup
DISPLAY=:1 python setup_accounts.py
```

---

## Best Practice for Production VPS

### Option A: Hybrid Approach (Recommended)

1. **On Windows (Development)**:
   - Run `setup_accounts.py` - Manual login with Chrome
   - Run `quick_collect_tokens.py` - Extract tokens
   - Test image generation locally

2. **On Linux VPS (Production)**:
   - Copy `tokens/` directory
   - Use tokens for API calls
   - Refresh tokens periodically from Windows

3. **Token Refresh Strategy**:
   ```bash
   # Automated refresh (Windows scheduled task)
   # Run every 2 hours:
   python quick_collect_tokens.py
   scp -r tokens/ user@vps:/path/to/Tokenade/
   ```

### Option B: Full Linux Setup

1. **Setup once on Linux VPS**:
   ```bash
   xvfb-run python setup_accounts.py
   ```

2. **Use collect_all_cookies.py for refreshing**:
   ```bash
   # Headless token collection
   python collect_all_cookies.py
   ```

This creates Linux-native browser sessions that work perfectly.

---

## Comparison

| Approach | Portability | Maintenance | Complexity |
|----------|-------------|-------------|------------|
| **Token-based** | ✅ Works anywhere | Manual refresh | ⭐ Simple |
| **Linux native sessions** | ⚠ Linux only | Auto-refresh | ⭐⭐ Medium |
| **Windows → Linux copy** | ❌ Doesn't work | N/A | N/A |

---

## Troubleshooting

### Issue: "Target page has been closed" on Linux
**Cause**: Windows browser_data incompatible with Linux

**Solution**: Use tokens OR create fresh Linux sessions

### Issue: Tokens expire
**Solution**: 
```bash
# On Windows (automate this)
python quick_collect_tokens.py
scp tokens/* user@vps:/path/to/Tokenade/tokens/
```

### Issue: Cannot run browser on headless VPS
**Solution**: Use Xvfb virtual display
```bash
sudo apt install xvfb
xvfb-run python setup_accounts.py
```

### Issue: Need to refresh tokens on Linux
**Solution**: 
- Option 1: Refresh from Windows, copy to Linux
- Option 2: Setup Linux browser sessions (one-time with Xvfb)

---

## Summary

**✅ What Works:**
- Token-based approach (copy `tokens/`)
- Fresh Linux browser sessions (with Xvfb)
- Same OS, same browser

**❌ What Doesn't Work:**
- Copying `browser_data/` from Windows to Linux
- Cross-OS browser profile portability

**🎯 Recommended:**
Use **token-based approach** for simplicity, or **create Linux native sessions** for autonomous operation.
