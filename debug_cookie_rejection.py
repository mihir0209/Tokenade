"""
Debug: Why are cookies being deleted after injection?

Check if cookies are being rejected due to:
1. Wrong encryption format
2. Expired cookies  
3. Invalid domains
4. Missing required fields
"""

import sqlite3
import os
import json

def debug_cookie_rejection():
    base_dir = os.getcwd()
    
    # Check the database BEFORE Chrome opens it
    db_path = os.path.join(base_dir, 'browser_data', '1', 'Default', 'Network', 'Cookies')
    json_path = os.path.join(base_dir, 'decrypted_cookies', 'account_1_cookies.json')
    
    print("=" * 80)
    print("DEBUGGING COOKIE REJECTION")
    print("=" * 80)
    
    #Load JSON
    with open(json_path, 'r') as f:
        json_cookies = json.load(f)
    
    print(f"\n📊 JSON file has: {len(json_cookies)} cookies")
    
    # Check database
    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM cookies")
    db_count = cursor.fetchone()[0]
    
    print(f"📊 Database has: {db_count} cookies")
    print(f"\n⚠️  MISMATCH: {len(json_cookies) - db_count} cookies missing!")
    
    # Check which cookies ARE in the database
    cursor.execute("SELECT name, host_key FROM cookies")
    db_cookies = {(name, host) for name, host in cursor.fetchall()}
    
    print(f"\n✅ Cookies IN database:")
    for name, host in sorted(db_cookies):
        print(f"   {name} ({host})")
    
    # Check which cookies are MISSING
    json_cookie_keys = {(c['name'], c['host_key']) for c in json_cookies}
    missing = json_cookie_keys - db_cookies
    
    print(f"\n❌ Cookies MISSING from database ({len(missing)}):")
    for name, host in sorted(list(missing)[:10]):
        print(f"   {name} ({host})")
    if len(missing) > 10:
        print(f"   ... and {len(missing) - 10} more")
    
    # Analyze the missing cookies - what do they have in common?
    missing_cookies = [c for c in json_cookies if (c['name'], c['host_key']) in missing]
    
    print(f"\n🔍 Analyzing missing cookies...")
    
    # Check domains
    domains = {}
    for c in missing_cookies:
        domain = c['host_key']
        domains[domain] = domains.get(domain, 0) + 1
    
    print(f"\n📋 Missing cookies by domain:")
    for domain, count in sorted(domains.items(), key=lambda x: -x[1])[:10]:
        print(f"   {domain}: {count} cookies")
    
    # Check if they're all google cookies
    google_missing = [c for c in missing_cookies if 'google' in c['host_key'].lower()]
    print(f"\n📋 Missing Google cookies: {len(google_missing)}/{len(missing_cookies)}")
    
    conn.close()

if __name__ == "__main__":
    debug_cookie_rejection()
