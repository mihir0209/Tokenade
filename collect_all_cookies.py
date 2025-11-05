"""
Headless Cookie Collector - Automatic Token Extraction

This script runs in headless mode and collects cookies/tokens from all accounts.
It uses the saved browser sessions from setup_accounts.py.

If an account is logged out, it can re-login automatically (if credentials provided).
"""

from playwright.sync_api import sync_playwright
import json
import os
import time
from datetime import datetime

# Base directory for all browser sessions
BASE_DIR = os.path.dirname(__file__)
BROWSER_DATA_BASE = os.path.join(BASE_DIR, 'browser_data')
TOKENS_OUTPUT_DIR = os.path.join(BASE_DIR, 'tokens')

# URLs
GMAIL_URL = "https://mail.google.com"  # For Google Account login
GOOGLE_LABS_URL = "https://labs.google/fx/tools/flow"
SESSION_API_URL = "https://labs.google/fx/api/auth/session"

# Optional: Credentials for auto-relogin (load from file)
CREDENTIALS_FILE = os.path.join(BASE_DIR, 'accounts.json')

# Browser configuration
BROWSER_CONFIGS = {
    'edge': {
        'name': 'Microsoft Edge',
        'path': r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        'channel': 'msedge'
    },
    'brave': {
        'name': 'Brave Browser',
        'path': r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe',
        'channel': None
    },
    'chrome': {
        'name': 'Google Chrome',
        'path': r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        'channel': None
    },
    'chrome_x86': {
        'name': 'Google Chrome (x86)',
        'path': r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
        'channel': None
    }
}

def detect_browser():
    """Detect which browser to use based on what's installed"""
    # Priority order: Chrome (best portability) > Edge > Brave
    
    # Check Chrome first (64-bit)
    if os.path.exists(BROWSER_CONFIGS['chrome']['path']):
        return BROWSER_CONFIGS['chrome']
    # Chrome 32-bit
    elif os.path.exists(BROWSER_CONFIGS['chrome_x86']['path']):
        return BROWSER_CONFIGS['chrome_x86']
    # Edge (common on Windows)
    elif os.path.exists(BROWSER_CONFIGS['edge']['path']):
        return BROWSER_CONFIGS['edge']
    # Brave
    elif os.path.exists(BROWSER_CONFIGS['brave']['path']):
        return BROWSER_CONFIGS['brave']
    else:
        # If neither Edge nor Brave found, show error
        # We should NOT fall back to Playwright Chromium!
        print("\n⚠️  WARNING: Neither Edge nor Brave found!")
        print("   If you set up accounts with a real browser, use the same browser.")
        print("   Falling back to Chromium may cause issues.")
        return {
            'name': 'Playwright Chromium (Fallback)',
            'path': None,
            'channel': None
        }

def load_credentials():
    """Load account credentials from file (optional)"""
    if os.path.exists(CREDENTIALS_FILE):
        with open(CREDENTIALS_FILE, 'r') as f:
            return json.load(f)
    return {}

def collect_token_from_account(account_number: int, credentials: dict = None, headless: bool = True):
    """
    Collect token from one account
    
    Args:
        account_number: Account number (1-26)
        credentials: Optional dict with email/password for re-login
        headless: Run in headless mode
        
    Returns:
        dict: Token data or None
    """
    
    user_data_dir = os.path.join(BROWSER_DATA_BASE, str(account_number))
    
    if not os.path.exists(user_data_dir):
        print(f"❌ Account {account_number}: No session found. Run setup_accounts.py first.")
        return None
    
    print(f"\n📋 Account {account_number}: Collecting token...")
    
    # Detect browser (same one used during setup)
    browser_config = detect_browser()
    if account_number == 1 or credentials:  # Show browser info on first account
        print(f"   🌐 Using: {browser_config['name']}")
    
    with sync_playwright() as p:
        try:
            # Launch with saved session
            launch_options = {
                'user_data_dir': user_data_dir,
                'headless': headless,
                'args': [
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--window-size=1920,1080'
                ],
                'viewport': {'width': 1920, 'height': 1080},
                'ignore_default_args': ['--enable-automation']
            }
            
            # Add executable path if using real browser
            if browser_config['path']:
                launch_options['executable_path'] = browser_config['path']
                if browser_config['channel']:
                    launch_options['channel'] = browser_config['channel']
            
            context = p.chromium.launch_persistent_context(**launch_options)
            
            page = context.pages[0] if context.pages else context.new_page()
            
            # NOTE: No JavaScript injection needed for real browsers (Edge/Brave)!
            # They already have real fingerprints
            
            # Try to get session - first check if Gmail is logged in
            print(f"   🔍 Checking Gmail login status...")
            try:
                page.goto(GMAIL_URL, wait_until='networkidle', timeout=15000)
                time.sleep(2)
                
                current_url = page.url
                if "mail.google.com" in current_url and "accounts.google.com" not in current_url:
                    print(f"   ✅ Gmail is logged in")
                else:
                    print(f"   ⚠ Gmail may not be logged in")
            except:
                print(f"   ⚠ Could not verify Gmail login")
            
            # Now try to get Google Labs session
            print(f"   🔍 Checking Google Labs session...")
            response = page.goto(SESSION_API_URL, wait_until='networkidle', timeout=15000)
            
            if response.status == 200:
                session_data = response.json()
                
                if 'access_token' in session_data:
                    email = session_data.get('user', {}).get('email', 'Unknown')
                    token = session_data['access_token']
                    
                    print(f"   ✅ Token collected!")
                    print(f"   📧 Email: {email}")
                    print(f"   🔑 Token: {token[:60]}...")
                    
                    # Prepare token data (WITHOUT cookies - we don't use them)
                    token_data = {
                        'account_number': account_number,
                        'email': email,
                        'access_token': token,
                        'expires': session_data.get('expires'),
                        'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'status': 'active'
                    }
                    
                    # NOTE: Cookies NOT included - we only need the access_token
                    # This keeps the JSON files small and efficient
                    
                    context.close()
                    return token_data
                else:
                    print(f"   ⚠ No access token in session")
            else:
                print(f"   ⚠ Session API returned status: {response.status}")
            
            # Not logged in - try to re-login if credentials provided
            if credentials and str(account_number) in credentials:
                print(f"   🔄 Attempting auto re-login...")
                
                creds = credentials[str(account_number)]
                email = creds.get('email')
                password = creds.get('password')
                
                if email and password:
                    # Navigate to Gmail for login
                    page.goto(GMAIL_URL, wait_until='networkidle', timeout=30000)
                    time.sleep(3)
                    
                    # Check if login page appears
                    try:
                        # Enter email
                        email_input = page.wait_for_selector('input[type="email"]', timeout=10000)
                        email_input.fill(email)
                        next_button = page.wait_for_selector('button:has-text("Next"), input[type="submit"]', timeout=5000)
                        next_button.click()
                        time.sleep(3)
                        
                        # Enter password
                        password_input = page.wait_for_selector('input[type="password"]', timeout=15000)
                        password_input.fill(password)
                        next_button = page.wait_for_selector('button:has-text("Next"), input[type="submit"]', timeout=5000)
                        next_button.click()
                        time.sleep(5)
                        
                        # Check for 2FA
                        try:
                            twofa = page.wait_for_selector('input[type="tel"], input[aria-label*="code"]', timeout=5000)
                            if twofa:
                                print(f"   ⚠ 2FA required - cannot auto-login")
                                context.close()
                                return None
                        except:
                            pass
                        
                        # Wait for Gmail to load
                        time.sleep(5)
                        page.goto(GMAIL_URL, wait_until='networkidle', timeout=15000)
                        time.sleep(2)
                        
                        current_url = page.url
                        if "mail.google.com" in current_url and "accounts.google.com" not in current_url:
                            print(f"   ✅ Gmail re-login successful!")
                            
                            # Now activate Google Labs session
                            print(f"   📋 Activating Google Labs session...")
                            page.goto(GOOGLE_LABS_URL, wait_until='networkidle', timeout=30000)
                            time.sleep(3)
                            
                            # Click sign in if needed
                            try:
                                sign_in_button = page.query_selector('text="Sign in with Google"')
                                if sign_in_button:
                                    sign_in_button.click()
                                    time.sleep(5)
                            except:
                                pass
                            
                            # Verify session
                            time.sleep(3)
                            response = page.goto(SESSION_API_URL, wait_until='networkidle', timeout=15000)
                        
                        if response.status == 200:
                            session_data = response.json()
                            
                            if 'access_token' in session_data:
                                print(f"   ✅ Re-login successful!")
                                
                                token_data = {
                                    'account_number': account_number,
                                    'email': session_data.get('user', {}).get('email', email),
                                    'access_token': session_data['access_token'],
                                    'expires': session_data.get('expires'),
                                    'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                    'status': 'relogged'
                                }
                                
                                # NOTE: Cookies NOT included - we only need the access_token
                                
                                context.close()
                                return token_data
                        
                    except Exception as e:
                        print(f"   ❌ Re-login failed: {e}")
            
            context.close()
            return None
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return None


def main():
    print("\n" + "=" * 80)
    print("HEADLESS COOKIE COLLECTOR - Automatic Token Extraction")
    print("=" * 80)
    
    # Create tokens directory
    os.makedirs(TOKENS_OUTPUT_DIR, exist_ok=True)
    
    # Load credentials (optional)
    credentials = load_credentials()
    if credentials:
        print(f"\n✓ Loaded credentials for {len(credentials)} account(s)")
    else:
        print(f"\n⚠ No credentials file found. Re-login will not be possible.")
        print(f"  Create {CREDENTIALS_FILE} to enable auto re-login.")
    
    # Find all account sessions
    if not os.path.exists(BROWSER_DATA_BASE):
        print(f"\n❌ No browser data found!")
        print(f"   Run setup_accounts.py first to set up accounts.")
        return
    
    account_dirs = [d for d in os.listdir(BROWSER_DATA_BASE) if d.isdigit()]
    account_numbers = sorted([int(d) for d in account_dirs])
    
    if not account_numbers:
        print(f"\n❌ No accounts found in {BROWSER_DATA_BASE}")
        print(f"   Run setup_accounts.py first.")
        return
    
    print(f"\n📋 Found {len(account_numbers)} account(s): {account_numbers}")
    
    # Ask which mode
    print(f"\n🎯 Collection mode:")
    print(f"   1. All accounts")
    print(f"   2. Specific accounts")
    print(f"   3. Single account")
    
    mode = input(f"\nSelect mode (1/2/3): ").strip()
    
    accounts_to_collect = []
    
    if mode == "1":
        accounts_to_collect = account_numbers
    elif mode == "2":
        nums = input(f"\nEnter account numbers (comma-separated): ").strip()
        accounts_to_collect = [int(x.strip()) for x in nums.split(',') if x.strip().isdigit()]
    elif mode == "3":
        num = int(input(f"\nEnter account number: ").strip())
        accounts_to_collect = [num]
    else:
        accounts_to_collect = account_numbers
    
    print(f"\n📋 Will collect from accounts: {accounts_to_collect}")
    
    # Ask about headless
    headless_input = input(f"\nRun in headless mode? (yes/no, default=yes): ").strip().lower()
    headless = headless_input != 'no'
    
    print(f"\n🚀 Starting collection... (headless={headless})")
    time.sleep(1)
    
    # Collect from each account
    all_tokens = []
    success_count = 0
    
    for account_num in accounts_to_collect:
        token_data = collect_token_from_account(account_num, credentials, headless)
        
        if token_data:
            all_tokens.append(token_data)
            success_count += 1
            
            # Save individual token file
            token_file = os.path.join(TOKENS_OUTPUT_DIR, f'account_{account_num}.json')
            with open(token_file, 'w') as f:
                json.dump(token_data, f, indent=2)
            print(f"   💾 Saved to: {token_file}")
        
        # Small delay between accounts
        if account_num != accounts_to_collect[-1]:
            time.sleep(1)
    
    # Save all tokens
    all_tokens_file = os.path.join(TOKENS_OUTPUT_DIR, 'all_tokens.json')
    with open(all_tokens_file, 'w') as f:
        json.dump(all_tokens, f, indent=2)
    
    # Summary
    print("\n\n" + "=" * 80)
    print("COLLECTION COMPLETE!")
    print("=" * 80)
    print(f"\n✅ Successfully collected: {success_count}/{len(accounts_to_collect)} accounts")
    print(f"\n📁 Tokens saved in: {TOKENS_OUTPUT_DIR}")
    print(f"   • Individual files: account_N.json")
    print(f"   • All tokens: all_tokens.json")
    
    if success_count < len(accounts_to_collect):
        failed = len(accounts_to_collect) - success_count
        print(f"\n⚠ {failed} account(s) failed to collect tokens")
        print(f"   Possible reasons:")
        print(f"   • Account logged out (run setup_accounts.py to re-login)")
        print(f"   • Session expired")
        print(f"   • Network issues")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
