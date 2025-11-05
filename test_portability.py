"""
Test Script: Verify browser_data portability

This script tests if browser profiles saved in browser_data/ can be used
with Playwright's Chromium (instead of the original Edge/Brave).

This is important for deployment/portability - can we use the saved sessions
anywhere without needing the original browser installed?
"""

from playwright.sync_api import sync_playwright
import os
import time
import shutil

# Paths
ORIGINAL_BROWSER_DATA = r'D:\Tokenade\browser_data\1'  # Account 1 from setup
TEST_DIR = os.path.join(os.path.dirname(__file__), 'test_portability')
COPIED_BROWSER_DATA = os.path.join(TEST_DIR, 'browser_data_copy')

def test_portability():
    print("\n" + "=" * 80)
    print("BROWSER DATA PORTABILITY TEST")
    print("=" * 80)
    
    print("\n📋 This test verifies if browser sessions are portable:")
    print("   1. Copy browser_data/1 to test location")
    print("   2. Use Playwright's Chromium (NOT Edge/Brave)")
    print("   3. Try to access Gmail with saved session")
    print("   4. Check if session persists")
    
    # Check if original browser data exists
    if not os.path.exists(ORIGINAL_BROWSER_DATA):
        print(f"\n❌ ERROR: No browser data found at {ORIGINAL_BROWSER_DATA}")
        print("   Run setup_accounts.py first to create account 1!")
        return
    
    print(f"\n✅ Found browser data at: {ORIGINAL_BROWSER_DATA}")
    
    # Create test directory
    os.makedirs(TEST_DIR, exist_ok=True)
    
    # Copy browser data
    print(f"\n📋 Copying browser data to test location...")
    if os.path.exists(COPIED_BROWSER_DATA):
        shutil.rmtree(COPIED_BROWSER_DATA)
    
    shutil.copytree(ORIGINAL_BROWSER_DATA, COPIED_BROWSER_DATA)
    print(f"   ✅ Copied to: {COPIED_BROWSER_DATA}")
    
    # Test with Playwright Chromium
    print(f"\n🚀 Testing with Playwright's Chromium (NOT Edge/Brave)...")
    
    with sync_playwright() as p:
        try:
            # Launch Playwright's Chromium with copied profile
            context = p.chromium.launch_persistent_context(
                user_data_dir=COPIED_BROWSER_DATA,
                headless=False,  # Visible so you can see
                args=[
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--no-first-run',
                    '--window-size=1280,720'
                ],
                viewport={'width': 1280, 'height': 720}
                # NOTE: No executable_path - uses Playwright's Chromium!
            )
            
            page = context.pages[0] if context.pages else context.new_page()
            
            print("\n✅ Playwright Chromium launched successfully!")
            
            # Navigate to Gmail
            print("\n🌐 Navigating to Gmail...")
            page.goto('https://mail.google.com', wait_until='networkidle', timeout=30000)
            time.sleep(3)
            
            current_url = page.url
            print(f"   Current URL: {current_url}")
            
            # Check if logged in
            if "mail.google.com" in current_url and "accounts.google.com" not in current_url:
                print("\n🎉 SUCCESS! Session is portable!")
                print("   ✅ Browser data works with Playwright Chromium")
                print("   ✅ Logged into Gmail without re-authentication")
                print("   ✅ Profile is PORTABLE!")
                
                # Try to get email
                try:
                    # Wait a bit for Gmail to load
                    time.sleep(2)
                    print("\n📧 Gmail appears to be loaded!")
                except:
                    pass
                
            elif "accounts.google.com" in current_url:
                print("\n⚠ PARTIAL SUCCESS - Redirected to login page")
                print("   The profile loaded, but session expired or incompatible")
                print("   This might be due to:")
                print("   - Browser fingerprint difference (Edge → Chromium)")
                print("   - Session timeout")
                print("   - Security checks")
            else:
                print(f"\n⚠ UNEXPECTED - Redirected to: {current_url}")
            
            print("\n📋 Browser will stay open. Check if you see:")
            print("   ✅ Gmail inbox (logged in) = Profile is portable!")
            print("   ❌ Login page = Profile not portable (browser-specific)")
            
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
