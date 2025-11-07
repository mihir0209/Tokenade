"""
Test Script: Cross-platform browser_data portability

This script tests if browser profiles saved in browser_data/ can be used:
1. On different browsers (Edge → Chrome)
2. On different OS platforms (Windows → Linux → Mac)

This is critical for VPS deployment!
"""

from playwright.sync_api import sync_playwright
import os
import time
import shutil
import platform

# Detect OS
OS_TYPE = platform.system()  # 'Windows', 'Linux', 'Darwin' (Mac)

# Paths
BASE_DIR = os.path.dirname(__file__)
ORIGINAL_BROWSER_DATA = os.path.join(BASE_DIR, 'browser_data', '1')  # Account 1
TEST_DIR = os.path.join(BASE_DIR, 'test_portability')
COPIED_BROWSER_DATA = os.path.join(TEST_DIR, 'browser_data_copy')

def get_chrome_path():
    """Get Google Chrome path based on OS"""
    if OS_TYPE == 'Windows':
        paths = [
            r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'
        ]
    elif OS_TYPE == 'Linux':
        paths = [
            '/usr/bin/google-chrome',
            '/usr/bin/google-chrome-stable'
        ]
    elif OS_TYPE == 'Darwin':  # Mac
        paths = [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        ]
    else:
        return None
    
    for path in paths:
        if os.path.exists(path):
            return path
    return None

def test_portability():
    print("\n" + "=" * 80)
    print("CROSS-PLATFORM BROWSER DATA PORTABILITY TEST")
    print("=" * 80)
    
    print(f"\n�️  Current OS: {OS_TYPE}")
    
    print("\n�📋 This test verifies if browser sessions are portable:")
    print("   1. Copy browser_data/1 to test location")
    print("   2. Use Google Chrome on current OS")
    print("   3. Try to access Gmail with saved session")
    print("   4. Check if session works across OS/browsers")
    
    # Check if original browser data exists
    if not os.path.exists(ORIGINAL_BROWSER_DATA):
        print(f"\n❌ ERROR: No browser data found at {ORIGINAL_BROWSER_DATA}")
        print("   Run setup_accounts.py first to create account 1!")
        return
    
    print(f"\n✅ Found browser data at: {ORIGINAL_BROWSER_DATA}")
    
    # Check which browser was used during setup
    last_browser_file = os.path.join(ORIGINAL_BROWSER_DATA, 'Last Browser')
    if os.path.exists(last_browser_file):
        with open(last_browser_file, 'r') as f:
            original_browser = f.read().strip()
        print(f"   Original browser: {original_browser}")
    
    # Get Chrome path for current OS
    chrome_path = get_chrome_path()
    
    if not chrome_path:
        print(f"\n❌ ERROR: Google Chrome not found on {OS_TYPE}")
        if OS_TYPE == 'Linux':
            print("\n📦 Install Chrome on Linux:")
            print("   wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb")
            print("   sudo apt install ./google-chrome-stable_current_amd64.deb")
        elif OS_TYPE == 'Darwin':
            print("\n📦 Install Chrome on Mac:")
            print("   brew install --cask google-chrome")
        return
    
    print(f"   Testing with: {chrome_path}")
    
    # Create test directory
    os.makedirs(TEST_DIR, exist_ok=True)
    
    # Copy browser data
    print(f"\n📋 Copying browser data to test location...")
    if os.path.exists(COPIED_BROWSER_DATA):
        shutil.rmtree(COPIED_BROWSER_DATA)
    
    shutil.copytree(ORIGINAL_BROWSER_DATA, COPIED_BROWSER_DATA)
    print(f"   ✅ Copied to: {COPIED_BROWSER_DATA}")
    
    # Test with Chrome on current OS
    print(f"\n🚀 Testing with Google Chrome on {OS_TYPE}...")
    
    with sync_playwright() as p:
        try:
            # Launch Chrome with copied profile
            context = p.chromium.launch_persistent_context(
                user_data_dir=COPIED_BROWSER_DATA,
                executable_path=chrome_path,  # Use Chrome on current OS
                headless=False,  # Visible so you can see
                args=[
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--no-first-run',
                    '--window-size=1280,720'
                ],
                viewport={'width': 1280, 'height': 720}
            )
            
            page = context.pages[0] if context.pages else context.new_page()
            
            print("\n✅ Chrome launched successfully!")
            
            # Navigate to Gmail
            print("\n🌐 Navigating to Gmail...")
            page.goto('https://mail.google.com', wait_until='networkidle', timeout=30000)
            time.sleep(3)
            
            current_url = page.url
            print(f"   Current URL: {current_url}")
            
            # Check if logged in
            if "mail.google.com" in current_url and "accounts.google.com" not in current_url:
                print("\n🎉 SUCCESS! Session is portable!")
                print(f"   ✅ Browser data works across OS ({OS_TYPE})")
                print("   ✅ Logged into Gmail without re-authentication")
                print("   ✅ Profile is CROSS-PLATFORM PORTABLE!")
                
                # Try to get email
                try:
                    time.sleep(2)
                    print("\n📧 Gmail appears to be loaded!")
                except:
                    pass
                
            elif "accounts.google.com" in current_url:
                print("\n❌ FAILED - Redirected to login page")
                print("   The profile loaded, but session is NOT portable")
                print("   Possible reasons:")
                print("   - Cookie encryption is OS-specific")
                print("   - Browser fingerprint mismatch")
                print("   - Security token incompatibility")
                print(f"\n   Browser data from {original_browser if 'original_browser' in locals() else 'unknown'}")
                print(f"   Cannot be used on {OS_TYPE} with Chrome")
            else:
                print(f"\n⚠ UNEXPECTED - Redirected to: {current_url}")
            
            print("\n📋 Browser will stay open. Check if you see:")
            print("   ✅ Gmail inbox (logged in) = Profile is portable!")
            print("   ❌ Login page = Profile NOT portable (OS/browser-specific)")
            
            print("\n⏳ Press ENTER to close browser...")
            input()
            
            context.close()
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    test_portability()
