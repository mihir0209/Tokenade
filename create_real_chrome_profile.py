"""
Create a real Chrome profile with Playwright and analyze its cookies database
"""

import os
from playwright.sync_api import sync_playwright
import sqlite3

def analyze_real_chrome():
    base_dir = os.getcwd()
    test_profile = os.path.join(base_dir, 'test_chrome_profile')
    
    print("=" * 80)
    print("CREATING REAL CHROME PROFILE")
    print("=" * 80)
    
    print(f"\n📁 Profile path: {test_profile}")
    
    with sync_playwright() as p:
        print("\n🚀 Launching Chrome...")
        
        # Use Chrome browser (not Chromium)
        browser_type = p.chromium
        
        context = browser_type.launch_persistent_context(
            user_data_dir=test_profile,
            headless=False,
            channel="chrome"  # Use real Chrome
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        print("✅ Chrome launched!")
        print("\n📋 Adding test cookies...")
        
        # Add some test cookies
        context.add_cookies([
            {
                'name': 'test_cookie',
                'value': 'test_value_123',
                'domain': '.google.com',
                'path': '/',
                'expires': 2000000000,
                'httpOnly': True,
                'secure': True
            },
            {
                'name': 'SID',
                'value': 'test_sid_value',
                'domain': '.google.com',
                'path': '/',
                'expires': 2000000000,
                'httpOnly': False,
                'secure': False
            }
        ])
        
        print("✅ Cookies added!")
        
        # Navigate to trigger cookie save
        print("\n🌐 Navigating to google.com...")
        page.goto('https://www.google.com', wait_until='networkidle')
        
        print("✅ Page loaded!")
        
        # Wait a bit for cookies to be written
        page.wait_for_timeout(2000)
        
        context.close()
    
    print("\n✅ Profile created!")
    
    # Analyze the cookies database
    cookies_db = os.path.join(test_profile, 'Default', 'Network', 'Cookies')
    
    if os.path.exists(cookies_db):
        print("\n" + "=" * 80)
        print("ANALYZING REAL CHROME COOKIES DATABASE")
        print("=" * 80)
        
        print(f"\n📁 Database: {cookies_db}")
        print(f"📊 Size: {os.path.getsize(cookies_db):,} bytes")
        
        conn = sqlite3.connect(cookies_db)
        cursor = conn.cursor()
        
        # Schema
        cursor.execute("PRAGMA table_info(cookies)")
        columns = cursor.fetchall()
        print(f"\n🔍 Schema ({len(columns)} columns):")
        for col in columns:
            col_id, col_name, col_type, not_null, default_val, pk = col
            nullable = "NOT NULL" if not_null else "NULL"
            pk_str = " PRIMARY KEY" if pk else ""
            default_str = f" DEFAULT {default_val}" if default_val is not None else ""
            print(f"   {col_name}: {col_type} {nullable}{default_str}{pk_str}")
        
        # Count cookies
        cursor.execute("SELECT COUNT(*) FROM cookies")
        count = cursor.fetchone()[0]
        print(f"\n📊 Total cookies: {count}")
        
        # Encryption check
        cursor.execute("""
            SELECT 
                name,
                LENGTH(value) as val_len,
                LENGTH(encrypted_value) as enc_len,
                CASE 
                    WHEN LENGTH(value) > 0 THEN 'PLAIN'
                    WHEN LENGTH(encrypted_value) > 0 THEN 'ENCRYPTED'
                    ELSE 'EMPTY'
                END as storage_type
            FROM cookies
            LIMIT 10
        """)
        
        print(f"\n🔍 Cookie storage analysis:")
        for name, val_len, enc_len, storage_type in cursor.fetchall():
            print(f"   {name}: {storage_type} (value={val_len}B, encrypted={enc_len}B)")
        
        # Meta table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        if 'meta' in tables:
            cursor.execute("SELECT key, value FROM meta")
            print(f"\n📋 Meta table:")
            for key, value in cursor.fetchall():
                print(f"   {key} = {value}")
        
        conn.close()
    else:
        print(f"\n❌ Cookies database not found at: {cookies_db}")


if __name__ == "__main__":
    try:
        analyze_real_chrome()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
