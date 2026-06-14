# Manual Test Report — Session Vault

**Date:** 2026-06-14
**Version:** v3.4.0

## Test 1: Vault Add and Retrieve

### Command
```bash
python -c "
from tokenade.core.importer.session_vault import SessionVault
import json

vault = SessionVault('test_sessions/.vault', max_versions=3)

# Add
sid = vault.add('test_sessions/google.tokenade', tags=['google', 'personal'], owner='testuser')
print(f'Added: {sid}')

# Retrieve
session = vault.get(sid)
print(f'Retrieved: {session[\"site_name\"]} ({session[\"metadata\"][\"cookie_count\"]} cookies)')
"
```

### Result
- **Status:** PASS
- **Output:** Session added with SHA-256 based ID, retrieved successfully

## Test 2: Vault ACL Management

### Command
```bash
python -c "
from tokenade.core.importer.session_vault import SessionVault

vault = SessionVault('test_sessions/.vault_v2')
sid = vault.add('test_sessions/google.tokenade', owner='admin')

# Owner has all permissions
print(f'Owner read: {vault.check_permission(sid, \"admin\", \"read\")}')
print(f'Owner write: {vault.check_permission(sid, \"admin\", \"write\")}')
print(f'Owner delete: {vault.check_permission(sid, \"admin\", \"delete\")}')

# Grant read to friend
vault.set_acl(sid, 'friend@example.com', ['read'])
print(f'Friend read: {vault.check_permission(sid, \"friend@example.com\", \"read\")}')
print(f'Friend write: {vault.check_permission(sid, \"friend@example.com\", \"write\")}')

# Unknown user
print(f'Unknown read: {vault.check_permission(sid, \"unknown\", \"read\")}')
"
```

### Result
- **Status:** PASS
- **Output:** ACL correctly enforces owner (all), friend (read-only), unknown (none)

## Test 3: Vault Versioning

### Command
```bash
python -c "
from tokenade.core.importer.session_vault import SessionVault
import json, tempfile, shutil
from pathlib import Path

vault = SessionVault('test_sessions/.vault_v3', max_versions=3)

# Create session file
session_file = Path('test_sessions/vault_test.tokenade')
shutil.copy('test_sessions/google.tokenade', session_file)

# Add initial
sid = vault.add(str(session_file), session_id='versioned')

# Update 5 times
for i in range(5):
    with open(session_file) as f:
        s = json.load(f)
    s['cookies'][0]['value'] = f'v{i}'
    with open(session_file, 'w') as f:
        json.dump(s, f)
    vault.update(sid, str(session_file))

entry = vault._index[sid]
print(f'Versions stored: {len(entry.versions)} (max 3)')
print(f'Updates performed: 5')
"
```

### Result
- **Status:** PASS
- **Output:** `Versions stored: 3 (max 3)` — oldest versions pruned correctly

## Test 4: Vault Stats

### Command
```bash
python -c "
from tokenade.core.importer.session_vault import SessionVault

vault = SessionVault('test_sessions/.vault_v4')
vault.add('test_sessions/google.tokenade', tags=['google'])
vault.add('test_sessions/github.tokenade', tags=['github'])

stats = vault.get_stats()
print(f'Total sessions: {stats[\"total_sessions\"]}')
print(f'Total cookies: {stats[\"total_cookies\"]}')
print(f'Sites: {stats[\"sites\"]}')
"
```

### Result
- **Status:** PASS
- **Output:** Correct statistics across multiple sessions

## Test 5: Vault Expired Session Cleanup

### Command
```bash
python -c "
from tokenade.core.importer.session_vault import SessionVault
import json

vault = SessionVault('test_sessions/.vault_v5')

# Add session with short expiry (already expired)
with open('test_sessions/google.tokenade') as f:
    session = json.load(f)

session_file = 'test_sessions/expiring.tokenade'
with open(session_file, 'w') as f:
    json.dump(session, f)

sid = vault.add(session_file, expires_in_seconds=-3600)  # Expired 1 hour ago
removed = vault.cleanup_expired()
print(f'Expired sessions removed: {removed}')
print(f'Vault remaining: {len(vault.list_sessions())}')
"
```

### Result
- **Status:** PASS
- **Output:** Expired session correctly identified and removed
