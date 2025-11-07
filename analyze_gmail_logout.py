"""
Analyze which cookies are being transferred vs which are missing

This will help us understand why Gmail is logged out.
"""

import json
import os

def analyze_cookie_transfer():
    """Compare what we decrypt vs what gets injected"""
    
    base_dir = os.getcwd()
    
    # Check decrypted cookies
    json_path = os.path.join(base_dir, 'decrypted_cookies', 'account_1_cookies.json')
    
    if not os.path.exists(json_path):
        print("❌ No decrypted cookies found")
        return
    
    with open(json_path, 'r') as f:
        decrypted_cookies = json.load(f)
    
    print("=" * 80)
    print("COOKIE TRANSFER ANALYSIS")
    print("=" * 80)
    
    print(f"\n📊 Total decrypted cookies: {len(decrypted_cookies)}")
    
    # Categorize cookies
    gmail_cookies = []
    accounts_cookies = []
    labs_cookies = []
    other_google = []
    
    for cookie in decrypted_cookies:
        host = cookie['host_key']
        name = cookie['name']
        
        if 'mail.google' in host:
            gmail_cookies.append(cookie)
        elif 'accounts.google' in host:
            accounts_cookies.append(cookie)
        elif 'labs.google' in host:
            labs_cookies.append(cookie)
        elif 'google' in host:
            other_google.append(cookie)
    
    print(f"\n📋 Cookie breakdown by domain:")
    print(f"   📧 Gmail (mail.google.com): {len(gmail_cookies)}")
    print(f"   🔑 Accounts (accounts.google.com): {len(accounts_cookies)}")
    print(f"   🧪 Labs (labs.google): {len(labs_cookies)}")
    print(f"   🌐 Other Google domains: {len(other_google)}")
    
    # Critical authentication cookies
    critical_cookies = [
        'SID', '__Secure-1PSID', '__Secure-3PSID',
        'HSID', 'SSID', 
        'APISID', 'SAPISID',
        '__Secure-1PAPISID', '__Secure-3PAPISID',
        'OSID', '__Secure-OSID',
        '__Host-GAPS'
    ]
    
    print(f"\n🔑 Critical authentication cookies:")
    
    found_critical = {}
    for cookie in decrypted_cookies:
        if cookie['name'] in critical_cookies:
            domain = cookie['host_key']
            if cookie['name'] not in found_critical:
                found_critical[cookie['name']] = []
            found_critical[cookie['name']].append(domain)
    
    for name in critical_cookies:
        if name in found_critical:
            domains = ', '.join(found_critical[name])
            print(f"   ✅ {name}: {domains}")
        else:
            print(f"   ❌ {name}: MISSING")
    
    # Check if injected cookies work
    print(f"\n🔍 Checking injected cookies in browser_data...")
    
    browser_data = os.path.join(base_dir, 'browser_data', '1', 'Default', 'Cookies')
    
    if os.path.exists(browser_data):
        import sqlite3
        conn = sqlite3.connect(browser_data)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM cookies")
        injected_count = cursor.fetchone()[0]
        
        print(f"   📊 Cookies in database: {injected_count}")
        
        # Check critical cookies
        cursor.execute("""
            SELECT name, host_key 
            FROM cookies 
            WHERE name IN ({})
        """.format(','.join(f"'{c}'" for c in critical_cookies)))
        
        injected_critical = cursor.fetchall()
        
        print(f"\n   🔑 Critical cookies in database: {len(injected_critical)}")
        for name, host in injected_critical:
            print(f"      {name} ({host})")
        
        # Check for Gmail-specific cookies
        cursor.execute("""
            SELECT name, host_key 
            FROM cookies 
            WHERE host_key LIKE '%mail.google%'
        """)
        
        gmail_db = cursor.fetchall()
        print(f"\n   📧 Gmail cookies in database: {len(gmail_db)}")
        for name, host in gmail_db:
            print(f"      {name} ({host})")
        
        conn.close()
    else:
        print(f"   ❌ No browser_data found")
    
    print("\n" + "=" * 80)
    print("DIAGNOSIS")
    print("=" * 80)
    
    print("""
Possible reasons Gmail is logged out:

1. ❌ OSID cookie missing/invalid
   - OSID is the "Origin Session ID" for Gmail
   - Without valid OSID, Gmail shows as logged out
   
2. ❌ Cookie domain mismatch
   - Some cookies might be for .google.co.in instead of .google.com
   - Browser location/region mismatch
   
3. ❌ Session validation failed
   - Google checks IP address, user agent, device fingerprint
   - Different environment = different fingerprint = logout
   
4. ❌ Missing session cookies
   - __Secure-OSID might be required
   - COMPASS cookie might be needed
   
5. ⏰ Cookies expired
   - Even though we transferred them, they might have expired
   - Google sessions can expire based on activity
""")
    
    # Check cookie expiration
    print("\n🕐 Checking cookie expiration...")
    from datetime import datetime
    
    now_chrome_time = int((datetime.now() - datetime(1601, 1, 1)).total_seconds() * 1000000)
    
    expired = 0
    expiring_soon = 0
    
    for cookie in decrypted_cookies:
        expires = cookie.get('expires_utc', 0)
        if expires > 0:
            if expires < now_chrome_time:
                expired += 1
            elif expires < now_chrome_time + (7 * 24 * 60 * 60 * 1000000):  # 7 days
                expiring_soon += 1
    
    print(f"   ⚠️  Expired cookies: {expired}")
    print(f"   ⏰ Expiring within 7 days: {expiring_soon}")
    print(f"   ✅ Valid long-term: {len(decrypted_cookies) - expired - expiring_soon}")

if __name__ == "__main__":
    analyze_cookie_transfer()
