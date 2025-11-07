#!/usr/bin/env python3
"""
Quick diagnostic script to check if the environment is set up correctly
"""

import os
import sys
import platform

print("🔍 DIAGNOSTIC CHECK")
print("=" * 50)

print(f"Python version: {sys.version}")
print(f"Platform: {platform.system()}")
print(f"Current directory: {os.getcwd()}")

print(f"\nFiles in current directory:")
files = os.listdir('.')
for file in sorted(files):
    if file.endswith('.py') or file.endswith('.json'):
        print(f"  📄 {file}")

print(f"\nChecking required files:")
required_files = [
    'fingerprint_matched_injection.py',
    'fingerprint_windows.json',
    'decrypted_cookies/account_1_cookies.json'
]

for file in required_files:
    if os.path.exists(file):
        print(f"  ✅ {file}")
    else:
        print(f"  ❌ {file} - MISSING")

print(f"\nChecking Python imports:")
try:
    import json
    print("  ✅ json")
except ImportError:
    print("  ❌ json")

try:
    from playwright.sync_api import sync_playwright
    print("  ✅ playwright")
except ImportError:
    print("  ❌ playwright - Run: pip install playwright")

try:
    import platform
    print("  ✅ platform")
except ImportError:
    print("  ❌ platform")

print(f"\n🎯 If all files exist and imports work, try running:")
print(f"   python3 fingerprint_matched_injection.py")