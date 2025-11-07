"""
Test what happens to cookies AFTER Chrome opens the profile

We'll check the database before and after Chrome opens it.
"""

import sqlite3
import os
from playwright.sync_api import sync_playwright

def count_cookies(db_path):
    """Count cookies in database"""
    if not os.path.exists(db_path):
        return 0
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM cookies")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_cookie_details(db_path):
    """Get details about cookies"""
    if not os.path.exists(db_path):
        return []
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, host_key, 
               LENGTH(value) as val_len,
               LENGTH(encrypted_value) as enc_len
        FROM cookies
        ORDER BY name
    """)
    cookies = cursor.fetchall()
    conn.close()
    return cookies

base_dir = os.getcwd()
profile_path = os.path.join(base_dir, 'browser_data', '1')
db_path = os.path.join(profile_path, 'Default', 'Network', 'Cookies')

print("=" * 80)
print("TESTING: What Chrome does with our injected cookies")
print("=" * 80)

# Check BEFORE Chrome opens
before_count = count_cookies(db_path)
before_cookies = get_cookie_details(db_path)

print(f"\n📊 BEFORE Chrome opens:")
print(f"   Total cookies: {before_count}")
print(f"\n   Storage format:")
for name, host, val_len, enc_len in before_cookies[:5]:
    storage = "PLAIN" if val_len > 0 else "ENCRYPTED" if enc_len > 0 else "EMPTY"
    print(f"   {name}: {storage} (value={val_len}B, encrypted={enc_len}B)")
if len(before_cookies) > 5:
    print(f"   ... and {len(before_cookies) - 5} more")

# Now open with Chrome
print(f"\n🚀 Opening Chrome with profile...")

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=profile_path,
        headless=True,
        channel="chrome"
    )
    
    page = context.pages[0] if context.pages else context.new_page()
    
    print(f"✅ Chrome opened!")
    
    # Check cookies in Playwright context
    playwright_cookies = context.cookies()
    print(f"\n🍪 Playwright sees {len(playwright_cookies)} cookies in context")
    
    # Navigate to a Google page to trigger cookie loading
    print(f"\n🌐 Navigating to mail.google.com...")
    page.goto('https://mail.google.com', wait_until='domcontentloaded', timeout=10000)
    
    # Check cookies again after navigation
    playwright_cookies_after = context.cookies()
    print(f"🍪 After navigation: {len(playwright_cookies_after)} cookies")
    
    # Close Chrome
    context.close()

print(f"\n✅ Chrome closed")

# Check AFTER Chrome closes
print(f"\n📊 AFTER Chrome closes:")

# Wait a moment for Chrome to finish writing
import time
time.sleep(1)

after_count = count_cookies(db_path)
after_cookies = get_cookie_details(db_path)

print(f"   Total cookies: {after_count}")

if after_count != before_count:
    print(f"\n   ⚠️  CHANGED: {before_count} → {after_count} ({after_count - before_count:+d})")
else:
    print(f"\n   ✅ No change in count")

print(f"\n   Storage format:")
for name, host, val_len, enc_len in after_cookies[:5]:
    storage = "PLAIN" if val_len > 0 else "ENCRYPTED" if enc_len > 0 else "EMPTY"
    print(f"   {name}: {storage} (value={val_len}B, encrypted={enc_len}B)")
if len(after_cookies) > 5:
    print(f"   ... and {len(after_cookies) - 5} more")

# Compare what changed
print(f"\n🔍 Analyzing changes...")

before_keys = {(name, host) for name, host, _, _ in before_cookies}
after_keys = {(name, host) for name, host, _, _ in after_cookies}

added = after_keys - before_keys
removed = before_keys - after_keys

if added:
    print(f"\n➕ Added cookies ({len(added)}):")
    for name, host in sorted(list(added)[:10]):
        print(f"   {name} ({host})")

if removed:
    print(f"\n➖ Removed cookies ({len(removed)}):")
    for name, host in sorted(list(removed)[:10]):
        print(f"   {name} ({host})")

# Check if encryption changed
before_plain = sum(1 for _, _, val_len, _ in before_cookies if val_len > 0)
after_plain = sum(1 for _, _, val_len, _ in after_cookies if val_len > 0)

before_encrypted = sum(1 for _, _, _, enc_len in before_cookies if enc_len > 0)
after_encrypted = sum(1 for _, _, _, enc_len in after_cookies if enc_len > 0)

print(f"\n📋 Encryption status:")
print(f"   BEFORE: {before_plain} plain, {before_encrypted} encrypted")
print(f"   AFTER:  {after_plain} plain, {after_encrypted} encrypted")

if before_plain > 0 and after_plain == 0 and after_encrypted > 0:
    print(f"\n   ✅ Chrome re-encrypted all plain-text cookies!")
