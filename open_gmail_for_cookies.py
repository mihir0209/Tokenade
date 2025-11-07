"""
Open Gmail and wait for user to login and navigate
"""

from playwright.sync_api import sync_playwright
import os
import platform

def get_chrome_path():
    """Get Google Chrome path based on OS"""
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

def open_gmail_for_cookies():
    """Open Gmail and wait for user interaction"""

    base_dir = os.getcwd()
    profile_path = os.path.join(base_dir, 'browser_data', '1')

    chrome_path = get_chrome_path()
    if not chrome_path:
        print("❌ Chrome not found!")
        return

    print("=" * 80)
    print("OPEN GMAIL FOR COOKIE COLLECTION")
    print("=" * 80)

    print(f"📁 Profile: {profile_path}")
    print(f"🔍 Chrome: {chrome_path}")

    with sync_playwright() as p:
        print("\n🚀 Opening Chrome with Gmail...")

        # Use the SAME launch options as setup_accounts.py for "secure" browser
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            headless=False,
            executable_path=chrome_path,  # Use real Chrome!
            args=[
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--no-first-run',
                '--no-default-browser-check',
                '--window-size=1920,1080'
            ],
            viewport={'width': 1920, 'height': 1080},
            ignore_default_args=['--enable-automation']  # Remove automation indicators
        )

        page = context.pages[0] if context.pages else context.new_page()

        print("✅ Chrome opened")

        # Open Gmail
        print("\n🌐 Opening Gmail...")
        page.goto('https://mail.google.com')

        print("\n" + "=" * 50)
        print("IMPORTANT: You MUST do these steps:")
        print("=" * 50)
        print("1. ✅ LOGIN to Gmail if not already logged in")
        print("2. 📧 Navigate to INBOX")
        print("3. ⚙️  Go to SETTINGS (gear icon)")
        print("4. 📁 Check different folders (Sent, Drafts, etc.)")
        print("5. 🔄 Do this for 1-2 minutes to create cookies")
        print("=" * 50)

        input("\nPress Enter ONLY when you've fully used Gmail...")

        # Check cookies
        cookies = context.cookies()
        gmail_cookies = [c for c in cookies if 'mail.google' in c['domain']]

        print(f"\n📊 Gmail cookies collected: {len(gmail_cookies)}")

        if gmail_cookies:
            print("✅ SUCCESS! Gmail cookies found:")
            for cookie in gmail_cookies:
                print(f"   {cookie['name']}")
        else:
            print("❌ NO Gmail cookies found!")
            print("   You probably didn't login or navigate enough.")

        context.close()

    print("\n✅ Done! Now run:")
    print("   python decrypt_cookies_windows.py")
    print("   (Then transfer to Linux)")

if __name__ == "__main__":
    open_gmail_for_cookies()