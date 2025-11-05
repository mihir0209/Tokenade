"""
Test real browser (Edge/Brave) with Playwright
"""

from playwright.sync_api import sync_playwright
import os
import time

BROWSER_CONFIGS = {
    '1': {
        'name': 'Microsoft Edge',
        'path': r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        'channel': 'msedge'
    },
    '2': {
        'name': 'Brave Browser',
        'path': r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe',
        'channel': None
    }
}

def test_browser():
    print("\n" + "=" * 80)
    print("REAL BROWSER TEST - Edge/Brave")
    print("=" * 80)
    
    print("\n🌐 Select browser to test:")
    print("   1. Microsoft Edge")
    print("   2. Brave Browser")
    
    choice = input("\nEnter choice (1/2): ").strip() or '1'
    browser_config = BROWSER_CONFIGS.get(choice, BROWSER_CONFIGS['1'])
    
    print(f"\n✅ Testing: {browser_config['name']}")
    print(f"   Path: {browser_config['path']}")
    
    # Check if browser exists
    if not os.path.exists(browser_config['path']):
        print(f"\n❌ ERROR: Browser not found!")
        print(f"   Expected at: {browser_config['path']}")
        print("\n💡 Install the browser or update the path in the script.")
        return
    
    print("\n✅ Browser found!")
    
    # Create test directory
    test_dir = os.path.join(os.path.dirname(__file__), 'test_real_browser')
    os.makedirs(test_dir, exist_ok=True)
    
    print(f"\n🚀 Launching {browser_config['name']}...")
    
    with sync_playwright() as p:
        launch_options = {
            'user_data_dir': test_dir,
            'headless': False,
            'args': [
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--no-first-run',
                '--no-default-browser-check',
                '--window-size=1920,1080'
            ],
            'viewport': {'width': 1920, 'height': 1080},
            'ignore_default_args': ['--enable-automation']
        }
        
        # Add executable path
        launch_options['executable_path'] = browser_config['path']
        if browser_config['channel']:
            launch_options['channel'] = browser_config['channel']
        
        try:
            context = p.chromium.launch_persistent_context(**launch_options)
            page = context.pages[0] if context.pages else context.new_page()
            
            print("\n✅ Browser launched successfully!")
            
            # Navigate to Google Sign-In
            print("\n🌐 Navigating to Google Sign-In page...")
            page.goto('https://accounts.google.com/ServiceLogin')
            time.sleep(3)
            
            print("\n" + "=" * 80)
            print("SUCCESS! Real browser is working!")
            print("=" * 80)
            
            print(f"\n✅ {browser_config['name']} opened successfully")
            print("✅ Navigated to Google Sign-In page")
            print("\n📋 Try logging in to test if Google accepts this browser!")
            print("   If you can log in without errors, it works! ✅")
            
            print("\n⏳ Press ENTER to close the browser...")
            input()
            
            context.close()
            print("\n✅ Test complete!")
            
        except Exception as e:
            print(f"\n❌ Error launching browser: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_browser()
