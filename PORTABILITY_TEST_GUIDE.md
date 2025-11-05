# 🧪 Browser Data Portability Test Setup

## This creates a COMPLETE isolated test environment

### What This Does:
1. Creates a new virtual environment (venv)
2. Installs Playwright
3. Installs Chromium browser
4. Copies browser_data/1 to test location
5. Runs test to verify portability

---

## 🚀 Quick Start

### Run this PowerShell script:

```powershell
# Navigate to Tokenade folder
cd D:\Tokenade

# Run the setup script
.\setup_portability_test.ps1
```

---

## 📋 Manual Steps (if you prefer)

### Step 1: Create Virtual Environment

```powershell
# Create venv
python -m venv test_venv

# Activate it
.\test_venv\Scripts\Activate.ps1

# You should see (test_venv) in your prompt
```

### Step 2: Install Dependencies

```powershell
# Install playwright
pip install playwright

# Install Chromium browser
playwright install chromium

# This downloads Playwright's bundled Chromium (~350MB)
```

### Step 3: Copy Browser Data

```powershell
# Create test directory
New-Item -ItemType Directory -Path "test_portability" -Force

# Copy browser data from account 1
Copy-Item -Recurse -Force "browser_data\1" "test_portability\browser_data_copy"
```

### Step 4: Run Test

```powershell
# Run the portability test
python test_portability.py
```

---

## 🎯 What To Expect

### ✅ **If Portable (SUCCESS):**

```
✅ Playwright Chromium launched successfully!
🌐 Navigating to Gmail...
🎉 SUCCESS! Session is portable!
   ✅ Browser data works with Playwright Chromium
   ✅ Logged into Gmail without re-authentication
   ✅ Profile is PORTABLE!
```

**You'll see:** Gmail inbox (logged in)

**Meaning:** 
- Browser data from Edge/Brave works with Chromium ✅
- Sessions are portable across browsers ✅
- Can deploy anywhere without original browser ✅

---

### ❌ **If NOT Portable (FAILURE):**

```
⚠ PARTIAL SUCCESS - Redirected to login page
   The profile loaded, but session expired or incompatible
```

**You'll see:** Google login page

**Meaning:**
- Browser data is browser-specific ❌
- Edge sessions need Edge, Brave sessions need Brave ❌
- Can't use Playwright Chromium with Edge/Brave profiles ❌

---

## 🔍 Why This Test Matters

### **Scenario 1: Portable Sessions (Best Case)**

```
Local Setup:
- Use Edge to log in → Save to browser_data/1

Deployment (Different Machine):
- Copy browser_data/1
- Use Playwright Chromium (no Edge needed!)
- Works! ✅
```

**Benefits:**
- No need to install Edge/Brave on servers
- Portable across systems
- Easier deployment

---

### **Scenario 2: Browser-Specific Sessions (Likely Case)**

```
Local Setup:
- Use Edge to log in → Save to browser_data/1

Deployment (Different Machine):
- Copy browser_data/1
- Try Playwright Chromium
- Fails - needs Edge ❌
```

**Implications:**
- Must use same browser that created the session
- Need Edge/Brave installed everywhere
- Less portable

---

## 💡 If NOT Portable - Alternative Solutions

### **Option A: Use Chrome Directly**

Instead of Edge/Brave, use Chrome from the start:

```python
executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe'
```

**Advantages:**
- Chrome more similar to Chromium
- Better compatibility
- More likely to be portable

---

### **Option B: Use Playwright Chromium from Start**

Don't use Edge/Brave at all:

```python
# No executable_path - uses Playwright Chromium
context = p.chromium.launch_persistent_context(
    user_data_dir='browser_data/1',
    headless=False
)
```

**Advantages:**
- 100% portable
- Same browser everywhere
- No dependencies

**Disadvantages:**
- Might get "browser not secure" error
- Need anti-detection measures

---

### **Option C: Keep Using Edge/Brave Everywhere**

Accept that sessions are browser-specific:

```python
# Always use Edge (install on all machines)
executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
```

---

## 🧪 Test Results

### After running test_portability.py:

**If you see Gmail inbox:**
- ✅ Sessions are portable!
- ✅ Can use Chromium anywhere
- ✅ No need for Edge/Brave on deployment

**If you see login page:**
- ❌ Sessions are browser-specific
- ❌ Need same browser everywhere
- ❌ Consider using Chrome or Chromium from start

---

## 📝 Next Steps Based on Results

### **If Portable:**
```powershell
# Great! Update collect_all_cookies.py to use Chromium
# No need for Edge/Brave on deployment servers
```

### **If NOT Portable:**
```powershell
# Option 1: Switch to Chrome for better portability
# Option 2: Use Playwright Chromium from the start (redo setup)
# Option 3: Accept browser-specific sessions (install Edge everywhere)
```

---

## 🔄 Clean Up After Test

```powershell
# Deactivate venv
deactivate

# Remove test files
Remove-Item -Recurse -Force test_venv
Remove-Item -Recurse -Force test_portability
```

---
