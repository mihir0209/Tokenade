"""
Clear Browser Session - Delete saved cookies and session data

Run this to log out and start fresh with new credentials
"""

import os
import shutil

# Browser data directory
USER_DATA_DIR = os.path.join(os.path.dirname(__file__), 'browser_data')

def clear_session():
    """Delete the browser_data folder to clear session"""
    
    print("=" * 80)
    print("Clear Browser Session")
    print("=" * 80)
    
    if os.path.exists(USER_DATA_DIR):
        print(f"\n📁 Found browser data: {USER_DATA_DIR}")
        
        confirm = input("\n⚠  Are you sure you want to delete the saved session? (yes/no): ").strip().lower()
        
        if confirm in ['yes', 'y']:
            try:
                shutil.rmtree(USER_DATA_DIR)
                print("\n✅ Session cleared successfully!")
                print("   Next time you run extract_cookies_browser.py, you'll need to log in again.")
            except Exception as e:
                print(f"\n❌ Error deleting session: {e}")
        else:
            print("\n❌ Cancelled. Session not cleared.")
    else:
        print(f"\n✓ No saved session found. Nothing to clear.")
    
    print("=" * 80)

if __name__ == "__main__":
    clear_session()
