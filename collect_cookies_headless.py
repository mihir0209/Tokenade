"""
Multi-Account Cookie Collector - Headless Mode

This script collects cookies from all configured accounts.
Runs in HEADLESS mode - fast and automatic.

If an account is logged out, it will automatically re-login.
"""

from playwright.sync_api import sync_playwright
import json
import time
import os
from datetime import datetime

# Configuration
ACCOUNTS_FILE = "accounts.json"
BROWSER_DATA_BASE = "browser_data"
COOKIES_OUTPUT_DIR = "cookies_output"

# URLs
GOOGLE_LABS_URL = "https://labs.google/fx/tools/flow"


def load_accounts():
    """Load accounts from JSON file"""
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, 'r') as f:
            return json.load(f)
    return []


def collect_cookies_for_account(account_number, email, password, headless=True):
    """
    Collect cookies for a single account
    
    Args:
        account_number: The account number
        email: Google account email
        password: Google account password (for re-login if needed)
        headless: Run in headless mode
    
    Returns:
        dict: Cookies and access token, or None if failed
    """
    
    user_data_dir = os.path.join(BROWSER_DATA_BASE, str(account_number))
    os.makedirs(user_data_dir, exist_ok=True)
    
    print(f"\n{'=' * 80}")
    print(f"Account #{account_number}: {email}")
    print(f"{'=' * 80}")
    
    with sync_playwright() as p:
        # Launch with persistent context
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=headless,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled'],
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        try:
            # Check if already logged in
            print("   🔍 Checking session...")
            
            try:
                response = page.goto('https://labs.google/fx/api/auth/session', wait_until='networkidle', timeout=15000)
                
                if response.status == 200:
                    session_data = response.json()
                    
                    if 'access_token' in session_data:
                        print("   ✅ Already logged in!")
                        
                        # Extract cookies
                        cookies = context.cookies()
                        
                        result = {
                            'account_number': account_number,
                            'email': email,
                            'access_token': session_data['access_token'],
                            'expires': session_data.get('expires', ''),
                            'user': session_data.get('user', {}),
                            'cookies': {cookie['name']: cookie['value'] for cookie in cookies},
                            'timestamp': datetime.now().isoformat()
                        }
                        
                        print(f"   ✓ Token: {result['access_token'][:60]}...")
                        return result
            except:
                pass
            
            # Need to re-login
            print("   ⚠ Not logged in. Re-authenticating...")
            
            # Navigate to Flow page
            page.goto(GOOGLE_LABS_URL, wait_until='networkidle', timeout=30000)
            time.sleep(2)
            
            # Click Sign in with Google
            try:
                sign_in_button = page.wait_for_selector('text="Sign in with Google"', timeout=10000)
                if sign_in_button:
                    sign_in_button.click()
                    time.sleep(3)
            except:
                print("   ⚠ Could not find sign-in button")
            
            # Check if Google offers account selection
            print("   🔍 Checking for account selection...")
            try:
                # Look for the email in account selection
                account_option = page.wait_for_selector(f'text="{email}"', timeout=5000)
                if account_option:
                    print(f"   ✓ Found account in list: {email}")
                    account_option.click()
                    time.sleep(3)
                    
                    # Might need password
                    try:
                        password_input = page.wait_for_selector('input[type="password"]', timeout=5000)
                        if password_input:
                            print("   🔒 Entering password...")
                            password_input.fill(password)
                            next_button = page.wait_for_selector('button:has-text("Next")', timeout=5000)
                            next_button.click()
                            time.sleep(5)
                    except:
                        pass
            except:
                # No account selection, do full login
                print("   ➜ Full login required...")
                
                # Email
                email_input = page.wait_for_selector('input[type="email"]', timeout=15000)
                email_input.fill(email)
                next_button = page.wait_for_selector('button:has-text("Next")', timeout=5000)
                next_button.click()
                time.sleep(3)
                
                # Password
                password_input = page.wait_for_selector('input[type="password"]', timeout=15000)
                password_input.fill(password)
                next_button = page.wait_for_selector('button:has-text("Next")', timeout=5000)
                next_button.click()
                time.sleep(5)
            
            # Verify login
            print("   🔍 Verifying login...")
            time.sleep(3)
            
            response = page.goto('https://labs.google/fx/api/auth/session', wait_until='networkidle', timeout=15000)
            
            if response.status == 200:
                session_data = response.json()
                
                if 'access_token' in session_data:
                    print("   ✅ Login successful!")
                    
                    cookies = context.cookies()
                    
                    result = {
                        'account_number': account_number,
                        'email': email,
                        'access_token': session_data['access_token'],
                        'expires': session_data.get('expires', ''),
                        'user': session_data.get('user', {}),
                        'cookies': {cookie['name']: cookie['value'] for cookie in cookies},
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    print(f"   ✓ Token: {result['access_token'][:60]}...")
                    return result
            
            print("   ❌ Could not verify login")
            return None
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return None
            
        finally:
            context.close()


def main():
    print("\n" + "=" * 80)
    print("MULTI-ACCOUNT COOKIE COLLECTOR - Headless Mode")
    print("=" * 80)
    
    # Load accounts
    accounts = load_accounts()
    
    if not accounts:
        print("\n❌ No accounts configured!")
        print("\n📝 Run 'python setup_multi_accounts.py' first to set up your accounts.")
        return
    
    print(f"\n📋 Found {len(accounts)} account(s) to process")
    print(f"⏱  Starting collection at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Ask for headless mode
    mode = input("\n🎯 Run in headless mode? (yes/no, default=yes): ").strip().lower()
    headless = mode not in ['no', 'n']
    
    print(f"\n🚀 Mode: {'Headless (invisible)' if headless else 'Visible'}")
    print("\n" + "=" * 80)
    
    # Create output directory
    os.makedirs(COOKIES_OUTPUT_DIR, exist_ok=True)
    
    # Collect from all accounts
    results = []
    successful = 0
    failed = 0
    
    for account in accounts:
        account_number = account['number']
        email = account['email']
        password = account['password']
        
        result = collect_cookies_for_account(account_number, email, password, headless)
        
        if result:
            results.append(result)
            successful += 1
            
            # Save individual account cookies
            output_file = os.path.join(COOKIES_OUTPUT_DIR, f'account_{account_number}_{email.replace("@", "_at_")}.json')
            with open(output_file, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"   💾 Saved to: {output_file}")
        else:
            failed += 1
    
    # Save all results
    all_results_file = os.path.join(COOKIES_OUTPUT_DIR, f'all_accounts_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
    with open(all_results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    # Summary
    print("\n\n" + "=" * 80)
    print("COLLECTION COMPLETE!")
    print("=" * 80)
    print(f"\n📊 Summary:")
    print(f"   ✅ Successful: {successful}")
    print(f"   ❌ Failed: {failed}")
    print(f"   📁 Total accounts: {len(accounts)}")
    
    print(f"\n💾 Results saved to: {COOKIES_OUTPUT_DIR}/")
    print(f"   • Individual files: account_X_email.json")
    print(f"   • Combined file: {all_results_file}")
    
    if successful > 0:
        print(f"\n✅ {successful} access token(s) ready to use!")
        print("\n🎨 Example usage:")
        print("   from whisk_with_aisandbox_scope import test_whisk_api")
        print(f"   token = results[0]['access_token']")
        print(f"   test_whisk_api(token, 'your prompt')")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
