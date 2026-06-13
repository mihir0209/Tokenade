# Tokenade Security Considerations

## Overview

Tokenade is a browser session portability tool. This document describes its security model, known limitations, and best practices.

## Threat Model

Tokenade is designed for **personal use on trusted machines**. It is NOT designed to:
- Protect against a compromised operating system
- Provide end-to-end encrypted session transfer over untrusted networks
- Be used as a production authentication system

## Cookie Encryption

### Storage Format
- **v2 format** (current): AES-256-GCM — authentication via GCM tag
- **v1 format** (deprecated): AES-256-GCM + redundant HMAC-SHA256 (still decrypted for backward compatibility)

### Key Derivation
- PBKDF2 with SHA-256, 600,000 iterations
- Random 16-byte salt per encryption
- Random 12-byte nonce per encryption

### File Permissions
- All encrypted/decrypted files are written with mode `0600` (owner read/write only)

## SSRF Protection

The proxy blocks outbound requests to:
- Private IP ranges: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
- Link-local: `169.254.0.0/16`
- Loopback: `127.0.0.0/8`, `::1`
- IPv6 private: `fc00::/7`
- Cloud metadata endpoints: `metadata.google.internal`

## Cookie Extraction Security

### What Gets Exported
- Cookie names, values, domains, paths, expiry times
- localStorage key-value pairs (when explicitly requested)
- Browser fingerprint data (user-agent, platform, etc.)

### What Does NOT Get Exported
- Master passwords or encryption keys
- Browser history or bookmarks
- Saved passwords (autofill)

## Credential Storage

### Default: System Keyring
- Windows: Credential Manager
- macOS: Keychain
- Linux: Secret Service (GNOME Keyring, KWallet)

### Fallback: AES-Encrypted File
- When keyring is unavailable, passwords are stored in an encrypted `accounts.json`
- Protected by a user-supplied master password

### Plaintext: Deprecated
- The old `accounts.json` plaintext format is no longer created
- Existing plaintext files trigger a warning

## Proxy Security

### Cookie Isolation
- Each session gets its own Playwright browser context
- Cookies from different sessions never mix

### XSS Prevention
- All user-controlled values in HTML responses are escaped with `html.escape()`

### Error Messages
- Generic error messages returned to clients
- Detailed errors logged server-side only

## TLS Fingerprint Matching

When `--fingerprint` is enabled:
- All browser requests intercepted via `page.route()`
- Forwarded through `curl-cffi` with donor's TLS fingerprint
- **Warning**: `cf_clearance` cookies are TLS-fingerprint-bound. Exporting from one browser and using with a different TLS profile may break Cloudflare-protected sites.

### Default Mode (Native Browsing)
- Cookies injected into Playwright context
- Browser loads pages with its own TLS fingerprint
- More compatible, fewer anti-bot detection issues

## Known Limitations

1. **No end-to-end encryption for transfer** — .tokenade files are encrypted at rest but transmitted as regular files
2. **Session expiry** — Cookies expire; sessions need periodic refresh
3. **IP binding** — Some services (Google, banking) bind sessions to IP address
4. **Device fingerprinting** — Some services detect device changes and invalidate sessions
5. **Rate limiting** — Bulk session operations may trigger rate limits
6. **macOS Chrome** — Keychain access may require user permission the first time
7. **Firefox on Linux** — Falls back to `secretstorage` (requires D-Bus); may not work in headless environments

## Best Practices

1. **Use `--fingerprint` sparingly** — Native browsing mode is more compatible
2. **Encrypt .tokenade files** — Use `tokenade encrypt` before transferring
3. **Delete after use** — Remove .tokenade files after injecting sessions
4. **Use fresh sessions** — Export cookies shortly before use; they expire
5. **Check `tokenade health`** — Verify session validity before relying on it
6. **Don't commit .tokenade files** — Add `*.tokenade` to `.gitignore`
