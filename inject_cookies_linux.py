"""
Linux Chrome Cookie Injector

This script imports decrypted cookies (from Windows) into a Linux Chrome profile.
It creates a new Cookies database compatible with Linux Chrome.

Usage:
    python3 inject_cookies_linux.py

This will:
1. Read decrypted cookies from JSON files
2. Create/update Linux Chrome Cookies database
3. Encrypt cookies using Linux encryption (if needed)
"""

import sqlite3
import os
import json
import platform
from datetime import datetime

def get_chrome_datetime_microseconds(dt):
    """Convert Python datetime to Chrome timestamp (microseconds since 1601-01-01)"""
    if dt is None:
        return 0
    
    # Chrome epoch: January 1, 1601
    epoch = datetime(1601, 1, 1)
    delta = dt - epoch
    return int(delta.total_seconds() * 1000000)

def create_cookies_database(db_path):
    """Create a fresh Chrome Cookies database with proper schema"""
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create cookies table (Chrome 120+ schema)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cookies(
            creation_utc INTEGER NOT NULL,
            host_key TEXT NOT NULL,
            top_frame_site_key TEXT NOT NULL,
            name TEXT NOT NULL,
            value TEXT NOT NULL,
            encrypted_value BLOB NOT NULL,
            path TEXT NOT NULL,
            expires_utc INTEGER NOT NULL,
            is_secure INTEGER NOT NULL,
            is_httponly INTEGER NOT NULL,
            last_access_utc INTEGER NOT NULL,
            has_expires INTEGER NOT NULL,
            is_persistent INTEGER NOT NULL,
            priority INTEGER NOT NULL,
            samesite INTEGER NOT NULL,
            source_scheme INTEGER NOT NULL,
            source_port INTEGER NOT NULL,
            last_update_utc INTEGER NOT NULL,
            source_type INTEGER NOT NULL,
            has_cross_site_ancestor INTEGER NOT NULL,
            UNIQUE (host_key, top_frame_site_key, name, path)
        )
    """)
    
    # Create index for performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS domain ON cookies(host_key)
    """)
    
    # Create meta table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS meta(
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Set version
    cursor.execute("INSERT OR REPLACE INTO meta VALUES ('version', '20')")
    cursor.execute("INSERT OR REPLACE INTO meta VALUES ('last_compatible_version', '20')")
    
    conn.commit()
    conn.close()
    
    print(f"✅ Created cookies database: {db_path}")

def inject_cookies_from_json(json_path, cookies_db_path):
    """
    Inject decrypted cookies from JSON into Linux Chrome database
    
    Args:
        json_path: Path to decrypted cookies JSON file
        cookies_db_path: Path to target Chrome Cookies database
    """
    
    print(f"\n📁 Reading cookies from: {json_path}")
    
    # Load decrypted cookies
    with open(json_path, 'r', encoding='utf-8') as f:
        cookies = json.load(f)
    
    print(f"📊 Loaded {len(cookies)} cookies")
    
    # Create database if it doesn't exist
    if not os.path.exists(cookies_db_path):
        print(f"\n📋 Creating new cookies database...")
        create_cookies_database(cookies_db_path)
    
    # Connect to database
    conn = sqlite3.connect(cookies_db_path)
    cursor = conn.cursor()
    
    print(f"\n💉 Injecting cookies into database...")
    
    success_count = 0
    skipped_count = 0
    
    for cookie in cookies:
        try:
            # On Linux, we store cookies as PLAIN TEXT (no encryption)
            # Chrome will handle encryption internally if needed
            
            # Get current time for last_update_utc
            current_time = get_chrome_datetime_microseconds(datetime.now())
            
            cursor.execute("""
                INSERT OR REPLACE INTO cookies (
                    creation_utc, host_key, top_frame_site_key, name, value, encrypted_value,
                    path, expires_utc, is_secure, is_httponly, last_access_utc,
                    has_expires, is_persistent, priority, samesite, source_scheme,
                    source_port, last_update_utc, source_type, has_cross_site_ancestor
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cookie.get('creation_utc', current_time),
                cookie['host_key'],
                cookie['host_key'],  # top_frame_site_key = host_key
                cookie['name'],
                cookie['value'],  # Plain text value
                b'',  # Empty encrypted_value (Linux Chrome will encrypt if needed)
                cookie['path'],
                cookie.get('expires_utc', 0),
                1 if cookie.get('is_secure', False) else 0,
                1 if cookie.get('is_httponly', False) else 0,
                cookie.get('last_access_utc', current_time),
                1 if cookie.get('has_expires', True) else 0,
                1 if cookie.get('is_persistent', True) else 0,
                cookie.get('priority', 1),
                cookie.get('samesite', -1),
                cookie.get('source_scheme', 2),
                443 if cookie.get('is_secure', False) else 80,  # source_port
                current_time,  # last_update_utc
                0,  # source_type
                0   # has_cross_site_ancestor
            ))
            
            success_count += 1
            
        except Exception as e:
            print(f"   ⚠️  Failed to inject cookie {cookie['name']}: {e}")
            skipped_count += 1
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ Injection complete!")
    print(f"   Successfully injected: {success_count}")
    print(f"   Skipped: {skipped_count}")
    
    return success_count

def inject_all_accounts():
    """Inject cookies for all accounts into Linux Chrome profiles"""
    
    base_dir = os.path.dirname(__file__)
    decrypted_dir = os.path.join(base_dir, 'decrypted_cookies')
    browser_data_base = os.path.join(base_dir, 'browser_data')
    
    print("\n" + "=" * 80)
    print("BATCH COOKIE INJECTION - Linux Chrome")
    print("=" * 80)
    print(f"\n🖥️  Platform: {platform.system()}")
    
    if not os.path.exists(decrypted_dir):
        print(f"\n❌ Decrypted cookies directory not found: {decrypted_dir}")
        print(f"   Run decrypt_cookies_windows.py on Windows first!")
        return
    
    # Find all decrypted cookie JSON files
    json_files = [f for f in os.listdir(decrypted_dir) if f.endswith('_cookies.json')]
    
    if not json_files:
        print(f"\n❌ No decrypted cookie files found in: {decrypted_dir}")
        return
    
    print(f"\n📋 Found {len(json_files)} cookie file(s)")
    
    # Create browser_data directory if needed
    os.makedirs(browser_data_base, exist_ok=True)
    
    success_count = 0
    
    for json_file in sorted(json_files):
        # Extract account number from filename (e.g., account_1_cookies.json -> 1)
        account_num = json_file.split('_')[1]
        
        json_path = os.path.join(decrypted_dir, json_file)
        
        # Create account directory structure
        account_dir = os.path.join(browser_data_base, account_num)
        default_dir = os.path.join(account_dir, 'Default')
        network_dir = os.path.join(default_dir, 'Network')
        
        os.makedirs(network_dir, exist_ok=True)
        
        cookies_db_path = os.path.join(network_dir, 'Cookies')
        
        print(f"\n{'=' * 80}")
        print(f"Account {account_num}")
        print(f"{'=' * 80}")
        print(f"Target: {cookies_db_path}")
        
        try:
            count = inject_cookies_from_json(json_path, cookies_db_path)
            if count > 0:
                success_count += 1
        except Exception as e:
            print(f"❌ Error injecting cookies for account {account_num}: {e}")
    
    print("\n\n" + "=" * 80)
    print("BATCH INJECTION COMPLETE")
    print("=" * 80)
    print(f"\n✅ Successfully injected: {success_count}/{len(json_files)} accounts")
    print(f"\n📁 Chrome profiles created in: {browser_data_base}")
    print(f"\n🚀 Next steps:")
    print(f"   1. Use these profiles with collect_all_cookies.py or setup_accounts.py")
    print(f"   2. Chrome will read the plain-text cookies")
    print(f"   3. Your Google sessions should work!")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Inject specific account
        account_num = sys.argv[1]
        json_path = f"decrypted_cookies/account_{account_num}_cookies.json"
        cookies_db = f"browser_data/{account_num}/Default/Network/Cookies"
        
        os.makedirs(os.path.dirname(cookies_db), exist_ok=True)
        
        inject_cookies_from_json(json_path, cookies_db)
    else:
        # Inject all accounts
        inject_all_accounts()
