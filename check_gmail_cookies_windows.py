"""
Check Windows Chrome for Gmail cookies and collect them if needed
"""

import sqlite3
import os

def check_gmail_cookies_windows():
    """Check if Windows Chrome has Gmail cookies"""
    
    print("=" * 80)
    print("CHECKING WINDOWS CHROME FOR GMAIL COOKIES")
    print("=" * 80)
    
    # Check browser_data for Gmail cookies
    for account_num in [1, 2]:
        cookies_db = f"browser_data/{account_num}/Default/Network/Cookies"
        
        if not os.path.exists(cookies_db):
            print(f"\n❌ Account {account_num}: No cookies database found")
            continue
        
        print(f"\n📋 Account {account_num}:")
        
        conn = sqlite3.connect(cookies_db)
        cursor = conn.cursor()
        
        # Check for Gmail cookies
        cursor.execute("""
            SELECT name, host_key, LENGTH(encrypted_value)
            FROM cookies
            WHERE host_key LIKE '%mail.google%'
            ORDER BY name
        """)
        
        gmail_cookies = cursor.fetchall()
        
        if gmail_cookies:
            print(f"   ✅ Has {len(gmail_cookies)} Gmail cookies:")
            for name, host, enc_len in gmail_cookies:
                print(f"      {name} ({host}) - {enc_len} bytes encrypted")
        else:
            print(f"   ❌ NO Gmail cookies found!")
            print(f"      This means Gmail was never opened in this profile on Windows")
        
        # Check all Google cookies
        cursor.execute("""
            SELECT DISTINCT host_key
            FROM cookies
            WHERE host_key LIKE '%google%'
            ORDER BY host_key
        """)
        
        all_google = cursor.fetchall()
        
        print(f"\n   📊 All Google domains with cookies:")
        for (host,) in all_google:
            cursor.execute("SELECT COUNT(*) FROM cookies WHERE host_key = ?", (host,))
            count = cursor.fetchone()[0]
            
            has_gmail = '📧' if 'mail' in host else ''
            has_labs = '🧪' if 'labs' in host else ''
            has_accounts = '🔑' if 'accounts' in host else ''
            
            print(f"      {has_gmail}{has_labs}{has_accounts} {host}: {count} cookies")
        
        conn.close()
    
    print("\n" + "=" * 80)
    print("SOLUTION")
    print("=" * 80)
    
    print("""
To get Gmail cookies on Windows:

1. Open Chrome with the profile:
   python setup_accounts.py
   
2. Navigate to mail.google.com
   - This creates Gmail-specific cookies (OSID, COMPASS, etc.)
   
3. Re-decrypt cookies:
   python decrypt_cookies_windows.py
   
4. Transfer and inject again:
   - Copy decrypted_cookies/ to Linux
   - python3 inject_cookies_via_playwright.py

Alternative (easier):
   Just do fresh login on Linux VPS:
   - python3 setup_accounts.py (on VPS)
   - Login manually once
   - Cookies persist forever
""")

if __name__ == "__main__":
    check_gmail_cookies_windows()
