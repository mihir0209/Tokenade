"""
Debug script to understand Chrome cookie encryption format
"""

import sqlite3
import os
import json
import base64
import win32crypt
from Crypto.Cipher import AES

# Paths
cookies_db = r"D:\Tokenade\browser_data\1\Default\Network\Cookies.sqlite"
local_state = r"D:\Tokenade\browser_data\1\Local State"

# Get encryption key
print("=" * 80)
print("GETTING ENCRYPTION KEY")
print("=" * 80)

with open(local_state, 'r', encoding='utf-8') as f:
    state = json.load(f)

encrypted_key = base64.b64decode(state['os_crypt']['encrypted_key'])
print(f"\nEncrypted key (base64 decoded): {encrypted_key[:50].hex()}...")
print(f"First 5 bytes (should be 'DPAPI'): {encrypted_key[:5]}")

# Remove DPAPI prefix
encrypted_key = encrypted_key[5:]

# Decrypt with DPAPI
key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
print(f"\nDecrypted AES key: {key.hex()}")
print(f"Key length: {len(key)} bytes")

# Get a sample cookie
print("\n" + "=" * 80)
print("ANALYZING SAMPLE COOKIE")
print("=" * 80)

conn = sqlite3.connect(cookies_db + '.temp')
import shutil
shutil.copy2(cookies_db, cookies_db + '.temp')
conn = sqlite3.connect(cookies_db + '.temp')
cursor = conn.cursor()

cursor.execute("SELECT name, host_key, encrypted_value FROM cookies WHERE name='SID' LIMIT 1")
name, host, enc_value = cursor.fetchone()

print(f"\nCookie: {name}")
print(f"Host: {host}")
print(f"Encrypted value length: {len(enc_value)} bytes")
print(f"\nFirst 50 bytes (hex): {enc_value[:50].hex()}")
print(f"First 50 bytes (raw): {enc_value[:50]}")
print(f"\nFirst 3 bytes: {enc_value[:3]}")
print(f"First 3 bytes (hex): {enc_value[:3].hex()}")
print(f"Version string: {enc_value[:3].decode('latin-1')}")

# Try to decrypt
print("\n" + "=" * 80)
print("ATTEMPTING DECRYPTION")
print("=" * 80)

try:
    # Method 1: Standard v10 with nonce
    print("\n1️⃣  Trying standard Chrome v80+ format (v10 + 12-byte nonce + ciphertext)...")
    version = enc_value[:3]
    nonce = enc_value[3:15]
    ciphertext = enc_value[15:]
    
    print(f"   Version: {version}")
    print(f"   Nonce (12 bytes): {nonce.hex()}")
    print(f"   Ciphertext length: {len(ciphertext)} bytes")
    
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    decrypted = cipher.decrypt_and_verify(ciphertext[:-16], ciphertext[-16:])
    
    print(f"   Decrypted (hex): {decrypted[:50].hex()}")
    print(f"   Decrypted (raw): {decrypted}")
    
    # Try different offsets
    for offset in [0, 1, 16, 32]:
        try:
            value = decrypted[offset:].decode('utf-8')
            print(f"   Offset {offset}: {value[:100]}...")
            break
        except:
            pass
    
    print(f"   ✅ FOUND AT OFFSET!")
    
except Exception as e:
    print(f"   ❌ Failed: {e}")
    
    # Method 2: Try without tag verification
    try:
        print("\n2️⃣  Trying without tag verification...")
        nonce = enc_value[3:15]
        ciphertext = enc_value[15:-16]
        tag = enc_value[-16:]
        
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        decrypted = cipher.decrypt(ciphertext)
        
        print(f"   Decrypted (hex): {decrypted[:50].hex()}")
        print(f"   Decrypted (raw): {decrypted}")
        print(f"   ✅ SUCCESS: {decrypted.decode('utf-8')}")
        
    except Exception as e2:
        print(f"   ❌ Failed: {e2}")
        
        # Method 3: Old DPAPI
        try:
            print("\n3️⃣  Trying old DPAPI method...")
            decrypted = win32crypt.CryptUnprotectData(enc_value, None, None, None, 0)[1]
            print(f"   ✅ SUCCESS: {decrypted.decode('utf-8')}")
        except Exception as e3:
            print(f"   ❌ Failed: {e3}")

conn.close()
os.remove(cookies_db + '.temp')

print("\n" + "=" * 80)
