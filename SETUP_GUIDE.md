# 🚀 Complete Setup Guide - Multi-Account Token Management

This guide will walk you through setting up and using the multi-account system for Google Labs Whisk API.

---

## 📚 Table of Contents

1. [What We're Building](#what-were-building)
2. [Step-by-Step Setup](#step-by-step-setup)
3. [Testing with 2 Accounts](#testing-with-2-accounts)
4. [Using the Tokens](#using-the-tokens)
5. [Troubleshooting](#troubleshooting)

---

## 🎯 What We're Building

**Goal**: Manage up to 26 Google accounts to get access tokens for Whisk API

**How it Works**:
1. **One-time Manual Login** → Use `setup_accounts.py` to log in to each account (visible browser)
2. **Save Sessions** → Each account's session saved in `browser_data/1`, `browser_data/2`, etc.
3. **Automated Collection** → Use `collect_all_cookies.py` to extract tokens (headless, fast)
4. **Use Tokens** → Load tokens from `tokens/` folder to make API calls

**Files Structure**:
```
D:\Tokenade\
├── setup_accounts.py         ← Step 1: Manual login (run once per account)
├── collect_all_cookies.py    ← Step 2: Collect tokens (run anytime)
├── browser_data/             ← Saved browser sessions
│   ├── 1/                    (Account 1 session)
│   ├── 2/                    (Account 2 session)
│   └── ...
└── tokens/                   ← Extracted tokens
    ├── account_1.json
    ├── account_2.json
    └── all_tokens.json
```

---

## 📝 Step-by-Step Setup

### **STEP 1: Run setup_accounts.py (Manual Login)**

This is the ONE-TIME setup where you log in to each account manually.

```bash
python setup_accounts.py
```

**What it will ask:**

1. **How many accounts to set up?** → Enter `2` (for testing)

2. **Which accounts to setup?**
   - Option 1: All accounts (1-2)
   - Option 2: Specific numbers → Enter `1,2`
   - Option 3: Range → Enter `1-2`
   
   → Choose **Option 1** for simplicity

3. **For Account 1:**
   - Browser window opens
   - Click "Sign in with Google"
   - Log in with your first Google account
   - **Wait for the script to confirm** ✅
   - Browser closes automatically

4. **For Account 2:**
   - Same process with second account
   - Browser opens again
   - Log in with second Google account
   - Wait for confirmation
   - Done!

**Expected Output**:
```
==========================================
SETUP COMPLETE!
==========================================

✅ Successfully set up: 2/2 accounts

Account 1: user1@gmail.com ✓
Account 2: user2@gmail.com ✓

📁 Sessions saved in browser_data/
```

**What Happens**:
- Creates `browser_data/1/` with Account 1's session
- Creates `browser_data/2/` with Account 2's session
- Saves `token_info.json` in each folder

---

### **STEP 2: Run collect_all_cookies.py (Automated Collection)**

Now that sessions are saved, you can collect tokens anytime WITHOUT logging in again!

```bash
python collect_all_cookies.py
```

**What it will ask:**

1. **Collection mode?**
   ```
   1. All accounts      ← Choose this
   2. Specific accounts
   3. Single account
   ```
   → Enter `1`

2. **Run in headless mode?** → Enter `yes` (or just press Enter)

**Expected Output**:
```
🚀 Starting collection... (headless=True)

📋 Account 1: Collecting token...
   🔍 Checking session...
   ✅ Token collected!
   📧 Email: user1@gmail.com
   🔑 Token: ya29.a0ATi6K2sC0mlJk4k9fd3Q7t8mLflM1J2OJvQG8WjP...
   💾 Saved to: D:\Tokenade\tokens\account_1.json

📋 Account 2: Collecting token...
   🔍 Checking session...
   ✅ Token collected!
   📧 Email: user2@gmail.com
   🔑 Token: ya29.a0ATi6K2xYz9pL3mN7rQ8tW5vXuH2kL9oP...
   💾 Saved to: D:\Tokenade\tokens\account_2.json

==========================================
COLLECTION COMPLETE!
==========================================

✅ Successfully collected: 2/2 accounts

📁 Tokens saved in: D:\Tokenade\tokens
   • Individual files: account_N.json
   • All tokens: all_tokens.json
```

**What Happens**:
- Opens browser sessions in headless mode (invisible)
- Extracts tokens from each account
- Saves to `tokens/account_1.json`, `tokens/account_2.json`
- Creates `tokens/all_tokens.json` with all tokens

---

## 🧪 Testing with 2 Accounts

### **Test 1: Verify Tokens Exist**

Check that token files were created:

```powershell
dir tokens\
```

You should see:
```
account_1.json
account_2.json
all_tokens.json
```

### **Test 2: View Token Content**

```powershell
Get-Content tokens\account_1.json | ConvertFrom-Json | ConvertTo-Json
```

Should show:
```json
{
  "account_number": 1,
  "email": "user1@gmail.com",
  "access_token": "ya29.a0ATi6K...",
  "expires": "2025-11-05T15:30:00Z",
  "collected_at": "2025-11-05 14:30:00",
  "status": "active",
  "cookies": [...]
}
```

### **Test 3: Use Token in API Call**

Let's create a simple test script:

```python
# test_tokens.py
import json
import requests

# Load all tokens
with open('tokens/all_tokens.json', 'r') as f:
    tokens = json.load(f)

print(f"\n📋 Found {len(tokens)} account(s)\n")

for token_data in tokens:
    print(f"Account {token_data['account_number']}: {token_data['email']}")
    print(f"  Token: {token_data['access_token'][:50]}...")
    print(f"  Status: {token_data['status']}")
    print()
```

Run it:
```bash
python test_tokens.py
```

---

## 🔄 Using the Tokens

### **Option A: Load All Tokens**

```python
import json

with open('tokens/all_tokens.json', 'r') as f:
    all_tokens = json.load(f)

# Use first available token
token = all_tokens[0]['access_token']
```

### **Option B: Load Specific Account**

```python
import json

with open('tokens/account_1.json', 'r') as f:
    token_data = json.load(f)

token = token_data['access_token']
```

### **Option C: Rotate Through Accounts**

```python
import json

with open('tokens/all_tokens.json', 'r') as f:
    tokens = json.load(f)

# Rotate through all accounts
for i, token_data in enumerate(tokens):
    print(f"Using account {i+1}: {token_data['email']}")
    
    # Make API call with this token
    headers = {'Authorization': f'Bearer {token_data["access_token"]}'}
    # ... your API call here
```

---

## 🛑 Stopping and Resuming Setup

### **Scenario: You stop setup_accounts.py after Account 1**

If you run `setup_accounts.py` and stop it after setting up Account 1:

1. Account 1 is saved in `browser_data/1/` ✅
2. Account 2 is NOT set up ❌

**To continue later:**

Run `setup_accounts.py` again:
```bash
python setup_accounts.py
```

Choose:
- How many accounts? → `2`
- Which accounts? → Option 2 (Specific numbers) → Enter `2`

This will ONLY set up Account 2, skipping Account 1.

**Or set up all again** (it will overwrite):
- Choose Option 1 (All accounts)
- Re-login to all accounts

---

## ❓ Troubleshooting

### **Problem 1: "No session found" when collecting**

**Cause**: Account not set up yet

**Solution**: Run `setup_accounts.py` first

---

### **Problem 2: "Session expired" / No token collected**

**Cause**: Been too long since last login

**Solution**: 
1. Run `setup_accounts.py` again for that account
2. Or use auto-relogin (see Advanced section)

---

### **Problem 3: Token works once but fails later**

**Cause**: Token expired (tokens expire in ~1 hour)

**Solution**: 
- Run `collect_all_cookies.py` again to get fresh tokens
- Do this before each batch of API calls

---

### **Problem 4: Browser doesn't close automatically**

**Cause**: Network delay or API not responding

**Solution**: 
- Wait 30 seconds
- If still stuck, close browser manually
- Run setup again for that account

---

## 🎓 Pro Tips

### **Tip 1: Fresh Tokens Before Big Jobs**

Always collect fresh tokens before making many API calls:
```bash
python collect_all_cookies.py
# Then run your API script
```

### **Tip 2: Check Token Expiry**

Tokens in the JSON have `"expires"` field. Check before using:
```python
from datetime import datetime

expires = token_data['expires']  # "2025-11-05T15:30:00Z"
# If expired, run collect_all_cookies.py again
```

### **Tip 3: Headless vs Visible**

- **Headless** (`yes`): Fast, invisible, good for automation
- **Visible** (`no`): Slower, shows browser, good for debugging

When collecting, if something fails, try visible mode:
```bash
python collect_all_cookies.py
# Choose: Run in headless mode? → no
```

### **Tip 4: Backup Sessions**

Your `browser_data/` folder contains all sessions. Back it up!
```powershell
# Backup
Copy-Item -Recurse browser_data browser_data_backup

# Restore
Copy-Item -Recurse browser_data_backup browser_data
```

---

## 🎯 Quick Reference

| Action | Command |
|--------|---------|
| Set up new accounts | `python setup_accounts.py` |
| Collect fresh tokens | `python collect_all_cookies.py` |
| Clear all sessions | `python clear_session.py` |
| View tokens | `Get-Content tokens\all_tokens.json` |

---

## 📞 What to Do Next

1. ✅ Run `python setup_accounts.py` → Set up 2 accounts
2. ✅ Run `python collect_all_cookies.py` → Collect tokens
3. ✅ Check `tokens/` folder → Verify JSON files exist
4. ✅ Create your Whisk API script → Use tokens from JSON

---

**Ready to start? Run:**
```bash
python setup_accounts.py
```

And follow the prompts! 🚀
