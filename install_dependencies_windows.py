"""
Install required dependencies for cookie decryption on Windows

This script checks and installs:
1. pywin32 - For Windows DPAPI access
2. pycryptodome - For AES encryption/decryption
"""

import subprocess
import sys

def install_package(package_name):
    """Install a Python package using pip"""
    print(f"\n📦 Installing {package_name}...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        print(f"✅ {package_name} installed successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to install {package_name}: {e}")
        return False

def check_import(module_name, package_name=None):
    """Check if a module can be imported"""
    if package_name is None:
        package_name = module_name
    
    try:
        __import__(module_name)
        print(f"✅ {package_name} is already installed")
        return True
    except ImportError:
        print(f"⚠️  {package_name} not found")
        return False

def main():
    print("\n" + "=" * 80)
    print("COOKIE DECRYPTION DEPENDENCIES - Windows")
    print("=" * 80)
    
    print("\n🔍 Checking dependencies...")
    
    # Check pywin32
    needs_pywin32 = not check_import('win32crypt', 'pywin32')
    
    # Check pycryptodome
    needs_crypto = not check_import('Crypto', 'pycryptodome')
    
    if not needs_pywin32 and not needs_crypto:
        print("\n🎉 All dependencies are already installed!")
        print("\n✅ You're ready to run decrypt_cookies_windows.py")
        return
    
    print("\n📦 Installing missing dependencies...")
    
    if needs_pywin32:
        install_package('pywin32')
    
    if needs_crypto:
        install_package('pycryptodome')
    
    print("\n" + "=" * 80)
    print("INSTALLATION COMPLETE")
    print("=" * 80)
    print("\n✅ Dependencies installed successfully!")
    print("\n🚀 Next step:")
    print("   python decrypt_cookies_windows.py")

if __name__ == "__main__":
    main()
