"""
Compare Cookie Databases - Injected vs Real Chrome

This script compares:
1. Our manually injected cookies database
2. A real Linux Chrome cookies database created by Playwright

This will help us understand what's missing or different.
"""

import sqlite3
import os

def analyze_db(db_path, label):
    """Analyze a cookies database"""
    
    print("\n" + "=" * 80)
    print(f"{label}")
    print("=" * 80)
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        return
    
    print(f"📁 Path: {db_path}")
    print(f"📊 Size: {os.path.getsize(db_path):,} bytes")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"\n📋 Tables: {', '.join(tables)}")
    
    # Check cookies table schema
    if 'cookies' in tables:
        cursor.execute("PRAGMA table_info(cookies)")
        columns = cursor.fetchall()
        print(f"\n🔍 Cookies table columns ({len(columns)}):")
        for col in columns:
            col_id, col_name, col_type, not_null, default_val, pk = col
            print(f"   {col_name} ({col_type})")
        
        # Count cookies
        cursor.execute("SELECT COUNT(*) FROM cookies")
        count = cursor.fetchone()[0]
        print(f"\n📊 Total cookies: {count}")
        
        # Check for encrypted vs plain text
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN LENGTH(encrypted_value) > 0 THEN 1 ELSE 0 END) as encrypted,
                SUM(CASE WHEN LENGTH(value) > 0 THEN 1 ELSE 0 END) as plain_text
            FROM cookies
        """)
        encrypted, plain = cursor.fetchone()
        print(f"   🔒 Encrypted: {encrypted}")
        print(f"   📝 Plain text: {plain}")
        
        # Sample Google cookies
        cursor.execute("""
            SELECT name, host_key, LENGTH(value), LENGTH(encrypted_value)
            FROM cookies 
            WHERE host_key LIKE '%google%'
            LIMIT 5
        """)
        print(f"\n🔍 Sample Google cookies:")
        for name, host, val_len, enc_len in cursor.fetchall():
            print(f"   {name} ({host}): value={val_len}B, encrypted={enc_len}B")
    
    # Check meta table
    if 'meta' in tables:
        cursor.execute("SELECT key, value FROM meta")
        print(f"\n📋 Meta table:")
        for key, value in cursor.fetchall():
            print(f"   {key} = {value}")
    
    conn.close()


def main():
    print("\n" + "=" * 80)
    print("COOKIE DATABASE COMPARISON")
    print("=" * 80)
    
    base_dir = os.getcwd()
    
    # Analyze injected database
    injected_db = os.path.join(base_dir, 'browser_data', '1', 'Default', 'Network', 'Cookies')
    analyze_db(injected_db, "INJECTED COOKIES (Our Manual Injection)")
    
    # We need to create a real Chrome profile for comparison
    print("\n\n" + "=" * 80)
    print("CREATING REAL CHROME PROFILE FOR COMPARISON")
    print("=" * 80)
    
    print("\n📋 We need to create a real Linux Chrome cookies database to compare.")
    print("   Let's create one using Playwright...")
    
    try:
        from playwright.sync_api import sync_playwright
        
        test_profile = os.path.join(base_dir, 'test_chrome_profile')
        
        print(f"\n🚀 Creating test Chrome profile at: {test_profile}")
        
        with sync_playwright() as p:
            # Create a real Chrome profile
            context = p.chromium.launch_persistent_context(
                user_data_dir=test_profile,
                headless=True
            )
            
            page = context.pages[0]
            
            # Set a test cookie
            context.add_cookies([{
                'name': 'test_cookie',
                'value': 'test_value',
                'domain': '.example.com',
                'path': '/'
            }])
            
            context.close()
        
        print(f"✅ Test profile created!")
        
        # Analyze real Chrome database
        real_db = os.path.join(test_profile, 'Default', 'Network', 'Cookies')
        analyze_db(real_db, "REAL CHROME COOKIES (Playwright Created)")
        
        # Compare side by side
        print("\n\n" + "=" * 80)
        print("COMPARISON SUMMARY")
        print("=" * 80)
        
        print("\n📋 Key differences to investigate:")
        print("   1. Schema differences (column count, types)")
        print("   2. Encryption method (encrypted_value vs value)")
        print("   3. Meta table version numbers")
        print("   4. Cookie flags and attributes")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
