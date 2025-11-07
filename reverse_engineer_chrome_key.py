"""
Decrypt a cookie from the real Chrome profile to reverse-engineer the key
"""

import sqlite3
import os
from Crypto.Cipher import AES
import hashlib

def try_decrypt_cookie(encrypted_value, key_material):
    """Try to decrypt with given key"""
    try:
        # Remove v10 prefix
        if encrypted_value[:3] != b'v10':
            return None, "Not v10 format"
        
        encrypted_value = encrypted_value[3:]
        
        # Extract nonce (12 bytes)
        nonce = encrypted_value[:12]
        
        # Extract ciphertext and tag
        ciphertext_and_tag = encrypted_value[12:]
        
        # Create cipher
        cipher = AES.new(key_material, AES.MODE_GCM, nonce=nonce)
        
        # Decrypt
        plaintext = cipher.decrypt_and_verify(ciphertext_and_tag[:-16], ciphertext_and_tag[-16:])
        
        return plaintext.decode('utf-8'), None
        
    except Exception as e:
        return None, str(e)

# Get a cookie from real Chrome
test_profile = os.path.join(os.getcwd(), 'test_chrome_profile')
cookies_db = os.path.join(test_profile, 'Default', 'Cookies')

print("=" * 80)
print("REVERSE ENGINEERING CHROME ENCRYPTION KEY")
print("=" * 80)

if not os.path.exists(cookies_db):
    print("❌ Real Chrome profile not found")
    exit(1)

conn = sqlite3.connect(cookies_db)
cursor = conn.cursor()

# Get a cookie to test
cursor.execute("SELECT name, encrypted_value FROM cookies WHERE LENGTH(encrypted_value) > 0 LIMIT 1")
row = cursor.fetchone()

if not row:
    print("❌ No encrypted cookies found")
    exit(1)

cookie_name, encrypted_value = row
conn.close()

print(f"\n🍪 Testing with cookie: {cookie_name}")
print(f"📊 Encrypted size: {len(encrypted_value)} bytes")
print(f"🔍 First bytes (hex): {encrypted_value[:20].hex()}")

# Try different key derivations
print("\n🔐 Trying different key derivations...")

# Method 1: Direct "peanuts"
print("\n1. Direct 'peanuts' key (padded to 16 bytes)")
key1 = b'peanuts' + b'\x00' * 9  # Pad to 16 bytes
plaintext, error = try_decrypt_cookie(encrypted_value, key1)
if plaintext:
    print(f"   ✅ SUCCESS: {plaintext[:100]}")
else:
    print(f"   ❌ Failed: {error}")

# Method 2: PBKDF2 with 'peanuts'
print("\n2. PBKDF2('peanuts', 'saltysalt', 1 iteration, 16 bytes)")
key2 = hashlib.pbkdf2_hmac('sha1', b'peanuts', b'saltysalt', 1, dklen=16)
plaintext, error = try_decrypt_cookie(encrypted_value, key2)
if plaintext:
    print(f"   ✅ SUCCESS: {plaintext[:100]}")
else:
    print(f"   ❌ Failed: {error}")

# Method 3: PBKDF2 with 1003 iterations (Firefox-style)
print("\n3. PBKDF2('peanuts', 'saltysalt', 1003 iterations, 16 bytes)")
key3 = hashlib.pbkdf2_hmac('sha1', b'peanuts', b'saltysalt', 1003, dklen=16)
plaintext, error = try_decrypt_cookie(encrypted_value, key3)
if plaintext:
    print(f"   ✅ SUCCESS: {plaintext[:100]}")
else:
    print(f"   ❌ Failed: {error}")

# Method 4: Read from Local State (if exists)
local_state = os.path.join(test_profile, 'Local State')
if os.path.exists(local_state):
    print("\n4. Key from Local State file")
    import json
    with open(local_state, 'r') as f:
        state = json.load(f)
    
    if 'os_crypt' in state and 'encrypted_key' in state['os_crypt']:
        import base64
        enc_key_b64 = state['os_crypt']['encrypted_key']
        enc_key = base64.b64decode(enc_key_b64)
        print(f"   Found encrypted_key: {enc_key[:20].hex()}...")
        
        # On Linux, the key might not be DPAPI encrypted
        # Try removing DPAPI prefix if present
        if enc_key[:5] == b'DPAPI':
            enc_key = enc_key[5:]
            print(f"   Removed DPAPI prefix")
        
        # Try using as-is
        if len(enc_key) == 16:
            plaintext, error = try_decrypt_cookie(encrypted_value, enc_key)
            if plaintext:
                print(f"   ✅ SUCCESS: {plaintext[:100]}")
            else:
                print(f"   ❌ Failed: {error}")
    else:
        print("   ❌ No encrypted_key in Local State")
else:
    print("\n4. No Local State file")

# Method 5: Try reading Chrome's actual encryption
print("\n5. Checking Chrome's keyring storage...")
print("   Note: Chrome on Linux may use:")
print("   - GNOME Keyring (Secret Service)")
print("   - KWallet (KDE)")
print("   - Fallback to 'peanuts'")
print("   WSL may not have access to these keyrings")

print("\n" + "=" * 80)
print("CONCLUSION")
print("=" * 80)
print("""
If none of the above methods worked, it means:
1. Chrome is using system keyring (not accessible from WSL)
2. We need to match the EXACT encryption Chrome is using
3. Alternative: Let Chrome encrypt the cookies for us
""")
