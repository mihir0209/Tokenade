"""
Analyze the injected cookies database to see what might be wrong
"""

import sqlite3
import os

def analyze_db(db_path):
    """Analyze a cookies database"""
    
    print(f"\n📁 Analyzing: {db_path}")
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found!")
        return
    
    print(f"📊 Size: {os.path.getsize(db_path):,} bytes")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"\n📋 Tables: {', '.join(tables)}")
    
    # Check cookies table schema
    cursor.execute("PRAGMA table_info(cookies)")
    columns = cursor.fetchall()
    print(f"\n🔍 Cookies table columns ({len(columns)}):")
    for col in columns:
        col_id, col_name, col_type, not_null, default_val, pk = col
        print(f"   {col_name}: {col_type}")
    
    # Count cookies
    cursor.execute("SELECT COUNT(*) FROM cookies")
    count = cursor.fetchone()[0]
    print(f"\n📊 Total cookies: {count}")
    
    # Check encryption status
    cursor.execute("""
        SELECT 
            SUM(CASE WHEN LENGTH(encrypted_value) > 0 THEN 1 ELSE 0 END) as encrypted,
            SUM(CASE WHEN LENGTH(value) > 0 THEN 1 ELSE 0 END) as plain_text
        FROM cookies
    """)
    encrypted, plain = cursor.fetchone()
    print(f"   🔒 Encrypted: {encrypted}")
    print(f"   📝 Plain text: {plain}")
    
    # Sample cookies
    cursor.execute("""
        SELECT name, host_key, path, expires_utc, is_secure, is_httponly, 
               LENGTH(value), LENGTH(encrypted_value)
        FROM cookies 
        WHERE host_key LIKE '%google%'
        ORDER BY name
        LIMIT 10
    """)
    
    print(f"\n🔍 Sample Google cookies:")
    for row in cursor.fetchall():
        name, host, path, expires, secure, httponly, val_len, enc_len = row
        print(f"   {name}")
        print(f"      Host: {host}, Path: {path}")
        print(f"      Expires: {expires}, Secure: {secure}, HttpOnly: {httponly}")
        print(f"      Value len: {val_len}B, Encrypted len: {enc_len}B")
    
    # Check meta table
    if 'meta' in tables:
        cursor.execute("SELECT key, value FROM meta")
        print(f"\n📋 Meta table:")
        for key, value in cursor.fetchall():
            print(f"   {key} = {value}")
    
    conn.close()


# Analyze injected database
base_dir = os.getcwd()
injected_db = os.path.join(base_dir, 'browser_data', '1', 'Default', 'Network', 'Cookies')

print("=" * 80)
print("ANALYZING INJECTED COOKIES DATABASE")
print("=" * 80)

analyze_db(injected_db)

print("\n\n" + "=" * 80)
print("POTENTIAL ISSUES TO CHECK")
print("=" * 80)

print("""
1. ❓ Are cookies encrypted or plain text?
   - Linux Chrome expects encrypted_value to be EMPTY
   - Linux Chrome should read from 'value' column

2. ❓ Is the schema complete?
   - Missing columns could cause Chrome to ignore the database

3. ❓ Are expiration times valid?
   - Expired cookies won't be loaded

4. ❓ Is the meta table version correct?
   - Wrong version might cause Chrome to reject the database
""")
