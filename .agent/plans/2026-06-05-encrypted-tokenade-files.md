# Encrypted .tokenade Files

**Date:** 2026-06-05
**Status:** Planned
**Priority:** High
**Security:** Critical

## Problem

`.tokenade` files contain sensitive session cookies in plaintext. If intercepted, attackers gain full account access.

## Solution

AES-256-GCM encryption for all `.tokenade` files with password-based key derivation.

## Implementation Plan

### Phase 1: Encryption Core
```python
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

class TokenadeEncryptor:
    def encrypt(self, data: bytes, password: str) -> bytes:
        """Encrypt with PBKDF2 + AES-256-GCM."""
    
    def decrypt(self, encrypted: bytes, password: str) -> bytes:
        """Decrypt and verify integrity."""
```

### Phase 2: File Format
```
┌─────────────────────────────────────────────────────┐
│  TOKENADE_ENCRYPTED_v1                             │
├─────────────────────────────────────────────────────┤
│  Salt (16 bytes)                                   │
│  Nonce (12 bytes)                                  │
│  Encrypted Data                                    │
│  HMAC-SHA256 (32 bytes)                            │
└─────────────────────────────────────────────────────┘
```

### Phase 3: CLI Integration
```bash
# Export with encryption
tokenade export --browser firefox --site chatgpt --encrypt --password "my-secret"

# Load with decryption
tokenade load chatgpt.tokenade --decrypt --password "my-secret"

# Change password
tokenade rekey chatgpt.tokenade --old-password "old" --new-password "new"

# Generate password from file
tokenade export --browser firefox --site chatgpt --encrypt --key-file ~/.ssh/id_rsa
```

### Phase 4: Key Management
```bash
# Store password in keyring
tokenade config set-keyring --site chatgpt --password "secret"

# Auto-load from keyring
tokenade load chatgpt.tokenade --decrypt --keyring

# Export keyring backup
tokenade config export-keyring --output keyring-backup.json
```

## Files

### New Files
- `tokenade/core/crypto/encryptor.py` - AES-256-GCM encryption
- `tokenade/core/crypto/keyring.py` - Keyring integration
- `tokenade/core/crypto/kdf.py` - Key derivation
- `tokenade/tests/test_encryption.py` - Tests

### Modified Files
- `tokenade/core/importer/exporter.py` - Add encryption support
- `tokenade/core/importer/session_loader.py` - Add decryption support
- `tokenade/cli.py` - Add --encrypt, --decrypt, --keyring flags

## Estimated Effort

4 days
