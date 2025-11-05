"""
Simple test script to verify your collected tokens work!
"""

import json
import os

def main():
    print("\n" + "=" * 60)
    print("TOKEN VERIFICATION TEST")
    print("=" * 60)
    
    tokens_dir = 'tokens'
    
    # Check if tokens directory exists
    if not os.path.exists(tokens_dir):
        print("\n❌ No tokens directory found!")
        print("   Run: python collect_all_cookies.py first")
        return
    
    # Check for all_tokens.json
    all_tokens_file = os.path.join(tokens_dir, 'all_tokens.json')
    
    if not os.path.exists(all_tokens_file):
        print("\n❌ No all_tokens.json found!")
        print("   Run: python collect_all_cookies.py first")
        return
    
    # Load all tokens
    with open(all_tokens_file, 'r') as f:
        tokens = json.load(f)
    
    if not tokens:
        print("\n❌ No tokens in file!")
        return
    
    print(f"\n✅ Found {len(tokens)} account(s) with tokens!\n")
    
    # Display each token
    for token_data in tokens:
        account_num = token_data.get('account_number', '?')
        email = token_data.get('email', 'Unknown')
        token = token_data.get('access_token', '')
        status = token_data.get('status', 'unknown')
        collected_at = token_data.get('collected_at', 'Unknown time')
        
        print(f"📋 Account {account_num}")
        print(f"   📧 Email: {email}")
        print(f"   🔑 Token: {token[:50]}..." if token else "   ❌ No token!")
        print(f"   📅 Collected: {collected_at}")
        print(f"   ✓ Status: {status}")
        print()
    
    # Check individual files
    print("\n📁 Individual token files:")
    for token_data in tokens:
        account_num = token_data.get('account_number', '?')
        file_path = os.path.join(tokens_dir, f'account_{account_num}.json')
        
        if os.path.exists(file_path):
            size = os.path.getsize(file_path)
            print(f"   ✓ account_{account_num}.json ({size:,} bytes)")
        else:
            print(f"   ❌ account_{account_num}.json (missing)")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE!")
    print("=" * 60)
    print("\n💡 Next step: Use these tokens in your Whisk API script")
    print(f"   Example: Load from '{all_tokens_file}'")
    print()

if __name__ == "__main__":
    main()
