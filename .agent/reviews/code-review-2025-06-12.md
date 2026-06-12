# Tokenade Code Review — 2025-06-12

## Scope
Full codebase review: proxy architecture, importer/runtime, CLI, crypto, tests.

---

## CRITICAL (Fix Immediately)

### C1 — XSS in GUI HTML (cdp_proxy.py, server.py)
User-controlled values (`site_name`, `browser_name`, `platform`, `current_url`) are interpolated directly into HTML f-strings with zero escaping. A `.tokenade` file with `<script>alert(1)</script>` in `site_name` executes JS in the user's browser.

**Fix:** Use `html.escape()` on all values interpolated into HTML responses.

### C2 — SSRF — arbitrary outbound requests (cdp_proxy.py, server.py)
The proxy forwards requests to ANY URL specified by the client via `/browse` POST or reverse proxy catch-all. No allowlist/blocklist. An attacker on the same machine can make the proxy request internal services (`169.254.169.254`, `localhost:xxxx`, RFC 1918 ranges) with donor cookies.

**Fix:** Add URL allowlist/blocklist. Block private IP ranges, link-local, and metadata endpoints.

### C3 — Dead code masking bugs in server.py
`server.py:527-544` has a duplicated try/except block that is unreachable. The live code path may be incomplete compared to the dead code.

**Fix:** Remove dead code, verify live path is correct.

### C4 — Plaintext password in accounts.json (cli.py)
`cmd_setup` writes password in plaintext to `accounts.json`. The `CredentialManager` with keyring support exists but is never used.

**Fix:** Use `CredentialManager` instead of plaintext storage. Add `chmod 0600`.

### C5 — Passwords accepted via CLI flag (cli.py)
`--password` flags on encrypt/decrypt/rekey commands expose passwords in shell history and process listing.

**Fix:** Remove `--password` flags. Use `getpass.getpass()` or env vars only.

### C6 — Double-cookie sending in TLS path (engine.py)
`RuntimeEngine.request` passes cookies both in the header AND as `cookies=` parameter to curl-cffi. This doubles cookie values, causing auth failures.

**Fix:** Remove the `cookies=` parameter from the `request()` call, keep only the header.

### C7 — Hardcoded "peanuts" fallback key (cookie_crypto.py)
Linux Chrome cookie decryption falls back to `b"peanuts"` with 1-iteration PBKDF2. This is effectively no encryption.

**Fix:** Document the limitation. Warn users when using on Linux that cookies are weakly encrypted.

### C8 — macOS mapped to Linux crypto (cookie_crypto.py)
`CookieCryptoFactory` maps `posix` to `LinuxCookieCrypto` for both Linux and macOS. macOS uses Keychain, not libsecret. Decryption will silently fail.

**Fix:** Add `MacCookieCrypto` or fail explicitly on unsupported platforms.

---

## HIGH (Fix Before Release)

### H1 — Pages never cleaned up — resource leak (cdp_proxy.py)
Every `/browse` POST creates a Playwright page stored in `self._pages`. Pages are never removed or closed. An attacker can POST in a loop to exhaust Chromium renderer processes.

**Fix:** Add page lifecycle management with TTL, max page count, and cleanup on tab close.

### H2 — Cookie values logged to stdout (cdp_proxy.py)
Cookie strings (auth tokens) are logged at INFO level for chatgpt.com URLs. Auth tokens in logs are a security antipattern.

**Fix:** Remove cookie value logging. Log only cookie count.

### H3 — Information disclosure in error messages (cdp_proxy.py, server.py)
`f"Error: {e}"` returned directly to clients, leaking Python exception internals.

**Fix:** Return generic error messages. Log details server-side only.

### H4 — `_http_session` creation race (cdp_proxy.py, server.py)
Multiple concurrent requests can all create new `aiohttp.ClientSession` simultaneously, leaking connections.

**Fix:** Use an `asyncio.Lock` for session creation.

### H5 — Connection leak in extract_chrome (cookie_extractor.py)
`conn.close()` is in the `try` block, not `finally`. If the query throws, the connection leaks.

**Fix:** Move `conn.close()` to `finally` block.

### H6 — Hostname leak in session packages (session_packager.py)
`socket.gethostname()` is embedded in `.tokenade` packages. If shared, this leaks the source machine identity.

**Fix:** Add option to suppress hostname. Make `source_device` opt-in.

### H7 — Linux DB not copied before extraction (cookie_crypto.py)
`LinuxCookieCrypto` connects directly to the live cookies.sqlite. If Chrome is running, causes `SQLITE_BUSY`.

**Fix:** Copy the DB before reading (like `WindowsCookieCrypto` does).

### H8 — No file permission hardening (cli.py, encryptor.py)
Encrypted files and `accounts.json` are written with default umask. Should be `0o600`.

**Fix:** `os.chmod(path, 0o600)` after writing sensitive files.

### H9 — Redundant HMAC over AES-GCM (encryptor.py)
AES-GCM already provides authentication. The additional HMAC is redundant and increases attack surface.

**Fix:** Remove HMAC. Rely on GCM tag.

### H10 — Key material not zeroed (encryptor.py)
Derived keys remain in memory after use with no attempt to clear.

**Fix:** Overwrite key bytes with zeros after use where possible.

### H11 — No Argon2id KDF (encryptor.py)
PBKDF2 with 600k iterations is acceptable but not state-of-the-art. Argon2id provides memory-hardness.

**Fix:** Migrate to Argon2id (with PBKDF2 fallback for compatibility).

### H12 — `_copy_db` leaves WAL/SHM temp files (cookie_extractor.py)
If WAL copy fails, orphaned temp files with plaintext cookie data remain on disk.

**Fix:** Clean up all temp files in `finally` block.

---

## MEDIUM

### M1 — CSRF on `/browse` POST (cdp_proxy.py)
No CSRF token on the browse form. Any page the user visits can POST to `http://127.0.0.1:9222/browse`.

### M2 — `localStorage` injection uses insufficient escaping (cdp_proxy.py)
Only `\` and `'` are escaped. A value containing `</script>` could theoretically break contexts.

### M3 — Regex-based HTML rewriting is fragile (server.py)
Using `re.sub` to parse and rewrite HTML is fundamentally unreliable. Malformed HTML, CDATA sections, JS string literals all cause incorrect rewrites.

### M4 — Manual redirect following loses cookies (server.py)
`_forward_request` manually follows redirects but doesn't capture `Set-Cookie` from intermediate responses.

### M5 — `_target_url`/`_proxy_active` race (server.py)
Shared mutable state without synchronization. A second POST changes the target while in-flight requests use the old one.

### M6 — `ssl=False` on aiohttp connector (server.py)
SSL verification completely disabled on fallback path. Vulnerable to MITM.

### M7 — Bidirectional localStorage origin filter (local_storage_extractor.py)
`origin_filter not in origin_from_dir and origin_from_dir not in origin_filter` — a filter of `"a"` matches everything.

### M8 — Duplicated domain-filtering logic (cli.py)
Nearly identical cookie-filtering blocks in `cmd_export` violate DRY.

### M9 — Broad `except Exception` swallowing (cli.py)
Nearly every command catches `Exception` broadly, losing stack traces and hiding bugs.

### M10 — `FingerprintMatcher` hardcodes `sec-fetch-site: "cross-site"` (engine.py)
Same-origin navigations should have `sec-fetch-site: "none"` or `"same-origin"`. This is a fingerprinting signal.

### M11 — Duplicate import of `urlparse` inside hot path (cdp_proxy.py)
`from urllib.parse import urlparse as _urlparse` is imported inside `_handle_route` which runs on every intercepted request.

### M12 — Anonymous `type()` response objects (cdp_proxy.py, server.py)
`type('Response', (), {...})()` used instead of proper dataclass/namedtuple. Fragile, no type checking.

### M13 — `infer_auth_status` false positives (session_packager.py)
Any 2+ cookies with `secure + httpOnly` flags count as "logged in". Analytics cookies like `_ga` have these flags.

### M14 — `_detect_tls_profile` runtime import (session_packager.py)
`from tokenade.core.runtime.tls_matcher import IMPERSONATE_TARGETS` inside method body. Fragile circular-import risk.

---

## LOW

### L1 — Unused imports
`Tuple` (cdp_proxy.py), `ssl` (server.py), `urljoin` (server.py), `re` (cookie_extractor.py).

### L2 — Dead code in cdp_proxy.py
`_strip_duplicate_headers`, `_LenientProtocol`, `_LenientServerFactory` exist for stale SW handling but CDP proxy doesn't use SWs.

### L3 — `_get_site_url` assumes `.com` TLD (server.py)
`f"https://www.{site_name}.com"` will produce wrong URLs for non-US sites.

### L4 — No `--version` flag on CLI

### L5 — `HandlerRegistry._handlers` is mutable class-level dict (base.py)
Shared across test runs, causes test pollution.

### L6 — `validate_format` doesn't validate version string format

### L7 — `CHROME_UA_BRANDS` dict missing versions 110, 116, 119

---

## Test Coverage Gaps

| Area | Status |
|------|--------|
| TokenadeEncryptor | Zero unit tests |
| cmd_encrypt/decrypt/rekey | No tests |
| cmd_proxy | No tests |
| cmd_export/load | No tests (most-used commands!) |
| macOS crypto path | Wrong + untested |
| WindowsCookieCrypto | No tests |
| CLI end-to-end | No integration tests |
| SSRF protection | No tests |

**Total:** 361 tests pass, 1 skipped. Good coverage on core logic but critical gaps in crypto and CLI commands.
