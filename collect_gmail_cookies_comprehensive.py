"""
Complete Gmail Cookie Collection and Transfer Solution

This script will:
1. Open Gmail in each Windows Chrome profile
2. Collect Gmail-specific cookies (OSID, COMPASS, etc.)
3. Decrypt ALL cookies including Gmail
4. Prepare for Linux transfer
"""

from playwright.sync_api import sync_playwright
import os
import time
import json

def collect_gmail_cookies_comprehensive():
    """Collect Gmail cookies from Windows Chrome profiles"""

    base_dir = os.getcwd()

    print("=" * 80)
    print("COMPLETE GMAIL COOKIE COLLECTION")
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
            print(f"   🚀 Opening Chrome with profile...")

            context = p.chromium.launch_persistent_context(
                user_data_dir=profile_path,
                headless=False,  # Show browser for Gmail login
                channel="msedge"  # Use Edge on Windows
            )

            page = context.pages[0] if context.pages else context.new_page()

            print(f"   ✅ Chrome opened")

            # Step 1: Check current Gmail cookies
            initial_cookies = context.cookies()
            initial_gmail = [c for c in initial_cookies if 'mail.google' in c['domain']]
            print(f"   📊 Initial Gmail cookies: {len(initial_gmail)}")

            # Step 2: Navigate to Gmail
            print(f"   🌐 Navigating to mail.google.com...")

            try:
                page.goto('https://mail.google.com', wait_until='networkidle', timeout=30000)
                print(f"   ✅ Gmail page loaded")

                # Wait for Gmail to fully initialize
                print(f"   ⏳ Waiting for Gmail to load completely...")
                time.sleep(8)

                # Check if Gmail is logged in
                if "Sign in" in page.title or "Gmail" not in page.title:
                    print(f"   ⚠️  Gmail might not be logged in")
                    print(f"   📝 Please login manually in the browser window")
                    input("   Press Enter when Gmail is loaded and logged in...")

                # Step 3: Navigate to different Gmail sections to trigger cookie creation
                print(f"   🔄 Navigating to Gmail sections to create cookies...")

                # Inbox
                page.goto('https://mail.google.com/mail/u/0/#inbox', wait_until='networkidle')
                time.sleep(2)

                # Settings (triggers more cookies)
                page.goto('https://mail.google.com/mail/u/0/#settings/general', wait_until='networkidle')
                time.sleep(2)

                # Back to inbox
                page.goto('https://mail.google.com/mail/u/0/#inbox', wait_until='networkidle')
                time.sleep(2)

                # Step 4: Check final Gmail cookies
                final_cookies = context.cookies()
                final_gmail = [c for c in final_cookies if 'mail.google' in c['domain']]

                print(f"   📊 Final Gmail cookies: {len(final_gmail)}")

                if final_gmail:
                    print(f"   ✅ Gmail cookies collected:")
                    for cookie in final_gmail:
                        print(f"      {cookie['name']}")
                else:
                    print(f"   ❌ Still no Gmail cookies - login might have failed")

            except Exception as e:
                print(f"   ❌ Error: {e}")

            print(f"   💾 Closing Chrome (cookies saved)...")
            context.close()

        print(f"   ✅ Profile {account_num} processed!")

    print("\n" + "=" * 80)
    print("NEXT STEPS - DECRYPT AND TRANSFER")
    print("=" * 80)

    print("""
1. Decrypt all cookies (including new Gmail ones):
   python decrypt_cookies_windows.py

2. Copy decrypted_cookies/ to Linux VPS:
   scp -r decrypted_cookies/ user@vps:/path/to/Tokenade/

3. On Linux VPS, inject cookies:
   python3 inject_cookies_via_playwright.py

4. Test Gmail login:
   python3 collect_all_cookies.py

5. Verify Gmail is logged in by checking:
   - Gmail shows inbox (not login page)
   - collect_all_cookies.py shows "Gmail logged in"
""")

if __name__ == "__main__":
    collect_gmail_cookies_comprehensive()
