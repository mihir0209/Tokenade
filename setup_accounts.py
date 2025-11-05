"""
Multi-Account Setup - ONE-TIME Manual Login for All Accounts

This script helps you log in to multiple Google accounts (up to 26) manually.
Each account's session is saved in a separate browser_data folder.

Usage:
1. Run this script
2. Log in to each Google account via Google Sign-In page
3. Session saved automatically
4. Repeat for all accounts

After this one-time setup, use the headless collector to get cookies automatically.
"""

from playwright.sync_api import sync_playwright
import json
import os
import time

# Base directory for all browser sessions
BASE_DIR = os.path.dirname(__file__)
BROWSER_DATA_BASE = os.path.join(BASE_DIR, 'browser_data')

# Target URLs
GOOGLE_SIGNIN_URL = "https://accounts.google.com/ServiceLogin"  # Direct Google Account sign-in
GOOGLE_ACCOUNT_URL = "https://myaccount.google.com"  # Google Account page to verify login
GOOGLE_LABS_URL = "https://labs.google/fx/tools/flow"
SESSION_API_URL = "https://labs.google/fx/api/auth/session"

# Global variable for browser selection
SELECTED_BROWSER = None

def setup_account(account_number: int, total_accounts: int):
    """
    Setup one account - manual login, save session
    
    Args:
        account_number: Account number (1-26)
        total_accounts: Total number of accounts to setup
    """
    
    user_data_dir = os.path.join(BROWSER_DATA_BASE, str(account_number))
    
    print("\n" + "=" * 80)
    print(f"ACCOUNT {account_number}/{total_accounts} - Manual Login Setup")
    print("=" * 80)
    
    # Browser selection
    browser_choices = {
        '1': {
            'name': 'Microsoft Edge',
            'path': r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
            'channel': 'msedge'
        },
        '2': {
            'name': 'Brave Browser',
            'path': r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe',
            'channel': None
        },
        '3': {
            'name': 'Google Chrome',
            'path': r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            'channel': None
        },
        '4': {
            'name': 'Google Chrome (x86)',
            'path': r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
            'channel': None
        }
    }
    
    # Ask user which browser to use (only on first account)
    global SELECTED_BROWSER
    if 'SELECTED_BROWSER' not in globals() or SELECTED_BROWSER is None:
        print("\n🌐 Select browser to use:")
        print("   1. Microsoft Edge")
        print("   2. Brave Browser")
        print("   3. Google Chrome (64-bit) ⭐ Best for portability")
        print("   4. Google Chrome (32-bit)")
        
        browser_choice = input("\nEnter choice (1/2/3/4, default=3): ").strip() or '3'
        SELECTED_BROWSER = browser_choices.get(browser_choice, browser_choices['3'])
        
        print(f"\n✅ Using: {SELECTED_BROWSER['name']}")
        print(f"   Path: {SELECTED_BROWSER['path']}")
        
        # Check if browser exists
        if not os.path.exists(SELECTED_BROWSER['path']):
            print(f"\n❌ ERROR: Browser not found at {SELECTED_BROWSER['path']}")
            print("   Please install the browser or check the path.")
            return False
    
    with sync_playwright() as p:
        # Launch browser with persistent context (VISIBLE for manual login)
        print(f"\n🚀 Opening {SELECTED_BROWSER['name']} for Account {account_number}...")
        print(f"📁 Session will be saved to: {user_data_dir}")
        
        launch_options = {
            'user_data_dir': user_data_dir,
            'headless': False,  # VISIBLE - you'll see the browser
            'executable_path': SELECTED_BROWSER['path'],  # Use real browser!
            'args': [
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--no-first-run',
                '--no-default-browser-check',
                '--window-size=1920,1080'
            ],
            'viewport': {'width': 1920, 'height': 1080},
            'ignore_default_args': ['--enable-automation']
        }
        
        # Add channel for Edge
        if SELECTED_BROWSER['channel']:
            launch_options['channel'] = SELECTED_BROWSER['channel']
        
        context = p.chromium.launch_persistent_context(**launch_options)
        page = context.pages[0] if context.pages else context.new_page()
        
        # NOTE: No JavaScript injection needed for real browsers!
        # Edge/Brave already have real fingerprints
        
        try:
            # STEP 1: Check if already logged in
            print(f"\n📋 Checking if already logged in...")
            
            try:
                page.goto(GOOGLE_ACCOUNT_URL, wait_until='networkidle', timeout=15000)
                time.sleep(2)
                current_url = page.url
                
                # If on myaccount.google.com (not redirected to signin), already logged in
                if "myaccount.google.com" in current_url and "signin" not in current_url.lower():
                    print(f"   ✅ Google Account is already logged in!")
                    
                    # Now check Google Labs session
                    print(f"\n📋 Checking Google Labs session...")
                    response = page.goto(SESSION_API_URL, wait_until='networkidle', timeout=15000)
                    
                    if response.status == 200:
                        session_data = response.json()
                        
                        if 'access_token' in session_data:
                            email = session_data.get('user', {}).get('email', 'Unknown')
                            print(f"   ✅ Account {account_number} is FULLY LOGGED IN!")
                            print(f"   📧 Email: {email}")
                            
                            # Save token info
                            token_file = os.path.join(user_data_dir, 'token_info.json')
                            with open(token_file, 'w') as f:
                                json.dump({
                                    'account_number': account_number,
                                    'email': email,
                                    'access_token': session_data['access_token'],
                                    'expires': session_data.get('expires'),
                                    'saved_at': time.strftime('%Y-%m-%d %H:%M:%S')
                                }, f, indent=2)
                            
                            print(f"   ✓ Session saved!")
                            context.close()
                            return True
            except:
                pass
            
            # STEP 2: Not logged in - navigate to Google Sign-In
            print(f"\n🔐 Navigating to Google Sign-In page...")
            page.goto(GOOGLE_SIGNIN_URL, wait_until='networkidle', timeout=30000)
            time.sleep(3)
            
            print(f"\n" + "=" * 80)
            print(f"⚠  MANUAL GOOGLE ACCOUNT LOGIN REQUIRED FOR ACCOUNT {account_number}")
            print("=" * 80)
            print(f"\n📝 Instructions:")
            print(f"   1. You should see 'Sign in' page with email field")
            print(f"   2. Enter your Google Account {account_number} email")
            print(f"   3. Click 'Next'")
            print(f"   4. Enter your password")
            print(f"   5. Click 'Next'")
            print(f"   6. Complete any 2FA/security check (if required)")
            print(f"   7. Wait until you see Google Account dashboard or search page")
            print(f"\n⏳ Take your time... I'll wait for you to complete login.")
            print(f"   Press ENTER in this terminal AFTER you've successfully logged in...")
            
            input(f"\n[Account {account_number}] Press ENTER after Google Account login is complete: ")
            
            # STEP 3: Verify Google Account login
            print(f"\n📋 Verifying Google Account login...")
            time.sleep(2)
            
            # Go to Google Account page to confirm
            page.goto(GOOGLE_ACCOUNT_URL, wait_until='networkidle', timeout=15000)
            time.sleep(2)
            
            current_url = page.url
            if "myaccount.google.com" in current_url and "signin" not in current_url.lower():
                print(f"   ✅ Google Account login confirmed!")
            else:
                print(f"   ⚠ Login status unclear. Current URL: {current_url}")
            
            # STEP 4: Navigate to Google Labs to activate session
            print(f"\n📋 Activating Google Labs session...")
            print(f"   (This will use your logged-in Google account automatically)")
            
            page.goto(GOOGLE_LABS_URL, wait_until='networkidle', timeout=30000)
            time.sleep(3)
            
            # Check if Google Labs needs explicit sign-in
            try:
                # Look for "Sign in with Google" button
                sign_in_button = page.query_selector('text="Sign in with Google"')
                
                if sign_in_button:
                    print(f"   📋 Google Labs requires sign-in. Clicking 'Sign in with Google'...")
                    sign_in_button.click()
                    time.sleep(5)
                    
                    # It should automatically use the logged-in Google account
                    # Check if account picker appears
                    try:
                        # Wait a bit for redirect or account picker
                        time.sleep(3)
                        print(f"   ⏳ Waiting for Google Labs to authenticate...")
                        time.sleep(5)
                    except:
                        pass
            except:
                print(f"   ✅ No sign-in required (already authenticated)")
            
            # STEP 5: Verify Google Labs session
            print(f"\n📋 Verifying Google Labs session...")
            time.sleep(2)
            
            try:
                response = page.goto(SESSION_API_URL, wait_until='networkidle', timeout=15000)
                
                if response.status == 200:
                    session_data = response.json()
                    
                    if 'access_token' in session_data:
                        email = session_data.get('user', {}).get('email', 'Unknown')
                        print(f"   ✅ SUCCESS! Account {account_number} logged in!")
                        print(f"   Email: {email}")
                        
                        # Save token info
                        token_file = os.path.join(user_data_dir, 'token_info.json')
                        with open(token_file, 'w') as f:
                            json.dump({
                                'account_number': account_number,
                                'email': email,
                                'access_token': session_data['access_token'],
                                'expires': session_data.get('expires'),
                                'saved_at': time.strftime('%Y-%m-%d %H:%M:%S')
                            }, f, indent=2)
                        
                        print(f"   ✓ Session saved to: {user_data_dir}")
                        context.close()
                        return True
                    else:
                        print(f"   ❌ No access token found. Login might have failed.")
                        context.close()
                        return False
                else:
                    print(f"   ❌ Session API returned status: {response.status}")
                    context.close()
                    return False
                    
            except Exception as e:
                print(f"   ❌ Error verifying login: {e}")
                context.close()
                return False
                
        except Exception as e:
            print(f"\n❌ Error during setup: {e}")
            import traceback
            traceback.print_exc()
            context.close()
            return False


def main():
    print("\n" + "=" * 80)
    print("MULTI-ACCOUNT SETUP - One-Time Manual Login")
    print("=" * 80)
    
    print("\n📝 This script helps you set up multiple Google accounts.")
    print("   Each account will be logged in manually (by you) ONE TIME.")
    print("   The session is saved and can be reused later automatically.")
    
    # Get number of accounts
    while True:
        try:
            num_accounts = input("\n🔢 How many accounts do you want to set up? (1-26): ").strip()
            num_accounts = int(num_accounts)
            if 1 <= num_accounts <= 26:
                break
            else:
                print("   ❌ Please enter a number between 1 and 26")
        except ValueError:
            print("   ❌ Please enter a valid number")
    
    print(f"\n✅ Setting up {num_accounts} account(s)")
    
    # Ask which accounts to setup
    print(f"\n📋 Which accounts do you want to set up?")
    print(f"   Options:")
    print(f"   1. All accounts (1 to {num_accounts})")
    print(f"   2. Specific account numbers")
    print(f"   3. Start from a specific number")
    
    choice = input(f"\nEnter choice (1/2/3): ").strip()
    
    accounts_to_setup = []
    
    if choice == "1":
        accounts_to_setup = list(range(1, num_accounts + 1))
    elif choice == "2":
        account_nums = input(f"\nEnter account numbers separated by commas (e.g., 1,3,5): ").strip()
        accounts_to_setup = [int(x.strip()) for x in account_nums.split(',') if x.strip().isdigit()]
    elif choice == "3":
        start_num = int(input(f"\nStart from account number: ").strip())
        accounts_to_setup = list(range(start_num, num_accounts + 1))
    else:
        print("Invalid choice. Setting up all accounts.")
        accounts_to_setup = list(range(1, num_accounts + 1))
    
    print(f"\n📋 Will set up accounts: {accounts_to_setup}")
    input("\nPress ENTER to start...")
    
    # Setup each account
    success_count = 0
    failed_accounts = []
    
    for account_num in accounts_to_setup:
        success = setup_account(account_num, num_accounts)
        
        if success:
            success_count += 1
            print(f"\n✅ Account {account_num} setup complete!")
        else:
            failed_accounts.append(account_num)
            print(f"\n❌ Account {account_num} setup failed!")
        
        # Pause between accounts (except for the last one)
        if account_num != accounts_to_setup[-1]:
            print(f"\n⏸  Moving to next account in 3 seconds...")
            time.sleep(3)
    
    # Summary
    print("\n\n" + "=" * 80)
    print("SETUP COMPLETE!")
    print("=" * 80)
    print(f"\n✅ Successfully set up: {success_count}/{len(accounts_to_setup)} accounts")
    
    if failed_accounts:
        print(f"❌ Failed accounts: {failed_accounts}")
        print(f"   You can run this script again to retry these accounts.")
    
    print(f"\n📁 All sessions saved in: {BROWSER_DATA_BASE}")
    print(f"\n🚀 Next step: Use the headless collector to get cookies automatically!")
    print(f"   Run: python collect_all_cookies.py")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
