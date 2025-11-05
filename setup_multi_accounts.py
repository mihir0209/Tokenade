"""
Multi-Account Setup - Initial Login for All Accounts

This script helps you log in to multiple Google accounts (up to 26) one by one.
Each account's session will be saved separately in browser_data/1, browser_data/2, etc.

Run this ONCE to set up all your accounts.
After setup, use the headless version to collect cookies automatically.
"""

from playwright.sync_api import sync_playwright
import json
import time
import os

# Configuration
ACCOUNTS_FILE = "accounts.json"  # Store account info
BROWSER_DATA_BASE = "browser_data"

# URLs
GOOGLE_LABS_URL = "https://labs.google/fx/tools/flow"


def load_accounts():
    """Load accounts from JSON file"""
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, 'r') as f:
            return json.load(f)
    return []


def save_accounts(accounts):
    """Save accounts to JSON file"""
    with open(ACCOUNTS_FILE, 'w') as f:
        json.dump(accounts, f, indent=2)


def setup_account(account_number, email, password):
    """
    Set up a single account with manual login
    
    Args:
        account_number: The account number (1, 2, 3, etc.)
        email: Google account email
        password: Google account password
    
    Returns:
        bool: True if successful
    """
    
    user_data_dir = os.path.join(BROWSER_DATA_BASE, str(account_number))
    os.makedirs(user_data_dir, exist_ok=True)
    
    print("\n" + "=" * 80)
    print(f"ACCOUNT #{account_number} SETUP")
    print("=" * 80)
    print(f"📧 Email: {email}")
    print(f"📁 Session will be saved to: {user_data_dir}")
    print("=" * 80)
    
    with sync_playwright() as p:
        # Launch browser with persistent context (visible)
        print("\n🚀 Launching browser (VISIBLE - you can see it)...")
        
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,  # Visible browser
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled'],
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        try:
            # Navigate to Google Labs
            print("\n📋 Step 1: Navigating to Google Labs Flow...")
            page.goto(GOOGLE_LABS_URL, wait_until='networkidle', timeout=30000)
            time.sleep(2)
            
            # Check if already logged in
            print("\n📋 Step 2: Checking if already logged in...")
            try:
                response = page.goto('https://labs.google/fx/api/auth/session', wait_until='networkidle', timeout=10000)
                
                if response.status == 200:
                    session_data = response.json()
                    
                    if 'access_token' in session_data:
                        print("   ✅ Already logged in!")
                        print(f"   User: {session_data.get('user', {}).get('email', 'Unknown')}")
                        context.close()
                        return True
            except:
                pass
            
            # Go back to Flow page
            page.goto(GOOGLE_LABS_URL, wait_until='networkidle', timeout=30000)
            time.sleep(2)
            
            # Click Sign in with Google
            print("\n📋 Step 3: Looking for 'Sign in with Google' button...")
            try:
                sign_in_button = page.wait_for_selector('text="Sign in with Google"', timeout=10000)
                
                if sign_in_button:
                    print("   ✓ Found button, clicking...")
                    sign_in_button.click()
                    time.sleep(3)
            except Exception as e:
                print(f"   ⚠ Could not find sign-in button: {e}")
            
            # Fill in email
            print("\n📋 Step 4: Entering email...")
            email_input = page.wait_for_selector('input[type="email"]', timeout=15000)
            email_input.fill(email)
            print(f"   ✓ Email entered: {email}")
            
            next_button = page.wait_for_selector('button:has-text("Next")', timeout=5000)
            next_button.click()
            time.sleep(3)
            
            # Fill in password
            print("\n📋 Step 5: Entering password...")
            password_input = page.wait_for_selector('input[type="password"]', timeout=15000)
            password_input.fill(password)
            print("   ✓ Password entered")
            
            next_button = page.wait_for_selector('button:has-text("Next")', timeout=5000)
            next_button.click()
            time.sleep(5)
            
            # Check for 2FA
            print("\n📋 Step 6: Checking for 2FA or recovery prompts...")
            print("   ⏳ If you see any prompts (2FA, recovery, etc.), please complete them.")
            print("   ⏳ Waiting 30 seconds for you to complete any prompts...")
            time.sleep(30)
            
            # Wait for successful login
            print("\n📋 Step 7: Verifying login...")
            time.sleep(5)
            
            # Verify session
            try:
                response = page.goto('https://labs.google/fx/api/auth/session', wait_until='networkidle', timeout=15000)
                
                if response.status == 200:
                    session_data = response.json()
                    
                    if 'access_token' in session_data:
                        print("   ✅ LOGIN SUCCESSFUL!")
                        print(f"   User: {session_data.get('user', {}).get('email', 'Unknown')}")
                        print(f"   Token: {session_data['access_token'][:60]}...")
                        
                        # Save account info
                        return True
                    else:
                        print("   ⚠ Session found but no access token")
                        return False
                else:
                    print(f"   ⚠ Session check returned status: {response.status}")
                    return False
                    
            except Exception as e:
                print(f"   ⚠ Could not verify session: {e}")
                return False
            
        except Exception as e:
            print(f"\n❌ Error during setup: {e}")
            import traceback
            traceback.print_exc()
            return False
            
        finally:
            print(f"\n💾 Saving session for account #{account_number}...")
            context.close()
            print("   ✓ Session saved!")


def main():
    print("\n" + "=" * 80)
    print("MULTI-ACCOUNT SETUP - Initial Login")
    print("=" * 80)
    print("\nThis script will help you set up multiple Google accounts.")
    print("Each account's session will be saved separately.")
    print("\n📝 You can:")
    print("   1. Add accounts one by one")
    print("   2. Each account gets saved to browser_data/1, browser_data/2, etc.")
    print("   3. After setup, use the headless script to collect cookies")
    print("\n" + "=" * 80)
    
    # Load existing accounts
    accounts = load_accounts()
    
    if accounts:
        print(f"\n📋 Found {len(accounts)} existing account(s):")
        for acc in accounts:
            print(f"   #{acc['number']}: {acc['email']}")
    
    # Add new accounts
    while True:
        print("\n" + "=" * 80)
        choice = input("\nAdd new account? (yes/no): ").strip().lower()
        
        if choice not in ['yes', 'y']:
            break
        
        # Get account details
        email = input("\n📧 Enter email: ").strip()
        password = input("🔒 Enter password: ").strip()
        
        if not email or not password:
            print("❌ Email and password required!")
            continue
        
        # Determine account number
        account_number = len(accounts) + 1
        
        # Setup the account
        success = setup_account(account_number, email, password)
        
        if success:
            # Save to accounts list
            accounts.append({
                'number': account_number,
                'email': email,
                'password': password,  # Store encrypted in production!
                'session_dir': f'browser_data/{account_number}'
            })
            save_accounts(accounts)
            
            print(f"\n✅ Account #{account_number} setup complete!")
            print(f"   Email: {email}")
            print(f"   Session saved to: browser_data/{account_number}")
        else:
            print(f"\n❌ Account setup failed. Please try again.")
    
    # Summary
    print("\n\n" + "=" * 80)
    print("SETUP COMPLETE!")
    print("=" * 80)
    print(f"\n📊 Total accounts configured: {len(accounts)}")
    
    for acc in accounts:
        print(f"   #{acc['number']}: {acc['email']}")
    
    print(f"\n📁 Sessions saved in: {BROWSER_DATA_BASE}/")
    print("\n🚀 Next steps:")
    print("   1. Run 'python collect_cookies_headless.py' to collect cookies from all accounts")
    print("   2. Sessions are persistent - no need to log in again unless logged out")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
