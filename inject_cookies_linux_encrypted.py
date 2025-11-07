"""
Encrypt cookies for Linux Chrome using the default encryption key

Linux Chrome uses:
1. Secret Service (if available) - but we don't have access to this
2. Fallback: hardcoded key "peanuts" (base64: cGVhbnV0cw==)

We'll use the fallback method since it works without system keyring access.
"""

import sqlite3
import os
import json
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
import base64

def get_linux_chrome_key():
    """
    Get the Chrome encryption key for Linux
    
    Linux Chrome uses a fallback key "peanuts" when Secret Service is unavailable.
    This is a well-known Chrome behavior.
    """
    # Chrome's fallback encryption key on Linux
    return b'peanuts'

def encrypt_cookie_value_linux(plaintext_value):
    """
    Encrypt a cookie value for Linux Chrome
    
    Format: v10 + nonce (12 bytes) + ciphertext + tag (16 bytes)
    Uses AES-256-GCM
    """
    # Get encryption key
    key = get_linux_chrome_key()
    
    # Derive 256-bit key from the password using PBKDF2
    # Chrome uses a simple derivation: SHA-1 hash repeated to get 32 bytes
    import hashlib
    key_material = hashlib.pbkdf2_hmac('sha1', key, b'saltysalt', 1, dklen=16)
    
    # Generate random nonce (12 bytes for GCM)
    nonce = get_random_bytes(12)
    
    # Create cipher
    cipher = AES.new(key_material, AES.MODE_GCM, nonce=nonce)
    
    # Encrypt the value
    ciphertext, tag = cipher.encrypt_and_digest(plaintext_value.encode('utf-8'))
    
    # Format: v10 + nonce + ciphertext + tag
    encrypted = b'v10' + nonce + ciphertext + tag
    
    return encrypted

def inject_encrypted_cookies(json_path, cookies_db_path):
    """
    Inject cookies into Linux Chrome database WITH ENCRYPTION
    """
    
    print(f"\n📁 Reading cookies from: {json_path}")
    
    # Load decrypted cookies
    with open(json_path, 'r', encoding='utf-8') as f:
        cookies = json.load(f)
    
    print(f"📊 Loaded {len(cookies)} cookies")
    
    # Create database directory
    os.makedirs(os.path.dirname(cookies_db_path), exist_ok=True)
    
    # Delete old database if exists
    if os.path.exists(cookies_db_path):
        os.remove(cookies_db_path)
    
    # Create new database
    conn = sqlite3.connect(cookies_db_path)
    cursor = conn.cursor()
    
    # Create cookies table (Chrome 120+ schema)
    cursor.execute("""
        CREATE TABLE cookies(
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
    
    cursor.execute("CREATE INDEX domain ON cookies(host_key)")
    
    # Create meta table
    cursor.execute("""
        CREATE TABLE meta(
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    cursor.execute("INSERT INTO meta VALUES ('version', '20')")
    cursor.execute("INSERT INTO meta VALUES ('last_compatible_version', '20')")
    
    print(f"\n🔐 Encrypting and injecting cookies...")
    
    from datetime import datetime
    
    def get_chrome_time(dt=None):
        if dt is None:
            dt = datetime.now()
        epoch = datetime(1601, 1, 1)
        delta = dt - epoch
        return int(delta.total_seconds() * 1000000)
    
    current_time = get_chrome_time()
    
    success_count = 0
    failed_count = 0
    
    for cookie in cookies:
        try:
            # Encrypt the cookie value
            encrypted_value = encrypt_cookie_value_linux(cookie['value'])
            
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
                cookie['host_key'],
                cookie['name'],
                '',  # Empty value field
                encrypted_value,  # Encrypted in encrypted_value field
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
                443 if cookie.get('is_secure', False) else 80,
                current_time,
                0,
                0
            ))
            
            success_count += 1
            
        except Exception as e:
            print(f"   ⚠️  Failed: {cookie['name']} - {e}")
            failed_count += 1
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ Injection complete!")
    print(f"   Successfully injected: {success_count}")
    print(f"   Failed: {failed_count}")
    
    return success_count

if __name__ == "__main__":
    import sys
    
    base_dir = os.getcwd()
    
    if len(sys.argv) > 1:
        account_num = sys.argv[1]
    else:
        account_num = '1'
    
    json_path = os.path.join(base_dir, 'decrypted_cookies', f'account_{account_num}_cookies.json')
    db_path = os.path.join(base_dir, 'browser_data', account_num, 'Default', 'Network', 'Cookies')
    
    print("=" * 80)
    print("LINUX CHROME COOKIE INJECTION - WITH ENCRYPTION")
    print("=" * 80)
    print(f"\n🔐 Using Linux Chrome encryption (v10 + 'peanuts' key)")
    
    inject_encrypted_cookies(json_path, db_path)
    
    print(f"\n✅ Done! Database created at: {db_path}")
