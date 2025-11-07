"""
Debug: Find where Chrome is actually saving cookies
"""

import os
from playwright.sync_api import sync_playwright

def find_all_cookie_files(base_path):
    """Find all files with 'cookie' in name"""
    cookie_files = []
    
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if 'cookie' in file.lower():
                full_path = os.path.join(root, file)
                size = os.path.getsize(full_path)
                cookie_files.append((full_path, size))
    
    return cookie_files

base_dir = os.getcwd()
profile_path = os.path.join(base_dir, 'browser_data', '1')

print("=" * 80)
print("DEBUGGING COOKIE STORAGE LOCATION")
print("=" * 80)

print(f"\n📁 Profile path: {profile_path}")

# Check what files exist BEFORE we add cookies
print(f"\n🔍 Files BEFORE adding cookies:")
before_files = find_all_cookie_files(profile_path) if os.path.exists(profile_path) else []
for path, size in before_files:
    rel_path = os.path.relpath(path, profile_path)
    print(f"   {rel_path}: {size:,} bytes")

# Now inject cookies
print(f"\n🚀 Injecting cookies via Playwright...")

import json

json_path = os.path.join(base_dir, 'decrypted_cookies', 'account_1_cookies.json')

with open(json_path, 'r') as f:
    cookies = json.load(f)

print(f"📊 Loaded {len(cookies)} cookies")

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=profile_path,
        headless=True,
        channel="chrome"
    )
    
    print(f"✅ Chrome launched")
    
    # Convert and add cookies (with validation)
    pw_cookies = []
    for cookie in cookies:
        try:
            pw_cookie = {
                'name': cookie['name'],
                'value': cookie['value'],
                'domain': cookie['host_key'],
                'path': cookie['path']
            }
            
            # Add optional secure/httpOnly flags
            if cookie.get('is_secure', False):
                pw_cookie['secure'] = True
            if cookie.get('is_httponly', False):
                pw_cookie['httpOnly'] = True
            
            # Add sameSite for secure cookies
            if cookie.get('is_secure', False):
                samesite = cookie.get('samesite', -1)
                if samesite == 1:
                    pw_cookie['sameSite'] = 'Lax'
                elif samesite == 2:
                    pw_cookie['sameSite'] = 'Strict'
                else:
                    pw_cookie['sameSite'] = 'None'
            
            pw_cookies.append(pw_cookie)
        except Exception as e:
            print(f"   ⚠️  Skipped {cookie.get('name', 'unknown')}: {e}")
    
    context.add_cookies(pw_cookies)
    
    print(f"✅ Added {len(pw_cookies)} cookies")
    
    # Check cookies in context
    saved = context.cookies()
    print(f"📊 Context has {len(saved)} cookies")
    
    # Try to force a save by navigating
    print(f"\n🌐 Navigating to google.com to trigger save...")
    page = context.pages[0] if context.pages else context.new_page()
    page.goto('https://www.google.com', wait_until='networkidle')
    
    # Wait a bit
    print(f"⏳ Waiting for Chrome to save...")
    page.wait_for_timeout(3000)
    
    print(f"💾 Closing Chrome...")
    context.close()

print(f"\n✅ Chrome closed")

# Check what files exist AFTER
print(f"\n🔍 Files AFTER adding cookies:")
after_files = find_all_cookie_files(profile_path)

for path, size in after_files:
    rel_path = os.path.relpath(path, profile_path)
    was_before = any(p == path for p, s in before_files)
    
    if was_before:
        before_size = next(s for p, s in before_files if p == path)
        if size != before_size:
            print(f"   {rel_path}: {before_size:,} → {size:,} bytes ⚠️ CHANGED!")
        else:
            print(f"   {rel_path}: {size:,} bytes (unchanged)")
    else:
        print(f"   {rel_path}: {size:,} bytes ✅ NEW!")

# Check the expected Cookies file specifically
cookies_db = os.path.join(profile_path, 'Default', 'Cookies')
print(f"\n📋 Expected location: {cookies_db}")

if os.path.exists(cookies_db):
    print(f"   ✅ EXISTS: {os.path.getsize(cookies_db):,} bytes")
    
    # Check content
    import sqlite3
    conn = sqlite3.connect(cookies_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM cookies")
    count = cursor.fetchone()[0]
    print(f"   📊 Contains {count} cookies")
    
    if count > 0:
        cursor.execute("SELECT name, host_key FROM cookies LIMIT 5")
        print(f"   🔍 Sample cookies:")
        for name, host in cursor.fetchall():
            print(f"      {name} ({host})")
    
    conn.close()
else:
    print(f"   ❌ DOES NOT EXIST!")
    
    # Check where it might be
    print(f"\n🔍 Searching for any 'Cookies' file...")
    all_cookie_files = []
    for root, dirs, files in os.walk(profile_path):
        if 'Cookies' in files:
            all_cookie_files.append(os.path.join(root, 'Cookies'))
    
    if all_cookie_files:
        print(f"   Found Cookies files at:")
        for path in all_cookie_files:
            print(f"      {os.path.relpath(path, profile_path)}")
    else:
        print(f"   ❌ No 'Cookies' file found anywhere!")
