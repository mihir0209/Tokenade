"""
Find where Chrome actually stores cookies in the profile
"""

import os

def find_files(directory, pattern):
    """Recursively find files matching pattern"""
    matches = []
    try:
        for root, dirs, files in os.walk(directory):
            for file in files:
                if pattern.lower() in file.lower():
                    full_path = os.path.join(root, file)
                    size = os.path.getsize(full_path)
                    matches.append((full_path, size))
    except Exception as e:
        print(f"Error scanning {directory}: {e}")
    return matches

base_dir = os.getcwd()
test_profile = os.path.join(base_dir, 'test_chrome_profile')

print("=" * 80)
print("SEARCHING FOR COOKIE FILES IN CHROME PROFILE")
print("=" * 80)

print(f"\n📁 Profile directory: {test_profile}")

if not os.path.exists(test_profile):
    print("❌ Profile directory not found!")
else:
    print(f"✅ Profile exists!")
    
    # List all files in profile
    print("\n📋 Searching for 'Cookie' files...")
    cookie_files = find_files(test_profile, 'cookie')
    
    if cookie_files:
        print(f"\n✅ Found {len(cookie_files)} file(s) with 'cookie' in name:")
        for path, size in cookie_files:
            rel_path = os.path.relpath(path, test_profile)
            print(f"   📄 {rel_path}")
            print(f"      Size: {size:,} bytes")
    else:
        print("❌ No cookie files found!")
    
    # Also search for any database files
    print("\n📋 Searching for database files (.db, .sqlite, .sql)...")
    db_files = []
    for ext in ['.db', '.sqlite', '.sql']:
        db_files.extend([(p, s) for p, s in find_files(test_profile, ext)])
    
    if db_files:
        print(f"\n✅ Found {len(db_files)} database file(s):")
        for path, size in db_files:
            rel_path = os.path.relpath(path, test_profile)
            print(f"   📄 {rel_path}")
            print(f"      Size: {size:,} bytes")
    
    # List directory structure
    print("\n📋 Directory structure:")
    for root, dirs, files in os.walk(test_profile):
        level = root.replace(test_profile, '').count(os.sep)
        indent = ' ' * 2 * level
        rel_root = os.path.relpath(root, test_profile)
        if rel_root == '.':
            rel_root = '/'
        print(f"{indent}📁 {rel_root}/")
        
        sub_indent = ' ' * 2 * (level + 1)
        for file in files[:5]:  # Show first 5 files per directory
            print(f"{sub_indent}📄 {file}")
        if len(files) > 5:
            print(f"{sub_indent}   ... and {len(files) - 5} more files")
        
        # Don't go too deep
        if level > 3:
            del dirs[:]

print("\n" + "=" * 80)
