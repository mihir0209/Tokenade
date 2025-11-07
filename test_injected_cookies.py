"""
Analyze the browser_data folders that were created
"""

import os
import sqlite3

def analyze_cookie_db(db_path, label):
    """Analyze a cookie database"""
    print("\n" + "=" * 80)
    print(label)
    print("=" * 80)
    
    if not os.path.exists(db_path):
        print(f"❌ Not found: {db_path}")
        return False
    
    print(f"📁 Path: {db_path}")
    print(f"📊 Size: {os.path.getsize(db_path):,} bytes")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get schema
        cursor.execute("PRAGMA table_info(cookies)")
        columns = cursor.fetchall()
        print(f"\n🔍 Schema ({len(columns)} columns):")
        for col in columns:
            col_id, col_name, col_type, not_null, default_val, pk = col
            print(f"   {col_name}: {col_type}")
        
        # Count cookies
        cursor.execute("SELECT COUNT(*) FROM cookies")
        count = cursor.fetchone()[0]
        print(f"\n📊 Total cookies: {count}")
        
        # Check storage type
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN LENGTH(value) > 0 THEN 1 ELSE 0 END) as plain,
                SUM(CASE WHEN LENGTH(encrypted_value) > 0 THEN 1 ELSE 0 END) as encrypted
            FROM cookies
        """)
        plain, encrypted = cursor.fetchone()
        print(f"   📝 Plain text (value): {plain}")
        print(f"   🔒 Encrypted (encrypted_value): {encrypted}")
        
        # Sample cookies
        cursor.execute("""
            SELECT name, host_key, 
                   LENGTH(value) as val_len, 
                   LENGTH(encrypted_value) as enc_len,
                   expires_utc
            FROM cookies 
            LIMIT 5
        """)
        
        print(f"\n🔍 Sample cookies:")
        for name, host, val_len, enc_len, expires in cursor.fetchall():
            storage = "PLAIN" if val_len > 0 else "ENCRYPTED" if enc_len > 0 else "EMPTY"
            print(f"   {name} ({host})")
            print(f"      Storage: {storage} (val={val_len}B, enc={enc_len}B)")
            print(f"      Expires: {expires}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

base_dir = os.getcwd()

print("=" * 80)
print("ANALYZING BROWSER_DATA FOLDERS")
print("=" * 80)

# Check injected cookies
for account_num in [1, 2]:
    db_path = os.path.join(base_dir, 'browser_data', str(account_num), 'Default', 'Network', 'Cookies')
    analyze_cookie_db(db_path, f"INJECTED COOKIES - Account {account_num}")

# Now let's check what happens when we use that profile with Playwright
print("\n\n" + "=" * 80)
print("TESTING: Can Playwright READ our injected cookies?")
print("=" * 80)

try:
    from playwright.sync_api import sync_playwright
    
    profile_path = os.path.join(base_dir, 'browser_data', '1')
    
    print(f"\n📁 Using profile: {profile_path}")
    
    with sync_playwright() as p:
        print("\n🚀 Launching Chrome with injected cookies...")
        
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            headless=True,
            channel="chrome"
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        print("✅ Chrome launched!")
        
        # Check if cookies are loaded
        print("\n🍪 Checking cookies in context...")
        cookies = context.cookies()
        
        print(f"\n📊 Total cookies loaded: {len(cookies)}")
        
        if cookies:
            print("\n🔍 Sample cookies loaded by Chrome:")
            for cookie in cookies[:10]:
                print(f"   {cookie['name']} ({cookie['domain']})")
                print(f"      Value: {cookie['value'][:50]}..." if len(cookie['value']) > 50 else f"      Value: {cookie['value']}")
        else:
            print("❌ No cookies were loaded by Chrome!")
            print("   This means Chrome is NOT reading our injected cookies.")
        
        context.close()
        
        print("\n✅ Test complete!")
        
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
