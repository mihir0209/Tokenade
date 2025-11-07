"""
Analyze how real Chrome on Linux encrypts cookies
"""

import sqlite3
import os

def analyze_chrome_encryption():
    """Check how Playwright's Chrome encrypts cookies"""
    
    test_profile = os.path.join(os.getcwd(), 'test_chrome_profile')
    cookies_db = os.path.join(test_profile, 'Default', 'Cookies')
    
    print("=" * 80)
    print("ANALYZING REAL CHROME COOKIE ENCRYPTION (Linux)")
    print("=" * 80)
    
    if not os.path.exists(cookies_db):
        print(f"❌ Not found: {cookies_db}")
        return
    
    print(f"\n📁 Database: {cookies_db}")
    print(f"📊 Size: {os.path.getsize(cookies_db):,} bytes")
    
    conn = sqlite3.connect(cookies_db)
    cursor = conn.cursor()
    
    # Get all cookies
    cursor.execute("""
        SELECT name, host_key, 
               value, 
               encrypted_value,
               LENGTH(value) as val_len,
               LENGTH(encrypted_value) as enc_len
        FROM cookies
    """)
    
    cookies = cursor.fetchall()
    
    print(f"\n📊 Total cookies: {len(cookies)}")
    
    for cookie in cookies:
        name, host, value, enc_value, val_len, enc_len = cookie
        
        print(f"\n🍪 Cookie: {name} ({host})")
        print(f"   Value length: {val_len} bytes")
        print(f"   Encrypted length: {enc_len} bytes")
        
        if val_len > 0:
            print(f"   ✅ Uses PLAIN TEXT storage (value field)")
            print(f"   Value: {value}")
        
        if enc_len > 0:
            print(f"   🔒 Uses ENCRYPTED storage (encrypted_value field)")
            # Show first few bytes in hex
            hex_preview = enc_value[:20].hex() if len(enc_value) >= 20 else enc_value.hex()
            print(f"   Encrypted (hex): {hex_preview}...")
            
            # Check for version prefix
            if enc_value[:3] == b'v10':
                print(f"   📋 Encryption: v10 (AES-256-GCM) - SAME AS WINDOWS!")
            elif enc_value[:3] == b'v11':
                print(f"   📋 Encryption: v11")
            else:
                print(f"   📋 Encryption: Unknown (first 3 bytes: {enc_value[:3]})")
    
    # Check if there's a Local State file
    local_state = os.path.join(test_profile, 'Local State')
    if os.path.exists(local_state):
        print(f"\n📄 Local State file exists: {local_state}")
        import json
        with open(local_state, 'r') as f:
            state = json.load(f)
            if 'os_crypt' in state and 'encrypted_key' in state['os_crypt']:
                print(f"   🔑 Has encrypted_key field")
                enc_key = state['os_crypt']['encrypted_key']
                print(f"   Key (base64): {enc_key[:50]}...")
            else:
                print(f"   ❌ No os_crypt.encrypted_key field")
    else:
        print(f"\n❌ No Local State file")
    
    conn.close()

if __name__ == "__main__":
    analyze_chrome_encryption()
