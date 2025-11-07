"""
Cookie Database Analyzer - Understand Chrome Cookie Structure

This script analyzes the Cookies SQLite database to understand:
1. Cookie structure and fields
2. Encryption status
3. Which cookies are needed for Google services
4. Whether cookies can be portable
"""

import sqlite3
import os
import json
from datetime import datetime

def analyze_cookies_db(cookies_db_path):
    """Analyze the Chrome Cookies SQLite database"""
    
    print("\n" + "=" * 80)
    print("CHROME COOKIES DATABASE ANALYZER")
    print("=" * 80)
    
    if not os.path.exists(cookies_db_path):
        print(f"\n❌ Cookie database not found at: {cookies_db_path}")
        return
    
    print(f"\n📁 Analyzing: {cookies_db_path}")
    print(f"📊 File size: {os.path.getsize(cookies_db_path):,} bytes")
    
    try:
        # Connect to database
        conn = sqlite3.connect(cookies_db_path)
        cursor = conn.cursor()
        
        # Get table schema
        print("\n" + "=" * 80)
        print("DATABASE SCHEMA")
        print("=" * 80)
        
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='cookies'")
        schema = cursor.fetchone()
        if schema:
            print("\n📋 Cookies table structure:")
            print(schema[0])
        
        # Get column names
        cursor.execute("PRAGMA table_info(cookies)")
        columns = cursor.fetchall()
        
        print("\n📊 Columns in cookies table:")
        for col in columns:
            col_id, col_name, col_type, not_null, default_val, pk = col
            print(f"   {col_id}. {col_name} ({col_type})")
        
        # Count total cookies
        cursor.execute("SELECT COUNT(*) FROM cookies")
        total_cookies = cursor.fetchone()[0]
        
        print("\n" + "=" * 80)
        print(f"COOKIE STATISTICS")
        print("=" * 80)
        print(f"\n📊 Total cookies: {total_cookies}")
        
        # Group by domain
        cursor.execute("""
            SELECT host_key, COUNT(*) as count 
            FROM cookies 
            GROUP BY host_key 
            ORDER BY count DESC 
            LIMIT 20
        """)
        
        print("\n🌐 Top 20 domains by cookie count:")
        for domain, count in cursor.fetchall():
            print(f"   {domain}: {count} cookies")
        
        # Find Google-related cookies
        print("\n" + "=" * 80)
        print("GOOGLE SERVICE COOKIES")
        print("=" * 80)
        
        cursor.execute("""
            SELECT host_key, name, path, is_secure, is_httponly, has_expires, is_persistent,
                   LENGTH(encrypted_value) as enc_len,
                   LENGTH(value) as val_len
            FROM cookies 
            WHERE host_key LIKE '%google.com%' 
            OR host_key LIKE '%gmail.com%'
            OR host_key LIKE '%labs.google%'
            ORDER BY host_key, name
        """)
        
        google_cookies = cursor.fetchall()
        
        print(f"\n🔍 Found {len(google_cookies)} Google-related cookies")
        
        # Group by domain
        from collections import defaultdict
        by_domain = defaultdict(list)
        
        for row in google_cookies:
            host_key = row[0]
            cookie_name = row[1]
            by_domain[host_key].append(row)
        
        print(f"\n📊 Google cookies by domain:")
        for domain, cookies in sorted(by_domain.items()):
            print(f"\n   🌐 {domain} ({len(cookies)} cookies):")
            for cookie in cookies[:10]:  # Show first 10
                host_key, name, path, is_secure, is_httponly, has_expires, is_persistent, enc_len, val_len = cookie
                
                encryption_status = "🔒 Encrypted" if enc_len > 0 else "📝 Plain text"
                value_status = f"Value: {val_len} bytes" if val_len > 0 else "No value"
                
                print(f"      • {name}")
                print(f"        Path: {path}")
                print(f"        Secure: {is_secure}, HttpOnly: {is_httponly}, Persistent: {is_persistent}")
                print(f"        {encryption_status}, {value_status}")
        
        # Check for critical authentication cookies
        print("\n" + "=" * 80)
        print("CRITICAL AUTHENTICATION COOKIES")
        print("=" * 80)
        
        critical_cookie_names = ['SID', 'SSID', 'APISID', 'SAPISID', 'HSID', '__Secure-1PSID', '__Secure-3PSID', 'SIDCC']
        
        for cookie_name in critical_cookie_names:
            cursor.execute("""
                SELECT host_key, name, is_secure, is_httponly, 
                       LENGTH(encrypted_value) as enc_len,
                       LENGTH(value) as val_len,
                       creation_utc, expires_utc
                FROM cookies 
                WHERE name = ?
                ORDER BY host_key
            """, (cookie_name,))
            
            results = cursor.fetchall()
            if results:
                print(f"\n🔑 {cookie_name} ({len(results)} found):")
                for row in results:
                    host, name, secure, httponly, enc_len, val_len, created, expires = row
                    print(f"   Domain: {host}")
                    print(f"   Encrypted: {enc_len > 0} ({enc_len} bytes)")
                    print(f"   Plain value: {val_len} bytes")
                    print(f"   Secure: {secure}, HttpOnly: {httponly}")
                    
                    # Convert WebKit/Chrome timestamp to readable format
                    if expires:
                        # Chrome timestamps are microseconds since 1601-01-01
                        expires_datetime = datetime(1601, 1, 1) + \
                                         datetime.resolution * expires
                        print(f"   Expires: {expires_datetime}")
        
        # Check encryption
        print("\n" + "=" * 80)
        print("ENCRYPTION ANALYSIS")
        print("=" * 80)
        
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN LENGTH(encrypted_value) > 0 THEN 1 ELSE 0 END) as encrypted_count,
                SUM(CASE WHEN LENGTH(value) > 0 THEN 1 ELSE 0 END) as plaintext_count,
                COUNT(*) as total
            FROM cookies
        """)
        
        enc_count, plain_count, total = cursor.fetchone()
        
        print(f"\n📊 Encryption statistics:")
        print(f"   🔒 Encrypted cookies: {enc_count} ({enc_count/total*100:.1f}%)")
        print(f"   📝 Plain text cookies: {plain_count} ({plain_count/total*100:.1f}%)")
        print(f"   📊 Total: {total}")
        
        # Sample encrypted value
        cursor.execute("""
            SELECT name, host_key, encrypted_value, LENGTH(encrypted_value) as len
            FROM cookies 
            WHERE LENGTH(encrypted_value) > 0 
            LIMIT 1
        """)
        
        sample = cursor.fetchone()
        if sample:
            name, host, enc_value, length = sample
            print(f"\n🔍 Sample encrypted cookie:")
            print(f"   Name: {name}")
            print(f"   Domain: {host}")
            print(f"   Encrypted value length: {length} bytes")
            print(f"   First 50 bytes (hex): {enc_value[:50].hex()}")
            
            # Check for Windows DPAPI prefix
            if enc_value[:3] == b'v10':
                print(f"   ⚠️  Encryption: Windows DPAPI (v10 prefix detected)")
                print(f"   ❌ NOT portable to Linux!")
            elif enc_value[:3] == b'v11':
                print(f"   ⚠️  Encryption: Chrome encryption v11")
            else:
                print(f"   Prefix: {enc_value[:10].hex()}")
        
        conn.close()
        
        print("\n" + "=" * 80)
        print("PORTABILITY ANALYSIS")
        print("=" * 80)
        
        print(f"""
🔍 Key Findings:

1. Cookie Storage:
   • Cookies stored in SQLite database
   • Two storage methods: encrypted_value OR value (plain text)
   • Most cookies are encrypted ({enc_count}/{total})

2. Encryption Method:
   • Windows: DPAPI (Data Protection API)
   • Linux: libsecret/keyring
   • Encryption is OS-specific!

3. Critical Google Cookies:
   • SID, SSID, APISID, SAPISID - Authentication tokens
   • __Secure-1PSID, __Secure-3PSID - Secure authentication
   • These are encrypted in the database

4. Portability:
   ❌ Encrypted cookies CANNOT be decrypted on different OS
   ❌ Windows DPAPI != Linux libsecret
   ❌ Simply copying Cookies file will NOT work

5. Alternative Approach:
   ✅ Extract decrypted cookie values on Windows
   ✅ Store as plain JSON
   ✅ Inject into Linux Chrome profile
   ✅ OR use tokens directly in API calls
        """)
        
    except Exception as e:
        print(f"\n❌ Error analyzing database: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Path to cookies database
    cookies_db = r"D:\Tokenade\browser_data\1\Default\Network\Cookies.sqlite"
    
    analyze_cookies_db(cookies_db)
