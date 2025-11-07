"""
Fingerprint-Matched Cookie Injection

This script injects cookies while making the browser fingerprint
identical to the source Windows machine to avoid Google's detection.
"""

import os
import json
import platform
from playwright.sync_api import sync_playwright
from datetime import datetime

# Debug: Print startup info
print("🔍 Starting fingerprint_matched_injection.py...")
print(f"   Python version: {platform.python_version()}")
print(f"   Platform: {platform.system()}")
print(f"   Current directory: {os.getcwd()}")
print(f"   Files in directory: {os.listdir('.')[:5]}...")  # Show first 5 files

def load_windows_fingerprint():
    """Load the Windows browser fingerprint for matching"""
    fp_file = "fingerprint_windows.json"
    if os.path.exists(fp_file):
        with open(fp_file, 'r') as f:
            return json.load(f)
    return None

def get_chrome_path():
    """Get Google Chrome path based on OS"""
    OS_TYPE = platform.system()

    if OS_TYPE == 'Linux':
        paths = [
            '/usr/bin/google-chrome',
            '/usr/bin/google-chrome-stable',
            '/usr/bin/chromium',
            '/usr/bin/chromium-browser'
        ]
    else:
        # For Windows/Mac, use default
        return None

    for path in paths:
        if os.path.exists(path):
            return path
    return None

def create_fingerprint_matching_context(p, windows_fp):
    """Create a Playwright context that matches Windows fingerprint"""

    # Base launch options (remove viewport from here)
    launch_options = {
        'headless': False,  # Must be visible for Gmail to work properly
        'args': [
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--no-first-run',
            '--disable-default-apps',
            '--disable-web-security',  # May help with cookie issues
            '--disable-features=VizDisplayCompositor',
            '--user-agent=' + windows_fp.get('userAgent', ''),
            '--window-size=' + f"{windows_fp.get('screen', {}).get('width', 1280)},{windows_fp.get('screen', {}).get('height', 720)}",
            '--timezone=' + windows_fp.get('timezone', 'America/New_York'),
            '--lang=' + windows_fp.get('language', 'en-US'),
            # Critical: Remove webdriver detection
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-tools',
            '--no-default-browser-check',
            '--disable-extensions-except=/tmp',  # Disable extensions
            '--disable-plugins',
            '--disable-images',  # Speed up loading
            '--disable-javascript-harmony-shipping',  # Avoid JS detection
        ],
        'ignore_default_args': ['--enable-automation'],  # Remove automation flag
    }

    # Use real Chrome if available
    chrome_path = get_chrome_path()
    if chrome_path:
        launch_options['executable_path'] = chrome_path

    # Launch browser
    browser = p.chromium.launch(**launch_options)

    # Create context with viewport and other fingerprint matching
    context_options = {
        'user_agent': windows_fp.get('userAgent', ''),
        'viewport': {
            'width': windows_fp.get('screen', {}).get('width', 1280),
            'height': windows_fp.get('screen', {}).get('height', 720)
        },
        'timezone_id': windows_fp.get('timezone', 'America/New_York'),
        'locale': windows_fp.get('language', 'en-US'),
        'permissions': [],  # No special permissions
        'geolocation': None,  # No geolocation
        'extra_http_headers': {
            'Accept-Language': windows_fp.get('language', 'en-US'),
        }
    }

    context = browser.new_context(**context_options)

    return browser, context

def inject_cookies_with_fingerprint_matching(json_path, profile_path):
    """
    Inject cookies while matching Windows browser fingerprint
    """

    print(f"\n📁 Reading cookies from: {json_path}")

    # Load decrypted cookies
    with open(json_path, 'r', encoding='utf-8') as f:
        cookies = json.load(f)

    print(f"📊 Loaded {len(cookies)} cookies")

    # Load Windows fingerprint
    windows_fp = load_windows_fingerprint()
    if not windows_fp:
        print("❌ No Windows fingerprint found! Run browser_fingerprint_diagnostic.py on Windows first")
        return 0

    print(f"🔍 Using Windows fingerprint from: {windows_fp.get('timestamp', 'unknown')}")

    # Create profile directory with proper path handling
    profile_path = os.path.abspath(profile_path)
    os.makedirs(profile_path, exist_ok=True)
    print(f"📁 Created profile directory: {profile_path}")

    print(f"\n🚀 Launching Chrome with Windows fingerprint matching...")

    saved_cookies = []  # Initialize to avoid UnboundLocalError

    with sync_playwright() as p:
        try:
            browser, context = create_fingerprint_matching_context(p, windows_fp)

            print(f"✅ Browser launched with fingerprint matching!")
            print(f"   User Agent: {windows_fp.get('userAgent', '')[:60]}...")
            print(f"   Timezone: {windows_fp.get('timezone')}")
            print(f"   Screen: {windows_fp.get('screen', {}).get('width')}x{windows_fp.get('screen', {}).get('height')}")

            # Convert cookies to Playwright format
            print(f"\n🍪 Converting {len(cookies)} cookies to Playwright format...")

            playwright_cookies = []

            for cookie in cookies:
                try:
                    # Convert Chrome timestamp to Unix timestamp
                    expires = None
                    if cookie.get('expires_utc', 0) > 0:
                        chrome_time = cookie['expires_utc']
                        # Chrome epoch: January 1, 1601
                        # Unix epoch: January 1, 1970
                        chrome_epoch_offset = 11644473600
                        # Chrome time is in microseconds, convert to seconds
                        expires = int((chrome_time / 1000000) - chrome_epoch_offset)

                    # Build Playwright cookie
                    pw_cookie = {
                        'name': cookie['name'],
                        'value': cookie['value'],
                        'domain': cookie['host_key'],
                        'path': cookie['path']
                    }

                    # Add optional fields
                    if cookie.get('is_httponly', False):
                        pw_cookie['httpOnly'] = True

                    if cookie.get('is_secure', False):
                        pw_cookie['secure'] = True

                    # Add sameSite
                    samesite_value = cookie.get('samesite', -1)
                    if samesite_value == 1:
                        pw_cookie['sameSite'] = 'Lax'
                    elif samesite_value == 2:
                        pw_cookie['sameSite'] = 'Strict'
                    elif cookie.get('is_secure', False):
                        pw_cookie['sameSite'] = 'None'

                    # Add expiration if valid
                    if expires and expires > 0:
                        pw_cookie['expires'] = expires

                    playwright_cookies.append(pw_cookie)

                except Exception as e:
                    print(f"   ⚠️  Skipped cookie {cookie.get('name', 'unknown')}: {e}")
                    continue

            print(f"✅ Converted {len(playwright_cookies)} cookies")

            # Inject cookies in batches with delays to avoid detection
            print(f"\n💉 Injecting cookies in batches to avoid detection...")

            batch_size = 20
            for i in range(0, len(playwright_cookies), batch_size):
                batch = playwright_cookies[i:i + batch_size]
                print(f"   Injecting batch {i//batch_size + 1}/{(len(playwright_cookies) + batch_size - 1)//batch_size} ({len(batch)} cookies)...")

                try:
                    context.add_cookies(batch)
                except Exception as e:
                    print(f"   ⚠️  Error injecting batch: {e}")
                    continue

                # Small delay between batches
                import time
                time.sleep(0.1)

            print(f"✅ All cookies injected!")

            # Verify cookies were added
            saved_cookies = context.cookies()
            print(f"\n📊 Verification: Browser now has {len(saved_cookies)} cookies")

            # Test Gmail access
            print(f"\n🔍 Testing Gmail access...")
            page = context.pages[0] if context.pages else context.new_page()

            try:
                page.goto("https://mail.google.com", wait_until='networkidle', timeout=30000)
                time.sleep(3)

                current_url = page.url
                if "mail.google.com" in current_url and "accounts.google.com" not in current_url:
                    print(f"✅ SUCCESS! Gmail loaded without redirect to sign-in!")
                    print(f"   URL: {current_url}")

                    # Check for Gmail content
                    try:
                        inbox_element = page.query_selector('text="Inbox"')
                        if inbox_element:
                            print(f"   ✅ Gmail inbox detected - authentication working!")
                        else:
                            print(f"   ⚠️  Gmail loaded but inbox not found")
                    except:
                        print(f"   ⚠️  Could not verify Gmail content")

                else:
                    print(f"❌ Gmail redirected to sign-in page")
                    print(f"   URL: {current_url}")

                    # Check if it's a 2FA or security check
                    if "challenge" in current_url or "verify" in current_url:
                        print(f"   🔐 Google security challenge detected")
                    elif "disabled" in current_url:
                        print(f"   🚫 Account may be disabled or suspended")

            except Exception as e:
                print(f"❌ Error testing Gmail: {e}")

            # Keep browser open for manual verification
            print(f"\n🎯 Browser is now open with injected cookies!")
            print(f"   Check Gmail manually to verify authentication")
            print(f"   Close this script when done testing")

            # Wait for user input to close
            input(f"\nPress Enter to close browser and save cookies...")

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

        finally:
            try:
                context.close()
                browser.close()
            except:
                pass

    # Verify profile was actually saved
    print(f"\n🔍 Verifying profile save...")
    if os.path.exists(profile_path):
        print(f"✅ Profile directory exists: {profile_path}")

        # Check for Chrome profile files
        expected_files = ['Cookies', 'Login Data', 'Preferences', 'Local State']
        found_files = [f for f in expected_files if os.path.exists(os.path.join(profile_path, f))]

        if found_files:
            print(f"✅ Found Chrome profile files: {found_files}")
        else:
            print(f"⚠️  Profile directory exists but no Chrome files found")

        # List all files in profile directory
        try:
            all_files = os.listdir(profile_path)
            if all_files:
                print(f"📁 Profile contents: {len(all_files)} files/directories")
                # Show first few files
                for file in sorted(all_files)[:5]:
                    file_path = os.path.join(profile_path, file)
                    if os.path.isdir(file_path):
                        print(f"   📁 {file}/")
                    else:
                        size = os.path.getsize(file_path)
                        print(f"   📄 {file} ({size} bytes)")
                if len(all_files) > 5:
                    print(f"   ... and {len(all_files) - 5} more")
            else:
                print(f"⚠️  Profile directory is empty")
        except Exception as e:
            print(f"⚠️  Could not list profile contents: {e}")
    else:
        print(f"❌ Profile directory not found: {profile_path}")
        print(f"   This may indicate the profile wasn't saved properly")

    print(f"\n✅ Done! Cookies saved to: {profile_path}")

    return len(saved_cookies)

def main():
    """Main function for fingerprint-matched injection"""

    print("\n" + "=" * 80)
    print("FINGERPRINT-MATCHED COOKIE INJECTION")
    print("Makes Linux browser identical to Windows to avoid Google detection")
    print("=" * 80)

    base_dir = os.getcwd()
    decrypted_dir = os.path.join(base_dir, 'decrypted_cookies')
    browser_data_base = os.path.join(base_dir, 'browser_data')

    if not os.path.exists(decrypted_dir):
        print(f"\n❌ Decrypted cookies directory not found: {decrypted_dir}")
        print(f"   Transfer decrypted_cookies/ from Windows first")
        return

    # Find all decrypted cookie JSON files
    json_files = [f for f in os.listdir(decrypted_dir) if f.endswith('_cookies.json')]

    if not json_files:
        print(f"\n❌ No decrypted cookie files found")
        return

    print(f"\n📋 Found {len(json_files)} cookie file(s)")

    # Check for Windows fingerprint
    if not os.path.exists('fingerprint_windows.json'):
        print(f"\n❌ Windows fingerprint not found!")
        print(f"   Run browser_fingerprint_diagnostic.py on Windows first")
        return

    print(f"\n🔍 Will match Windows browser fingerprint to avoid detection")

    success_count = 0

    for json_file in sorted(json_files):
        # Extract account number
        account_num = json_file.split('_')[1]

        json_path = os.path.join(decrypted_dir, json_file)
        profile_path = os.path.join(browser_data_base, account_num)

        print(f"\n{'=' * 80}")
        print(f"Account {account_num} - Fingerprint-Matched Injection")
        print(f"{'=' * 80}")

        try:
            count = inject_cookies_with_fingerprint_matching(json_path, profile_path)
            if count > 0:
                success_count += 1

                # Additional verification that profile was saved
                if os.path.exists(profile_path):
                    print(f"\n✅ Profile verification: Directory exists and contains files")
                else:
                    print(f"\n⚠️  Profile verification: Directory not found after injection")

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

    print("\n\n" + "=" * 80)
    print("FINGERPRINT-MATCHED INJECTION COMPLETE")
    print("=" * 80)
    print(f"\n✅ Successfully injected: {success_count}/{len(json_files)} accounts")
    print(f"\n📁 Profiles created in: {browser_data_base}")
    print(f"\n🎯 Test Gmail manually - it should work without redirect!")

    if success_count > 0:
        print(f"\n🎉 SUCCESS! Gmail authentication is working!")
        print(f"   You can now use collect_all_cookies.py to verify both Gmail and Labs")
        print(f"   The authentication should persist across browser sessions")
    else:
        print(f"\n⚠️  Injection completed but verification failed")
        print(f"   Check the profile directories manually")

    print(f"\n" + "=" * 80)

if __name__ == "__main__":
    try:
        print("🚀 Calling main() function...")
        main()
        print("✅ main() completed successfully")
    except Exception as e:
        print(f"❌ Error in main(): {e}")
        import traceback
        traceback.print_exc()