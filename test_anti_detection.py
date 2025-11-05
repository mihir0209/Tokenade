"""
Quick test to verify anti-detection measures are working
"""

from playwright.sync_api import sync_playwright
import os
import time

TEST_DIR = os.path.join(os.path.dirname(__file__), 'test_browser')

def test_anti_detection():
    print("\n" + "=" * 80)
    print("ANTI-DETECTION TEST")
    print("=" * 80)
    
    print("\n📋 Testing anti-detection measures...")
    print("   Browser will open and run checks in console.")
    print("   Watch the DevTools console for results.\n")
    
    with sync_playwright() as p:
        os.makedirs(TEST_DIR, exist_ok=True)
        
        context = p.chromium.launch_persistent_context(
            user_data_dir=TEST_DIR,
            headless=False,
            args=[
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--allow-running-insecure-content',
                '--disable-setuid-sandbox',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-infobars',
                '--window-size=1920,1080',
                '--auto-open-devtools-for-tabs'  # Opens DevTools automatically
            ],
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            ignore_default_args=['--enable-automation'],
            bypass_csp=True
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        # Inject anti-detection scripts
        page.add_init_script("""
            // Overwrite the `navigator.webdriver` property to hide automation
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // Overwrite the `plugins` property to add fake plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // Overwrite the `languages` property
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            
            // Add chrome object
            window.chrome = {
                runtime: {}
            };
            
            // Overwrite permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)
        
        # Go to Google Sign-In page
        print("🌐 Navigating to Google Sign-In page...")
        page.goto('https://accounts.google.com/ServiceLogin', wait_until='networkidle')
        time.sleep(3)
        
        # Run detection tests in browser console
        print("\n📊 Running detection tests in browser console...\n")
        
        # Test 1: navigator.webdriver
        webdriver_result = page.evaluate("navigator.webdriver")
        print(f"1. navigator.webdriver: {webdriver_result}")
        if webdriver_result is None:
            print("   ✅ PASS - Hidden from detection")
        else:
            print("   ❌ FAIL - Detected as automation")
        
        # Test 2: plugins
        plugins_count = page.evaluate("navigator.plugins.length")
        print(f"\n2. navigator.plugins.length: {plugins_count}")
        if plugins_count > 0:
            print("   ✅ PASS - Has fake plugins")
        else:
            print("   ❌ FAIL - No plugins (suspicious)")
        
        # Test 3: languages
        languages = page.evaluate("navigator.languages")
        print(f"\n3. navigator.languages: {languages}")
        if languages and len(languages) > 0:
            print("   ✅ PASS - Has languages set")
        else:
            print("   ❌ FAIL - No languages")
        
        # Test 4: window.chrome
        has_chrome = page.evaluate("typeof window.chrome !== 'undefined'")
        print(f"\n4. window.chrome exists: {has_chrome}")
        if has_chrome:
            print("   ✅ PASS - Chrome object present")
        else:
            print("   ❌ FAIL - No chrome object")
        
        # Test 5: User agent
        user_agent = page.evaluate("navigator.userAgent")
        print(f"\n5. User Agent: {user_agent}")
        if "Chrome/131" in user_agent:
            print("   ✅ PASS - Latest Chrome version")
        else:
            print("   ⚠ WARNING - Not latest Chrome")
        
        # Test 6: Check if automation banner exists
        automation_banner = page.query_selector('text="Chrome is being controlled by automated test software"')
        print(f"\n6. Automation banner present: {automation_banner is not None}")
        if automation_banner is None:
            print("   ✅ PASS - No automation banner")
        else:
            print("   ❌ FAIL - Automation banner visible")
        
        print("\n\n" + "=" * 80)
        print("TEST RESULTS")
        print("=" * 80)
        
        # Summary
        checks = [
            webdriver_result is None,
            plugins_count > 0,
            languages and len(languages) > 0,
            has_chrome,
            "Chrome/131" in user_agent,
            automation_banner is None
        ]
        
        passed = sum(checks)
        total = len(checks)
        
        print(f"\n✅ Passed: {passed}/{total} checks")
        
        if passed == total:
            print("\n🎉 ALL CHECKS PASSED! Anti-detection is working perfectly!")
            print("   Google should NOT detect this as an automated browser.")
        elif passed >= 4:
            print("\n✓ Most checks passed. Anti-detection is working well.")
            print("   Google likely won't detect automation.")
        else:
            print("\n⚠ Some checks failed. May still be detected.")
            print("   Review the failures above.")
        
        print("\n📋 The browser will stay open. Try logging into Google!")
        print("   If you can log in without 'browser may not be secure' error,")
        print("   then anti-detection is working! ✅")
        
        print("\n⏳ Press ENTER to close the browser...")
        input()
        
        context.close()
        print("\n✅ Test complete!")

if __name__ == "__main__":
    test_anti_detection()
