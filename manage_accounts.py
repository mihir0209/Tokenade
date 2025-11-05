"""
Account Manager - View, Add, Remove accounts

Manage your multi-account setup
"""

import json
import os
import shutil

ACCOUNTS_FILE = "accounts.json"
BROWSER_DATA_BASE = "browser_data"


def load_accounts():
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, 'r') as f:
            return json.load(f)
    return []


def save_accounts(accounts):
    with open(ACCOUNTS_FILE, 'w') as f:
        json.dump(accounts, f, indent=2)


def list_accounts():
    accounts = load_accounts()
    
    if not accounts:
        print("\n📋 No accounts configured yet.")
        return
    
    print(f"\n📋 Configured Accounts ({len(accounts)} total):")
    print("=" * 80)
    
    for acc in accounts:
        print(f"   #{acc['number']}: {acc['email']}")
        print(f"      Session: {acc['session_dir']}")
        
        # Check if session exists
        if os.path.exists(acc['session_dir']):
            print(f"      Status: ✓ Session exists")
        else:
            print(f"      Status: ⚠ Session missing")
        print()


def remove_account():
    accounts = load_accounts()
    
    if not accounts:
        print("\n❌ No accounts to remove.")
        return
    
    list_accounts()
    
    try:
        account_num = int(input("\nEnter account number to remove: ").strip())
    except ValueError:
        print("❌ Invalid number")
        return
    
    # Find account
    account = None
    account_index = None
    
    for i, acc in enumerate(accounts):
        if acc['number'] == account_num:
            account = acc
            account_index = i
            break
    
    if not account:
        print(f"❌ Account #{account_num} not found")
        return
    
    # Confirm
    print(f"\n⚠ Remove account #{account_num}: {account['email']}?")
    confirm = input("This will delete the session data. (yes/no): ").strip().lower()
    
    if confirm not in ['yes', 'y']:
        print("❌ Cancelled")
        return
    
    # Remove session directory
    if os.path.exists(account['session_dir']):
        shutil.rmtree(account['session_dir'])
        print(f"✓ Deleted session: {account['session_dir']}")
    
    # Remove from list
    accounts.pop(account_index)
    save_accounts(accounts)
    
    print(f"✅ Removed account #{account_num}: {account['email']}")


def clear_all_sessions():
    print("\n⚠ WARNING: This will delete ALL saved sessions!")
    confirm = input("Continue? (yes/no): ").strip().lower()
    
    if confirm not in ['yes', 'y']:
        print("❌ Cancelled")
        return
    
    if os.path.exists(BROWSER_DATA_BASE):
        shutil.rmtree(BROWSER_DATA_BASE)
        print(f"✅ Deleted all sessions: {BROWSER_DATA_BASE}/")
    else:
        print("✓ No sessions to delete")


def main():
    while True:
        print("\n" + "=" * 80)
        print("ACCOUNT MANAGER")
        print("=" * 80)
        print("\n1. List accounts")
        print("2. Remove an account")
        print("3. Clear all sessions")
        print("4. Exit")
        
        choice = input("\nSelect option (1-4): ").strip()
        
        if choice == '1':
            list_accounts()
        elif choice == '2':
            remove_account()
        elif choice == '3':
            clear_all_sessions()
        elif choice == '4':
            print("\n👋 Goodbye!")
            break
        else:
            print("❌ Invalid option")


if __name__ == "__main__":
    main()
