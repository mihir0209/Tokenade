"""
Quick Token Collector - Read tokens from browser_data

This script simply reads the token_info.json files saved during setup.
No browser automation needed!
"""

import json
import os
from datetime import datetime

# Directories
BASE_DIR = os.path.dirname(__file__)
BROWSER_DATA_BASE = os.path.join(BASE_DIR, 'browser_data')
TOKENS_OUTPUT_DIR = os.path.join(BASE_DIR, 'tokens')

def collect_tokens():
    """Collect all tokens from browser_data directories"""
    
    print("\n" + "=" * 80)
    print("QUICK TOKEN COLLECTOR - Reading saved tokens")
    print("=" * 80)
    
    # Create tokens directory
    os.makedirs(TOKENS_OUTPUT_DIR, exist_ok=True)
    
    # Find all account directories
    if not os.path.exists(BROWSER_DATA_BASE):
        print(f"\n❌ No browser data found!")
        return
    
    account_dirs = [d for d in os.listdir(BROWSER_DATA_BASE) if d.isdigit()]
    account_numbers = sorted([int(d) for d in account_dirs])
    
    if not account_numbers:
        print(f"\n❌ No accounts found!")
        return
    
    print(f"\n📋 Found {len(account_numbers)} account(s): {account_numbers}")
    
    all_tokens = []
    success_count = 0
    
    for account_num in account_numbers:
        token_file = os.path.join(BROWSER_DATA_BASE, str(account_num), 'token_info.json')
        
        if os.path.exists(token_file):
            try:
                with open(token_file, 'r') as f:
                    token_data = json.load(f)
                
                email = token_data.get('email', 'Unknown')
                token = token_data.get('access_token', '')
                
                print(f"\n✅ Account {account_num}: {email}")
                print(f"   🔑 Token: {token[:60]}...")
                print(f"   📅 Saved: {token_data.get('saved_at', 'Unknown')}")
                print(f"   ⏰ Expires: {token_data.get('expires', 'Unknown')}")
                
                # Save to tokens directory
                output_file = os.path.join(TOKENS_OUTPUT_DIR, f'account_{account_num}.json')
                with open(output_file, 'w') as f:
                    json.dump(token_data, f, indent=2)
                
                all_tokens.append(token_data)
                success_count += 1
                
            except Exception as e:
                print(f"\n❌ Account {account_num}: Error reading token - {e}")
        else:
            print(f"\n⚠ Account {account_num}: No token_info.json found")
    
    # Save all tokens
    if all_tokens:
        all_tokens_file = os.path.join(TOKENS_OUTPUT_DIR, 'all_tokens.json')
        with open(all_tokens_file, 'w') as f:
            json.dump(all_tokens, f, indent=2)
        
        print("\n" + "=" * 80)
        print(f"✅ Successfully collected: {success_count}/{len(account_numbers)} tokens")
        print(f"\n📁 Tokens saved in: {TOKENS_OUTPUT_DIR}")
        print("=" * 80 + "\n")
    else:
        print("\n❌ No tokens collected!")


if __name__ == "__main__":
    collect_tokens()
