"""
Linux Transfer Package Creator

Creates a complete package for Linux with all necessary files
for fingerprint-matched cookie injection.
"""

import os
import zipfile
import json
import platform
from datetime import datetime

def create_linux_transfer_package():
    """Create a transfer package for Linux with all necessary files"""

    print("📦 CREATING LINUX TRANSFER PACKAGE")
    print("=" * 80)

    # Files to include
    required_files = [
        'decrypted_cookies/',
        'fingerprint_windows.json',
        'fingerprint_matched_injection.py',
        'browser_fingerprint_diagnostic.py',
        'collect_all_cookies.py',
        'setup_linux_auth.py',
        'diagnostic.py'  # NEW: Diagnostic script
    ]

    # Check if all required files exist
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)

    if missing_files:
        print(f"❌ Missing required files: {missing_files}")
        return False

    # Create package info
    package_info = {
        'created_at': datetime.now().isoformat(),
        'created_on': platform.system(),
        'purpose': 'Cross-platform Google authentication transfer',
        'instructions': [
            '1. Transfer this ZIP to your Linux VPS',
            '2. Extract the ZIP file',
            '3. Run: python3 diagnostic.py (check if environment is set up)',
            '4. Run: python3 fingerprint_matched_injection.py',
            '5. If Gmail still redirects, run: python3 setup_linux_auth.py',
            '6. Test with: python3 collect_all_cookies.py'
        ],
        'files_included': required_files,
        'notes': [
            'Cross-platform cookie injection has limitations due to Google security',
            'If fingerprint matching fails, use setup_linux_auth.py for one-time manual login',
            'Google Labs tokens are preserved and will work after authentication',
            'Gmail requires fresh login on Linux due to security restrictions'
        ]
    }

    # Create ZIP file
    zip_filename = f"google_auth_linux_transfer_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

    print(f"📁 Creating package: {zip_filename}")

    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Add package info
        zipf.writestr('PACKAGE_INFO.json', json.dumps(package_info, indent=2))

        # Add required files
        for file_path in required_files:
            if os.path.isdir(file_path.rstrip('/')):
                # Add directory contents
                for root, dirs, files in os.walk(file_path):
                    for file in files:
                        full_path = os.path.join(root, file)
                        arc_path = os.path.relpath(full_path, '.')
                        zipf.write(full_path, arc_path)
                        print(f"   ✅ Added: {arc_path}")
            else:
                # Add single file
                zipf.write(file_path, file_path)
                print(f"   ✅ Added: {file_path}")

    # Get file size
    file_size = os.path.getsize(zip_filename)
    file_size_mb = file_size / (1024 * 1024)

    print(f"\n✅ Package created successfully!")
    print(f"   📁 File: {zip_filename}")
    print(f"   📊 Size: {file_size_mb:.2f} MB")
    print(f"   📋 Contents: {len(required_files)} file groups")

    # Display instructions
    print(f"\n📋 TRANSFER INSTRUCTIONS:")
    print(f"   1. Copy {zip_filename} to your Linux VPS")
    print(f"   2. Extract: unzip {zip_filename}")
    print(f"   3. Navigate: cd {zip_filename.replace('.zip', '')}")
    print(f"   4. Run: python3 fingerprint_matched_injection.py")
    print(f"   5. Test Gmail manually")

    print(f"\n🎯 EXPECTED RESULTS:")
    print(f"   • Browser launches with Windows fingerprint")
    print(f"   • Gmail loads without redirect to sign-in")
    print(f"   • Full authentication persistence achieved")

    return zip_filename

def main():
    import platform

    if platform.system() != "Windows":
        print("❌ This script should be run on Windows to create the transfer package")
        return

    try:
        zip_file = create_linux_transfer_package()

        if zip_file:
            print(f"\n🚀 Ready to transfer: {zip_file}")
            print(f"   Use SCP, SFTP, or your preferred method to copy to Linux VPS")

    except Exception as e:
        print(f"❌ Error creating package: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()