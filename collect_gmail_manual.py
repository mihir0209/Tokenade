"""
Simple Gmail cookie collection - manual approach with explicit browser paths
"""

from playwright.sync_api import sync_playwright
import os
import platform

def get_chrome_path():
    """Get Google Chrome path based on OS"""
    os_type = platform.system()

    if os_type == 'Windows':
        # Try 64-bit first, then 32-bit
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
    elif os_type == 'Darwin':  # Mac
        paths = [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/Applications/Chromium.app/Contents/MacOS/Chromium'
        ]
    else:
        return None

    # Return first existing path
    for path in paths:
        if os.path.exists(path):
            return path

    return None

def collect_gmail_simple():
    """Simple Gmail collection with manual interaction"""

    base_dir = os.getcwd()
    profile_path = os.path.join(base_dir, 'browser_data', '1')

    print("=" * 80)
    print("GMAIL COOKIE COLLECTION - MANUAL")
    print("=" * 80)

    print(f"\n📁 Using profile: {profile_path}")

    # Get Chrome path
    chrome_path = get_chrome_path()
    if not chrome_path:
        print("❌ Google Chrome not found on system!")
        print("   Please install Google Chrome first.")
        return

    print(f"🔍 Using Chrome: {chrome_path}")

    with sync_playwright() as p:
        print(f"\n🚀 Opening Chrome...")

        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            headless=False,
            executable_path=chrome_path  # Use explicit Chrome path
        )

        page = context.pages[0] if context.pages else context.new_page()

        print(f"✅ Chrome opened")

        # Navigate to Gmail
        print(f"\n🌐 Opening Gmail...")
        page.goto('https://mail.google.com')

        print(f"\n📝 MANUAL STEPS:")
        print(f"   1. Login to Gmail if needed")
        print(f"   2. Navigate around Gmail (inbox, settings, etc.)")
        print(f"   3. Close this terminal when done")

        input("\nPress Enter when you've finished using Gmail...")

        # Check cookies
        cookies = context.cookies()
        gmail_cookies = [c for c in cookies if 'mail.google' in c['domain']]

        print(f"\n📊 Gmail cookies collected: {len(gmail_cookies)}")

        if gmail_cookies:
            print(f"✅ Success! Gmail cookies:")
            for cookie in gmail_cookies:
                print(f"   {cookie['name']}")

        context.close()

    print(f"\n✅ Done! Now run: python decrypt_cookies_windows.py")

if __name__ == "__main__":
    collect_gmail_simple()
