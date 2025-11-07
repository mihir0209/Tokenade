"""
FINAL: Collect Gmail cookies - MUST interact with Gmail
"""

from playwright.sync_api import sync_playwright
import os
import platform

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

def collect_gmail_cookies_final():
    base_dir = os.getcwd()
    profile_path = os.path.join(base_dir, 'browser_data', '1')

    chrome_path = get_chrome_path()
    if not chrome_path:
        print("❌ Chrome not found!")
        return

    print("=" * 80)
    print("FINAL GMAIL COOKIE COLLECTION")
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

        print("✅ Chrome opened with Gmail")

        # Check initial Gmail cookies
        initial_cookies = context.cookies()
        initial_gmail = [c for c in initial_cookies if 'mail.google' in c['domain']]
        print(f"\n📊 Initial Gmail cookies: {len(initial_gmail)}")

        print("\n" + "=" * 60)
        print("🚨 CRITICAL: You MUST actually use Gmail now!")
        print("=" * 60)
        print("1. 🔐 LOGIN to Gmail (if not logged in)")
        print("2. 📧 Go to INBOX")
        print("3. ⚙️ Click SETTINGS gear icon")
        print("4. 📁 Click 'See all settings'")
        print("5. 🔄 Switch between tabs: General, Labels, Inbox, etc.")
        print("6. 📂 Check different folders: Sent, Drafts, Trash")
        print("7. ✉️ Open 2-3 emails")
        print("8. ⏳ Do this for AT LEAST 2 minutes")
        print("=" * 60)
        print("❌ DO NOT just press Enter - actually use Gmail!")

        input("\nPress Enter ONLY after you've spent 2+ minutes using Gmail: ")

        # Check final cookies
        final_cookies = context.cookies()
        final_gmail = [c for c in final_cookies if 'mail.google' in c['domain']]

        print(f"\n📊 Final Gmail cookies: {len(final_gmail)}")

        if final_gmail:
            print("✅ SUCCESS! Gmail cookies created:")
            for cookie in final_gmail:
                print(f"   {cookie['name']}")
        else:
            print("❌ FAILED! No Gmail cookies found.")
            print("   You didn't actually use Gmail!")

        context.close()

    print("\n✅ Done! Now run:")
    print("   python decrypt_cookies_windows.py")
    print("   python check_gmail_cookies_windows.py  # Verify Gmail cookies exist")
    print("   # Then transfer to Linux")

if __name__ == "__main__":
    collect_gmail_cookies_final()