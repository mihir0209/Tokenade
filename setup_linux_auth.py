"""
One-Time Linux Authentication Setup

This script helps establish fresh Gmail authentication on Linux
while preserving existing Google Labs tokens.
"""

import os
import json
import time
from playwright.sync_api import sync_playwright
from datetime import datetime

def get_chrome_path():
    """Get Google Chrome path based on OS"""
    OS_TYPE = os.name  # 'posix' for Linux/Mac, 'nt' for Windows

    if OS_TYPE == 'posix':  # Linux/Mac
        paths = [
            '/usr/bin/google-chrome',
            '/usr/bin/google-chrome-stable',
            '/usr/bin/chromium',
            '/usr/bin/chromium-browser'
        ]
    else:  # Windows
        paths = [
            r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'
        ]

    for path in paths:
        if os.path.exists(path):
            return path
    return None

def setup_linux_authentication(account_number: int = 1):
    """
    Set up fresh Gmail authentication on Linux
    """

    print("\n" + "=" * 80)
    print("ONE-TIME LINUX GMAIL AUTHENTICATION SETUP")
    print("=" * 80)

    base_dir = os.getcwd()
    browser_data_base = os.path.join(base_dir, 'browser_data')
    profile_path = os.path.join(browser_data_base, str(account_number))

    # Create profile directory
    os.makedirs(profile_path, exist_ok=True)

    print(f"\n🎯 Setting up Account {account_number}")
    print(f"📁 Profile: {profile_path}")

    # Check if we have existing Labs tokens to preserve
    tokens_file = os.path.join(base_dir, 'tokens', f'account_{account_number}.json')
    has_existing_tokens = os.path.exists(tokens_file)

    if has_existing_tokens:
        print(f"✅ Found existing Google Labs tokens - will preserve them")
        with open(tokens_file, 'r') as f:
            existing_tokens = json.load(f)
        print(f"   Email: {existing_tokens.get('email', 'Unknown')}")
    else:
        print(f"⚠️  No existing tokens found - will create fresh authentication")

    print(f"\n🚀 Launching Chrome for manual Gmail login...")
    print(f"   You will need to manually sign in to Gmail")
    print(f"   The browser will stay open until you complete authentication")

    with sync_playwright() as p:
        try:
            # Launch with minimal automation detection
            launch_options = {
                'headless': False,
                'user_data_dir': profile_path,
                'args': [
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--no-first-run',
                    '--disable-default-apps',
                    '--disable-web-security',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-tools',
                    '--no-default-browser-check',
                    '--window-size=1280,720'
                ],
                'ignore_default_args': ['--enable-automation']
            }

            # Use real Chrome if available
            chrome_path = get_chrome_path()
            if chrome_path:
                launch_options['executable_path'] = chrome_path
                print(f"   Using Chrome: {chrome_path}")

            browser = p.chromium.launch(**launch_options)
            context = browser.new_context(
                viewport={'width': 1280, 'height': 720},
                timezone_id='Asia/Calcutta',
                locale='en-US'
            )

            page = context.new_page()

            print(f"\n🔐 MANUAL LOGIN REQUIRED")
            print(f"=" * 50)
            print(f"1. 📧 Go to Gmail: https://mail.google.com")
            print(f"2. 🔑 Sign in with your Google account")
            print(f"3. ✅ Complete any 2FA if prompted")
            print(f"4. 📬 Verify you can see your inbox")
            print(f"5. 🔄 Then return here and press Enter")
            print(f"=" * 50)

            # Navigate to Gmail
            page.goto("https://mail.google.com", wait_until='networkidle', timeout=30000)

            # Wait for user to complete login
            input(f"\nPress Enter when you have successfully logged into Gmail...")

            # Verify login worked
            print(f"\n🔍 Verifying Gmail authentication...")

            # Check current URL
            current_url = page.url
            if "mail.google.com" in current_url and "accounts.google.com" not in current_url:
                print(f"✅ Gmail login successful!")
                print(f"   URL: {current_url}")

                # Try to detect inbox
                try:
                    # Look for common Gmail elements
                    inbox_selectors = [
                        'text="Inbox"',
                        '[aria-label="Inbox"]',
                        '.aAy[aria-label="Inbox"]',
                        'div[role="navigation"] a[href*="inbox"]'
                    ]

                    inbox_found = False
                    for selector in inbox_selectors:
                        try:
                            element = page.query_selector(selector)
                            if element:
                                print(f"   ✅ Gmail inbox detected")
                                inbox_found = True
                                break
                        except:
                            continue

                    if not inbox_found:
                        print(f"   ⚠️  Gmail loaded but inbox detection uncertain")

                except Exception as e:
                    print(f"   ⚠️  Could not verify inbox: {e}")

            else:
                print(f"❌ Gmail login failed or incomplete")
                print(f"   Current URL: {current_url}")
                if "accounts.google.com" in current_url:
                    print(f"   Still on sign-in page")

            # Now activate Google Labs if we have existing tokens
            if has_existing_tokens:
                print(f"\n🔬 Activating Google Labs session...")

                # Navigate to Labs
                page.goto("https://labs.google/fx/tools/flow", wait_until='networkidle', timeout=30000)
                time.sleep(3)

                # Check if Labs loaded
                labs_url = page.url
                if "labs.google" in labs_url:
                    print(f"✅ Google Labs loaded successfully")
                    print(f"   URL: {labs_url}")
                else:
                    print(f"⚠️  Google Labs may not have loaded properly")
                    print(f"   URL: {labs_url}")

            # Save the session
            print(f"\n💾 Saving browser session...")
            context.close()
            browser.close()

            print(f"✅ Session saved to: {profile_path}")

            # Test the saved session
            print(f"\n🧪 Testing saved session...")
            test_session(account_number)

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

def test_session(account_number: int):
    """
    Test that the saved session works
    """

    print(f"\n🔍 Testing Account {account_number} session...")

    base_dir = os.getcwd()
    browser_data_base = os.path.join(base_dir, 'browser_data')
    profile_path = os.path.join(browser_data_base, str(account_number))

    with sync_playwright() as p:
        try:
            # Launch with saved session
            launch_options = {
                'headless': True,  # Test in headless mode
                'user_data_dir': profile_path,
                'args': [
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled'
                ],
                'ignore_default_args': ['--enable-automation']
            }

            chrome_path = get_chrome_path()
            if chrome_path:
                launch_options['executable_path'] = chrome_path

            browser = p.chromium.launch(**launch_options)
            context = browser.new_context()
            page = context.new_page()

            # Test Gmail
            print(f"   Testing Gmail...")
            page.goto("https://mail.google.com", wait_until='networkidle', timeout=15000)
            time.sleep(2)

            gmail_url = page.url
            gmail_ok = "mail.google.com" in gmail_url and "accounts.google.com" not in gmail_url

            if gmail_ok:
                print(f"   ✅ Gmail: Working")
            else:
                print(f"   ❌ Gmail: Failed (redirected to sign-in)")

            # Test Google Labs API
            print(f"   Testing Google Labs...")
            response = page.goto("https://labs.google/fx/api/auth/session", wait_until='networkidle', timeout=15000)

            labs_ok = False
            if response.status == 200:
                try:
                    session_data = response.json()
                    if 'access_token' in session_data:
                        email = session_data.get('user', {}).get('email', 'Unknown')
                        print(f"   ✅ Labs: Working (Email: {email})")
                        labs_ok = True
                    else:
                        print(f"   ❌ Labs: No access token")
                except:
                    print(f"   ❌ Labs: Invalid response")
            else:
                print(f"   ❌ Labs: HTTP {response.status}")

            context.close()
            browser.close()

            # Summary
            print(f"\n📊 Session Test Results:")
            if gmail_ok and labs_ok:
                print(f"🎉 SUCCESS! Both Gmail and Labs working!")
            elif gmail_ok:
                print(f"✅ Gmail working, Labs needs attention")
            elif labs_ok:
                print(f"✅ Labs working, Gmail needs attention")
            else:
                print(f"❌ Both Gmail and Labs failed")

        except Exception as e:
            print(f"❌ Test error: {e}")

def main():
    """Main function"""

    print("🔐 ONE-TIME LINUX AUTHENTICATION SETUP")
    print("=" * 80)
    print("This will help you establish fresh Gmail authentication on Linux")
    print("while preserving your existing Google Labs tokens.")

    # Find existing accounts
    base_dir = os.getcwd()
    browser_data_base = os.path.join(base_dir, 'browser_data')

    if not os.path.exists(browser_data_base):
        print(f"\n❌ No browser data found!")
        print(f"   Run fingerprint_matched_injection.py first")
        return

    account_dirs = [d for d in os.listdir(browser_data_base) if d.isdigit()]
    account_numbers = sorted([int(d) for d in account_dirs])

    if not account_numbers:
        print(f"\n❌ No accounts found")
        return

    print(f"\n📋 Found accounts: {account_numbers}")

    # Ask which account to set up
    if len(account_numbers) == 1:
        account_num = account_numbers[0]
    else:
        account_num = int(input(f"\nEnter account number to set up: ").strip())

    if account_num not in account_numbers:
        print(f"❌ Account {account_num} not found")
        return

    # Confirm
    print(f"\n⚠️  This will overwrite the existing profile for Account {account_num}")
    confirm = input(f"Continue? (yes/no): ").strip().lower()

    if confirm != 'yes':
        print(f"Cancelled.")
        return

    # Run setup
    setup_linux_authentication(account_num)

    print(f"\n" + "=" * 80)
    print(f"SETUP COMPLETE")
    print(f"=" * 80)
    print(f"\n🎯 Your Gmail authentication should now work on Linux!")
    print(f"   Run collect_all_cookies.py to verify both Gmail and Labs")

if __name__ == "__main__":
    main()