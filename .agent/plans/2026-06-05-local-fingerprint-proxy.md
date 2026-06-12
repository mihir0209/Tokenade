# Local Fingerprint Proxy Server — Core Architecture

**Date:** 2026-06-05
**Status:** Planned
**Priority:** Critical (this is the original vision)
**Blocks:** Real-world anti-bot bypass for complex sites

## The Vision

Instead of injecting cookies into a target browser and hoping the fingerprint matches, we run a **local proxy server** that:

1. Loads a `.tokenade` file (donor fingerprint + cookies + TLS profile)
2. Listens on `127.0.0.1:<port>`
3. When the receiver browser makes ANY request through this proxy:
   - TLS handshake impersonates the **donor** browser (JA3/JA4 match)
   - HTTP headers match the **donor** browser's ordering and values
   - Cookies from the **donor** session are injected automatically
4. The receiver browser never touches the remote server directly — everything goes through the proxy

**Result:** The remote server sees requests that are indistinguishable from the donor device.

## Why This Works (vs. direct cookie injection)

| Approach | TLS Fingerprint | HTTP Headers | Cookies | Anti-Bot Bypass |
|----------|----------------|--------------|---------|-----------------|
| Direct injection | Receiver's (wrong) | Receiver's (wrong) | Donor's | ❌ Fails on Cloudflare |
| **Proxy server** | **Donor's (exact)** | **Donor's (exact)** | **Donor's** | **✅ Passes** |

## Architecture

```
┌──────────────────────┐     HTTP/S      ┌─────────────────────────┐
│  Receiver Browser    │ ──────────────> │  Local Proxy Server     │
│  (any browser)       │ <────────────── │  127.0.0.1:9222         │
│                      │                 │                         │
│  Config:             │                 │  .tokenade file loaded: │
│  HTTP_PROXY=         │                 │  ├─ cookies (donor)     │
│    127.0.0.1:9222    │                 │  ├─ fingerprint (donor) │
│  HTTPS_PROXY=        │                 │  ├─ tls (donor JA3)     │
│    127.0.0.1:9222    │                 │  └─ header order (donor)│
└──────────────────────┘                 └────────────┬────────────┘
                                                      │
                                                      │ curl-cffi
                                                      │ (JA3 matched)
                                                      ▼
                                             ┌─────────────────┐
                                             │  Remote Server   │
                                             │  (chatgpt.com)   │
                                             │  sees: donor     │
                                             │  device exactly  │
                                             └─────────────────┘
```

## Implementation Plan

### Phase 1: Enhance .tokenade Format (Day 1)

Add TLS profile fields to the session package so the proxy knows which impersonation to use.

**File:** `tokenade/core/importer/session_packager.py`

```json
{
  "version": "2.0",
  "cookies": [...],
  "fingerprint": {...},
  "tls_profile": {
    "browser": "chrome",
    "version": "120",
    "impersonate": "chrome120",
    "http_version": "2"
  },
  "header_order": ["authority", "method", "path", "scheme", "..."],
  "proxy_config": {
    "port": 9222,
    "auth_required": false
  }
}
```

### Phase 2: Fix Header Ordering (Day 1)

The constants `CHROME_HEADERS`/`FIREFOX_HEADERS` exist in `engine.py:70-99` but are never applied. Fix `FingerprintMatcher.get_headers()` to actually sort outgoing headers.

**File:** `tokenade/core/runtime/engine.py:114-169`

### Phase 3: Fix Cookie Expiry in CookieJar (Day 1)

Add `expires` checking to `CookieJar.get_for_request()`. Currently expired cookies are still served.

**File:** `tokenade/core/runtime/engine.py:238-265`

### Phase 4: Build the Proxy Server (Days 2-5)

**New file:** `tokenade/core/proxy/server.py`

```python
class TokenadeProxy:
    """
    Local HTTP/HTTPS proxy server.
    
    Usage:
        proxy = TokenadeProxy.from_session("chatgpt.tokenade", port=9222)
        proxy.start()  # Listens on 127.0.0.1:9222
        
        # Configure browser:
        # HTTP_PROXY=http://127.0.0.1:9222
        # HTTPS_PROXY=http://127.0.0.1:9222
    """
    
    def __init__(self, session_package, port=9222):
        self.cookie_jar = CookieJar()
        self.cookie_jar.add_cookies(session_package['cookies'])
        self.fingerprint = FingerprintMatcher(session_package.get('fingerprint'))
        self.tls_matcher = create_tls_matcher(
            browser=session_package['tls_profile']['browser'],
            version=session_package['tls_profile']['version']
        )
        self.port = port
    
    def handle_request(self, method, url, headers, body):
        """Intercept request, apply donor fingerprint, forward."""
        # 1. Replace headers with donor-matched headers
        donor_headers = self.fingerprint.get_headers(url)
        # 2. Inject donor cookies
        cookies = self.cookie_jar.get_for_request(url)
        donor_headers['cookie'] = cookies
        # 3. Forward via TLS-matched connection
        response = self.tls_matcher.request(method, url, donor_headers, body)
        # 4. Capture Set-Cookie from response
        # 5. Return response to client
```

**Key design decisions:**

1. **Proxy library:** Use `aiohttp` for the proxy server (async, handles CONNECT for HTTPS)
2. **TLS forwarding:** For HTTPS CONNECT tunnels, use `curl-cffi` with impersonation for the upstream connection
3. **Certificate:** For MITM mode (optional), generate a local CA and re-sign responses. For passthrough mode (default), just tunnel with matching TLS

### Phase 5: CLI Integration (Day 5)

```bash
# Start proxy from session file
tokenade proxy --session chatgpt.tokenade --port 9222

# Start with auto-refresh
tokenade proxy --session chatgpt.tokenade --port 9222 --auto-refresh --source-browser firefox

# Multi-site proxy (multiple .tokenade files, route by domain)
tokenade proxy --session-dir ./sessions/ --port 9222
```

### Phase 6: Browser Launch Helper (Day 6)

```bash
# Launch browser pre-configured to use proxy
tokenade proxy --session chatgpt.tokenade --launch-brave

# Launch with specific profile
tokenade proxy --session chatgpt.tokenade --launch-chrome --profile "Work"
```

This would:
1. Start the proxy
2. Launch the browser with `--proxy-server=127.0.0.1:9222`
3. Optionally inject stealth scripts for JS-level fingerprint matching

## Files

### New Files
- `tokenade/core/proxy/__init__.py`
- `tokenade/core/proxy/server.py` — Main proxy server (aiohttp-based)
- `tokenade/core/proxy/handler.py` — Request/response interception logic
- `tokenade/core/proxy/tunnel.py` — HTTPS CONNECT tunnel handling
- `tokenade/core/proxy/cert.py` — Optional MITM certificate generation
- `tokenade/tests/test_proxy.py` — Tests

### Modified Files
- `tokenade/core/importer/session_packager.py` — Add `tls_profile`, `header_order` to .tokenade format
- `tokenade/core/runtime/engine.py` — Fix header ordering, cookie expiry
- `tokenade/core/runtime/tls_matcher.py` — Add proxy support, HTTP/2 config
- `tokenade/cli.py` — Add `proxy` command
- `requirements.txt` — Add `aiohttp` as dependency

## Reusable Components (Already Implemented)

| Component | File | Reuse |
|-----------|------|-------|
| `CookieJar` | `engine.py:210-277` | Direct — cookie storage + matching |
| `FingerprintMatcher` | `engine.py:61-207` | Direct — header generation (needs ordering fix) |
| `TLSMatcher` | `tls_matcher.py:67-239` | Direct — JA3-matched requests |
| `SessionPackager.load()` | `session_packager.py:198-216` | Direct — reads .tokenade file |
| `create_engine_from_session()` | `engine.py:609-629` | Direct — creates configured engine |
| `BrowserFingerprint` | `manager.py:19-97` | Direct — donor identity |
| `RuntimeConfig` | `engine.py:39-58` | Direct — proxy configuration |

## What Needs Building

| Gap | Effort | Priority |
|-----|--------|----------|
| HTTP proxy server (aiohttp) | 4 days | Critical |
| HTTPS CONNECT tunnel | 2 days | Critical |
| Header ordering activation | 0.5 day | High |
| Cookie expiry in CookieJar | 0.5 day | High |
| TLS fields in .tokenade | 0.5 day | High |
| MITM certificate generation | 1 day | Medium |
| Multi-site domain routing | 1 day | Medium |
| Auto-refresh integration | 1 day | Medium |
| Browser launch helper | 1 day | Low |

## Success Criteria

- [ ] Proxy starts on specified port
- [ ] TLS handshake matches donor browser (verify at ja3er.com)
- [ ] HTTP headers match donor browser order and values
- [ ] Cookies injected from .tokenade file
- [ ] Cloudflare challenge pages bypassed
- [ ] Works with Chrome, Brave, Firefox, Edge
- [ ] Multi-site routing works (multiple .tokenade files)
- [ ] All existing tests pass
- [ ] New proxy tests pass

## Estimated Effort

**8-10 days** for production-ready local fingerprint proxy

## Dependencies

- `aiohttp` — Async HTTP server (for proxy)
- `curl-cffi` — TLS fingerprint matching (already optional)
- `pyOpenSSL` — Optional MITM certificate generation

## Verification Plan

1. Start proxy with ChatGPT .tokenade file
2. Configure curl to use proxy: `curl --proxy http://127.0.0.1:9222 https://chatgpt.com`
3. Verify TLS fingerprint at ja3er.com matches donor
4. Verify ChatGPT shows logged-in state
5. Test with Cloudflare-protected sites
