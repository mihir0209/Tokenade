# Runtime Engine Enhancement: JA3 Fingerprint Matching

**Date:** 2026-06-01
**Status:** Planned
**Priority:** High

## Overview

The current RuntimeEngine matches HTTP headers but not TLS fingerprints.
This plan adds JA3 fingerprint matching for complete browser impersonation
without running a full browser.

## Current Limitation

```python
# Current: Headers only
headers = {
    "user-agent": "Mozilla/5.0...",
    "sec-ch-ua": "...",
    # TLS fingerprint is still default Python/requests
}

# Problem: Server sees JA3 fingerprint mismatch
# Python requests JA3 != Chrome JA3
```

## Solution: curl-impersonate Integration

```python
from curl_cffi import requests as curl_requests

# Use curl-impersonate with Chrome JA3
response = curl_requests.get(
    url,
    impersonate="chrome120",  # Matches Chrome's JA3 exactly
    headers=matched_headers,
    cookies=cookies,
)
```

## Implementation Plan

1. **Add curl-cffi dependency** (optional extra: `pip install tokenade[runtime]`)
2. **Create TLSFingerprintMatcher class**
   - Map browser versions to JA3 signatures
   - Support Chrome 109, 119, 120, Edge, Firefox
3. **Extend RuntimeEngine**
   - Use curl-impersonate when available
   - Fallback to requests with warning
4. **Add TLS validation tests**
   - Verify JA3 matches target browser
   - Test against JA3 fingerprinting services

## Benefits

- **Complete Impersonation:** Headers + TLS + HTTP/2 behavior
- **Server-Side Stealth:** Bypasses advanced bot detection
- **Performance:** No browser overhead for API calls
- **Scalability:** Lightweight for high-throughput scenarios

## Success Criteria

- [ ] JA3 fingerprint matches Chrome 120 exactly
- [ ] HTTP/2 behavior matches browser
- [ ] All tests pass against fingerprinting services
- [ ] Documentation for supported browser versions

## Estimated Effort

3-5 days for full TLS fingerprint matching
