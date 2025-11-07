"""
Open Gmail in Windows Chrome profiles to collect Gmail cookies

This script will:
1. Open each profile
2. Navigate to mail.google.com
3. Wait for Gmail to load
4. Close (cookies saved automatically)
"""

from playwright.sync_api import sync_playwright
import os
import time

def collect_gmail_cookies():
    """Visit Gmail to collect Gmail-specific cookies"""
    
    base_dir = os.getcwd()
    
    print("=" * 80)
    print("COLLECTING GMAIL COOKIES")
    print("=" * 80)
    
    accounts = [1, 2]
    
    for account_num in accounts:
        profile_path = os.path.join(base_dir, 'browser_data', str(account_num))
        
        if not os.path.exists(profile_path):
            print(f"\n❌ Account {account_num}: Profile not found")
            continue
        
        print(f"\n📋 Account {account_num}")
        print(f"   📁 Profile: {profile_path}")
        
        with sync_playwright() as p:
            print(f"   🚀 Opening Chrome...")
            
            context = p.chromium.launch_persistent_context(
                user_data_dir=profile_path,
                headless=False,  # Show browser so you can see it working
                channel="msedge"  # Use Edge on Windows
            )
            
            page = context.pages[0] if context.pages else context.new_page()
            
            print(f"   ✅ Chrome opened")
            
            # Navigate to Gmail
            print(f"   🌐 Navigating to mail.google.com...")
            
            try:
                page.goto('https://mail.google.com', wait_until='networkidle', timeout=30000)
                print(f"   ✅ Gmail loaded")
                
                # Wait for Gmail to fully load
                print(f"   ⏳ Waiting for Gmail to initialize...")
                time.sleep(5)
                
                # Check if logged in
                cookies = context.cookies()
                gmail_cookies = [c for c in cookies if 'mail.google' in c['domain']]
                
                print(f"   📊 Gmail cookies collected: {len(gmail_cookies)}")
                
                if gmail_cookies:
                    print(f"   ✅ Success! Gmail cookies:")
                    for cookie in gmail_cookies[:5]:
                        print(f"      {cookie['name']}")
                else:
                    print(f"   ⚠️  No Gmail cookies - might need to login")
                
            except Exception as e:
                print(f"   ❌ Error: {e}")
            
            print(f"   💾 Closing Chrome (cookies will be saved)...")
            context.close()
        
        print(f"   ✅ Done!")
    
    print("\n" + "=" * 80)
    print("NEXT STEPS")
    print("=" * 80)
    print("""
1. Run: python decrypt_cookies_windows.py
   - This will include the new Gmail cookies

2. Copy decrypted_cookies/ to Linux

3. Run on Linux: python3 inject_cookies_via_playwright.py

4. Test: python3 collect_all_cookies.py
""")

if __name__ == "__main__":
    collect_gmail_cookies()
