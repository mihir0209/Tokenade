"""
Quick Setup - Install Playwright Browsers

Run this first before using the cookie extractor
"""

import subprocess
import sys

def install_playwright_browsers():
    """Install Playwright browser binaries"""
    
    print("=" * 80)
    print("Installing Playwright Browsers")
    print("=" * 80)
    
    print("\n📦 Installing Chromium browser...")
    print("This may take a few minutes...\n")
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True
        )
        
        print(result.stdout)
        
        if result.returncode == 0:
            print("\n✅ Chromium installed successfully!")
            return True
        else:
            print(f"\n❌ Installation failed!")
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("\n🚀 Playwright Setup for Cookie Extraction\n")
    
    success = install_playwright_browsers()
    
    if success:
        print("\n" + "=" * 80)
        print("✅ SETUP COMPLETE!")
        print("=" * 80)
        print("\n📝 Next steps:")
        print("   1. Set your Google credentials:")
        print('      $env:GOOGLE_EMAIL = "your-email@gmail.com"')
        print('      $env:GOOGLE_PASSWORD = "your-password-or-app-password"')
        print("\n   2. Run the cookie extractor:")
        print("      python extract_cookies_browser.py")
        print("\n📖 For detailed setup instructions:")
        print("      See BROWSER_AUTOMATION_SETUP.md")
    else:
        print("\n" + "=" * 80)
        print("❌ SETUP FAILED")
        print("=" * 80)
        print("\nTry manual installation:")
        print("   python -m playwright install chromium")
