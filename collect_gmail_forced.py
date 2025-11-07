"""
FORCED Gmail cookie collection - won't proceed until Gmail cookies exist
"""

from playwright.sync_api import sync_playwright
import os
import platform
import time

def get_chrome_path():
    os_type = platform.system()
    if os_type == 'Windows':
        paths = [
            r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'
        ]
    elif os_type == 'Linux':
        paths = [
            '/usr/bin/google-chrome',
            '/usr/bin/google-chrome-stable',
            '/usr/bin/chromium',
            '/usr/bin/chromium-browser'
        ]
    elif os_type == 'Darwin':
        paths = [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/Applications/Chromium.app/Contents/MacOS/Chromium'
        ]
    else:
        return None

    for path in paths:
        if os.path.exists(path):
            return path
    return None

def wait_for_gmail_cookies(context, required_cookies=3):
    """Wait until Gmail cookies are created"""
    print(f"\n⏳ Waiting for Gmail cookies (need at least {required_cookies})...")

    attempts = 0
    max_attempts = 60  # 5 minutes max

    while attempts < max_attempts:
        cookies = context.cookies()
        gmail_cookies = [c for c in cookies if 'mail.google' in c['domain']]

        if len(gmail_cookies) >= required_cookies:
            print(f"✅ SUCCESS! Found {len(gmail_cookies)} Gmail cookies:")
            for cookie in gmail_cookies:
                print(f"   {cookie['name']}")
            return True

        attempts += 1
        if attempts % 10 == 0:  # Every 10 seconds
            print(f"   Still waiting... {len(gmail_cookies)} Gmail cookies so far (need {required_cookies})")

        time.sleep(5)  # Check every 5 seconds

    print(f"❌ TIMEOUT! Only found {len(gmail_cookies)} Gmail cookies after 5 minutes")
    return False

def collect_gmail_cookies_forced():
    base_dir = os.getcwd()
    profile_path = os.path.join(base_dir, 'browser_data', '1')

    chrome_path = get_chrome_path()
    if not chrome_path:
        print("❌ Chrome not found!")
        return

    print("=" * 80)
    print("FORCED GMAIL COOKIE COLLECTION")
    print("=" * 80)

    print(f"📁 Profile: {profile_path}")
    print(f"🔍 Chrome: {chrome_path}")

    with sync_playwright() as p:
        print("\n🚀 Opening Chrome...")

        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            headless=False,
            executable_path=chrome_path,
            args=[
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--no-first-run',
                '--no-default-browser-check',
                '--window-size=1920,1080'
            ],
            viewport={'width': 1920, 'height': 1080},
            ignore_default_args=['--enable-automation']
        )

        page = context.pages[0] if context.pages else context.new_page()

        print("✅ Chrome opened")

        # Open Gmail
        print("\n🌐 Opening Gmail...")
        page.goto('https://mail.google.com')

        print("\n" + "=" * 60)
        print("🚨 YOU MUST USE GMAIL NOW - SCRIPT WON'T PROCEED UNTIL COOKIES EXIST!")
        print("=" * 60)
        print("1. 🔐 LOGIN to Gmail (if not logged in)")
        print("2. 📧 Go to INBOX")
        print("3. ⚙️ Click SETTINGS gear icon → 'See all settings'")
        print("4. 📁 Switch between tabs: General, Labels, Inbox, Accounts")
        print("5. 📂 Check folders: Sent, Drafts, Trash, Spam")
        print("6. ✉️ Open several emails")
        print("7. ⏳ Keep Gmail active for several minutes")
        print("=" * 60)
        print("⏳ Script will automatically detect when Gmail cookies are created...")

        # Wait for Gmail cookies to be created
        success = wait_for_gmail_cookies(context, required_cookies=3)

        if success:
            print("\n🎉 GMAIL COOKIES SUCCESSFULLY CREATED!")
            print("   Now you can decrypt and transfer them to Linux.")
        else:
            print("\n❌ Failed to create Gmail cookies.")
            print("   You may need to try again.")

        context.close()

    if success:
        print("\n✅ Ready for next steps:")
        print("   python decrypt_cookies_windows.py")
        print("   python check_gmail_cookies_windows.py")
        print("   # Then transfer decrypted_cookies/ to Linux")

if __name__ == "__main__":
    collect_gmail_cookies_forced()