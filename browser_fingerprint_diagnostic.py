"""
Browser Fingerprint Diagnostic Tool

This script compares browser fingerprints between Windows and Linux
to identify why Google is invalidating cross-platform cookies.
"""

import os
import json
import platform
from playwright.sync_api import sync_playwright
from datetime import datetime

def get_chrome_path():
    """Get Google Chrome path based on OS"""
    OS_TYPE = platform.system()

    if OS_TYPE == 'Windows':
        paths = [
            r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'
        ]
    elif OS_TYPE == 'Linux':
        paths = [
            '/usr/bin/google-chrome',
            '/usr/bin/google-chrome-stable',
            '/usr/bin/chromium',
            '/usr/bin/chromium-browser'
        ]
    elif OS_TYPE == 'Darwin':  # Mac
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

def collect_browser_fingerprint():
    """Collect comprehensive browser fingerprint data"""

    fingerprint = {
        'os': platform.system(),
        'os_version': platform.version(),
        'architecture': platform.machine(),
        'python_version': platform.python_version(),
        'timestamp': datetime.now().isoformat(),
    }

    chrome_path = get_chrome_path()
    if chrome_path:
        fingerprint['chrome_path'] = chrome_path
        fingerprint['chrome_exists'] = True
    else:
        fingerprint['chrome_path'] = None
        fingerprint['chrome_exists'] = False

    with sync_playwright() as p:
        # Launch browser with minimal args to get baseline fingerprint
        launch_args = {
            'headless': True,
            'args': [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--no-first-run',
                '--disable-default-apps',
                '--disable-extensions',
                '--disable-plugins',
                '--disable-images',
                '--disable-javascript',  # Disable JS to get static fingerprint
            ]
        }

        if chrome_path:
            launch_args['executable_path'] = chrome_path

        try:
            browser = p.chromium.launch(**launch_args)
            context = browser.new_context()
            page = context.new_page()

            # Collect fingerprint data via JavaScript
            fingerprint_data = page.evaluate("""
                ({
                    userAgent: navigator.userAgent,
                    platform: navigator.platform,
                    language: navigator.language,
                    languages: navigator.languages,
                    cookieEnabled: navigator.cookieEnabled,
                    doNotTrack: navigator.doNotTrack,
                    hardwareConcurrency: navigator.hardwareConcurrency,
                    deviceMemory: navigator.deviceMemory,
                    screen: {
                        width: screen.width,
                        height: screen.height,
                        colorDepth: screen.colorDepth,
                        pixelDepth: screen.pixelDepth
                    },
                    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                    timezoneOffset: new Date().getTimezoneOffset(),
                    plugins: Array.from(navigator.plugins).map(p => ({
                        name: p.name,
                        description: p.description,
                        filename: p.filename
                    })),
                    webdriver: navigator.webdriver,
                    webkitPersistentStorage: typeof navigator.webkitPersistentStorage,
                    webkitTemporaryStorage: typeof navigator.webkitTemporaryStorage
                })
            """)

            fingerprint.update(fingerprint_data)

            # Test cookie functionality
            page.goto('data:text/html,<html><body>Test</body></html>')

            # Set a test cookie
            context.add_cookies([{
                'name': 'test_fingerprint',
                'value': 'fingerprint_test_value',
                'domain': 'example.com',
                'path': '/'
            }])

            # Check if cookie was set
            cookies = context.cookies()
            test_cookie = next((c for c in cookies if c['name'] == 'test_fingerprint'), None)
            fingerprint['cookie_functionality'] = test_cookie is not None

            context.close()
            browser.close()

        except Exception as e:
            fingerprint['error'] = str(e)

    return fingerprint

def compare_fingerprints(fp1, fp2, name1="Windows", name2="Linux"):
    """Compare two browser fingerprints and identify differences"""

    print(f"\n{'='*80}")
    print(f"BROWSER FINGERPRINT COMPARISON: {name1} vs {name2}")
    print(f"{'='*80}")

    differences = []

    # Compare key fingerprint attributes
    compare_keys = [
        'userAgent', 'platform', 'language', 'timezone', 'timezoneOffset',
        'screen', 'hardwareConcurrency', 'deviceMemory', 'cookieEnabled'
    ]

    for key in compare_keys:
        val1 = fp1.get(key)
        val2 = fp2.get(key)

        if val1 != val2:
            differences.append({
                'attribute': key,
                'windows': val1,
                'linux': val2
            })
            print(f"❌ {key}:")
            print(f"   {name1}: {val1}")
            print(f"   {name2}: {val2}")
        else:
            print(f"✅ {key}: {val1}")

    # Check for webdriver detection
    if fp1.get('webdriver') or fp2.get('webdriver'):
        differences.append({
            'attribute': 'webdriver_detected',
            'windows': fp1.get('webdriver'),
            'linux': fp2.get('webdriver')
        })
        print(f"⚠️  Webdriver detected - automation flagged!")

    # Check cookie functionality
    cookie1 = fp1.get('cookie_functionality', False)
    cookie2 = fp2.get('cookie_functionality', False)

    if cookie1 != cookie2:
        differences.append({
            'attribute': 'cookie_functionality',
            'windows': cookie1,
            'linux': cookie2
        })
        print(f"❌ Cookie functionality differs!")

    print(f"\n📊 Summary:")
    print(f"   Total differences: {len(differences)}")

    if differences:
        print(f"   These differences may cause Google to invalidate cookies!")
        print(f"   Key issues:")
        for diff in differences[:5]:  # Show first 5
            print(f"   • {diff['attribute']}")
    else:
        print(f"   Fingerprints are identical - cookie issues may be elsewhere")

    return differences

def save_fingerprint(fingerprint, filename):
    """Save fingerprint to JSON file"""
    with open(filename, 'w') as f:
        json.dump(fingerprint, f, indent=2)
    print(f"💾 Saved fingerprint to: {filename}")

def main():
    print("🔍 BROWSER FINGERPRINT DIAGNOSTIC TOOL")
    print("=" * 80)

    # Collect current system's fingerprint
    print(f"\n📱 Collecting browser fingerprint for {platform.system()}...")
    current_fp = collect_browser_fingerprint()

    # Save current fingerprint
    fp_file = f"fingerprint_{platform.system().lower()}.json"
    save_fingerprint(current_fp, fp_file)

    # Check if we have a comparison fingerprint
    other_os = "Linux" if platform.system() == "Windows" else "Windows"
    other_fp_file = f"fingerprint_{other_os.lower()}.json"

    if os.path.exists(other_fp_file):
        print(f"\n🔄 Loading {other_os} fingerprint for comparison...")
        with open(other_fp_file, 'r') as f:
            other_fp = json.load(f)

        differences = compare_fingerprints(
            current_fp if platform.system() == "Windows" else other_fp,
            other_fp if platform.system() == "Windows" else current_fp,
            "Windows", "Linux"
        )

        # Save comparison results
        comparison_file = "fingerprint_comparison.json"
        with open(comparison_file, 'w') as f:
            json.dump({
                'windows': current_fp if platform.system() == "Windows" else other_fp,
                'linux': other_fp if platform.system() == "Windows" else current_fp,
                'differences': differences,
                'comparison_timestamp': datetime.now().isoformat()
            }, f, indent=2)
        print(f"💾 Saved comparison to: {comparison_file}")

    else:
        print(f"\n⚠️  No {other_os} fingerprint found for comparison")
        print(f"   Run this script on {other_os} first to create comparison data")

    # Display current fingerprint summary
    print(f"\n📋 Current {platform.system()} Fingerprint Summary:")
    print(f"   OS: {current_fp.get('os')} {current_fp.get('os_version')}")
    print(f"   User Agent: {current_fp.get('userAgent', 'N/A')[:80]}...")
    print(f"   Platform: {current_fp.get('platform')}")
    print(f"   Timezone: {current_fp.get('timezone')}")
    print(f"   Screen: {current_fp.get('screen', {}).get('width')}x{current_fp.get('screen', {}).get('height')}")
    print(f"   Cookies work: {current_fp.get('cookie_functionality', False)}")
    print(f"   Webdriver detected: {current_fp.get('webdriver', False)}")

    if current_fp.get('error'):
        print(f"   ❌ Error: {current_fp['error']}")

if __name__ == "__main__":
    main()