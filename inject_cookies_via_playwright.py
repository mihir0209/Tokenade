"""
Inject cookies using Playwright's add_cookies() method

This lets Chrome handle the encryption automatically!
Instead of manually creating encrypted cookies, we use Playwright to:
1. Open a Chrome profile
2. Add cookies via the API
3. Chrome encrypts and saves them automatically
"""

import os
import json
from playwright.sync_api import sync_playwright
from datetime import datetime

def convert_chrome_time_to_unix(chrome_time):
    """Convert Chrome timestamp to Unix timestamp (seconds)"""
    if chrome_time == 0:
        return None
    
    # Chrome epoch: January 1, 1601
    # Unix epoch: January 1, 1970
    # Difference: 11644473600 seconds
    chrome_epoch_offset = 11644473600
    
    # Chrome time is in microseconds, convert to seconds
    unix_time = (chrome_time / 1000000) - chrome_epoch_offset
    
    return int(unix_time)

def inject_cookies_via_playwright(json_path, profile_path):
    """
    Inject cookies into Chrome profile using Playwright
    
    This method lets Chrome handle encryption automatically!
    """
    
    print(f"\n📁 Reading cookies from: {json_path}")
    
    # Load decrypted cookies
    with open(json_path, 'r', encoding='utf-8') as f:
        cookies = json.load(f)
    
    print(f"📊 Loaded {len(cookies)} cookies")
    
    # Create profile directory
    os.makedirs(profile_path, exist_ok=True)
    
    print(f"\n🚀 Launching Chrome with profile: {profile_path}")
    
    with sync_playwright() as p:
        # Launch persistent context (creates a real Chrome profile)
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            headless=True,
            channel="chrome"
        )
        
        print(f"✅ Chrome launched!")
        
        # Convert cookies to Playwright format
        print(f"\n🍪 Converting {len(cookies)} cookies to Playwright format...")
        
        playwright_cookies = []
        
        for cookie in cookies:
            try:
                # Convert Chrome timestamp to Unix timestamp
                expires = convert_chrome_time_to_unix(cookie.get('expires_utc', 0))
                
                # Get domain - must start with . for wildcard or be exact domain
                domain = cookie['host_key']
                
                # Build Playwright cookie
                pw_cookie = {
                    'name': cookie['name'],
                    'value': cookie['value'],
                    'domain': domain,
                    'path': cookie['path']
                }
                
                # Add optional fields
                if cookie.get('is_httponly', False):
                    pw_cookie['httpOnly'] = True
                
                if cookie.get('is_secure', False):
                    pw_cookie['secure'] = True
                
                # Add sameSite if not default
                samesite_value = cookie.get('samesite', -1)
                if samesite_value == 1:
                    pw_cookie['sameSite'] = 'Lax'
                elif samesite_value == 2:
                    pw_cookie['sameSite'] = 'Strict'
                elif cookie.get('is_secure', False):  # Secure cookies can use None
                    pw_cookie['sameSite'] = 'None'
                
                # Add expiration if valid
                if expires and expires > 0:
                    pw_cookie['expires'] = expires
                
                playwright_cookies.append(pw_cookie)
                
            except Exception as e:
                print(f"   ⚠️  Skipped cookie {cookie.get('name', 'unknown')}: {e}")
                continue
        
        print(f"✅ Converted {len(playwright_cookies)} cookies")
        
        # Add cookies to context
        print(f"\n💉 Injecting cookies into Chrome...")
        
        try:
            context.add_cookies(playwright_cookies)
            print(f"✅ Successfully injected all cookies!")
            
            # Verify cookies were added
            saved_cookies = context.cookies()
            print(f"\n📊 Verification: Chrome now has {len(saved_cookies)} cookies")
            
            # Show sample cookies
            print(f"\n🔍 Sample cookies:")
            for cookie in saved_cookies[:10]:
                print(f"   {cookie['name']} ({cookie['domain']})")
            if len(saved_cookies) > 10:
                print(f"   ... and {len(saved_cookies) - 10} more")
            
        except Exception as e:
            print(f"❌ Error adding cookies: {e}")
            import traceback
            traceback.print_exc()
        
        # Close Chrome (this saves the cookies to disk)
        print(f"\n💾 Closing Chrome to save cookies...")
        context.close()
    
    print(f"\n✅ Done! Cookies saved to: {profile_path}")
    
    return len(saved_cookies)

def inject_all_accounts():
    """Inject cookies for all accounts using Playwright"""
    
    base_dir = os.getcwd()
    decrypted_dir = os.path.join(base_dir, 'decrypted_cookies')
    browser_data_base = os.path.join(base_dir, 'browser_data')
    
    print("\n" + "=" * 80)
    print("PLAYWRIGHT COOKIE INJECTION - Let Chrome Handle Encryption!")
    print("=" * 80)
    
    if not os.path.exists(decrypted_dir):
        print(f"\n❌ Decrypted cookies directory not found: {decrypted_dir}")
        return
    
    # Find all decrypted cookie JSON files
    json_files = [f for f in os.listdir(decrypted_dir) if f.endswith('_cookies.json')]
    
    if not json_files:
        print(f"\n❌ No decrypted cookie files found")
        return
    
    print(f"\n📋 Found {len(json_files)} cookie file(s)")
    
    success_count = 0
    
    for json_file in sorted(json_files):
        # Extract account number
        account_num = json_file.split('_')[1]
        
        json_path = os.path.join(decrypted_dir, json_file)
        profile_path = os.path.join(browser_data_base, account_num)
        
        print(f"\n{'=' * 80}")
        print(f"Account {account_num}")
        print(f"{'=' * 80}")
        
        try:
            count = inject_cookies_via_playwright(json_path, profile_path)
            if count > 0:
                success_count += 1
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n\n" + "=" * 80)
    print("INJECTION COMPLETE")
    print("=" * 80)
    print(f"\n✅ Successfully injected: {success_count}/{len(json_files)} accounts")
    print(f"\n📁 Profiles created in: {browser_data_base}")
    print(f"\n🚀 Chrome has encrypted the cookies automatically!")
    print(f"\n📋 Next steps:")
    print(f"   1. Use these profiles with collect_all_cookies.py")
    print(f"   2. Your Google sessions should work!")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Inject specific account
        account_num = sys.argv[1]
        base_dir = os.getcwd()
        json_path = os.path.join(base_dir, 'decrypted_cookies', f'account_{account_num}_cookies.json')
        profile_path = os.path.join(base_dir, 'browser_data', account_num)
        
        print("=" * 80)
        print(f"INJECTING ACCOUNT {account_num} VIA PLAYWRIGHT")
        print("=" * 80)
        
        inject_cookies_via_playwright(json_path, profile_path)
    else:
        # Inject all accounts
        inject_all_accounts()
