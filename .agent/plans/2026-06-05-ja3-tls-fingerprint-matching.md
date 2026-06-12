# JA3/TLS Fingerprint Matching

**Date:** 2026-06-05
**Status:** Planned
**Priority:** Critical
**Blocks:** Real-world cookie injection on Cloudflare-protected sites

## Problem

Cloudflare and similar anti-bot services check TLS fingerprints (JA3/JA4). When cookies are injected via Playwright/Chromium, the TLS fingerprint doesn't match the source browser (Firefox). This causes:
- Cloudflare challenge pages ("Just a moment...")
- 403 responses from API endpoints
- Session validation failures even when cookies are correct

## Evidence from Testing

```
api_probe: FAIL (confidence=0.8) - API returned 403
url_redirect: stayed on target but Cloudflare intercepted
page shows "Just a moment..." after cookie injection
```

## Solution: curl-impersonate Integration

```python
from curl_cffi import requests as curl_requests

# Match Chrome/Firefox TLS fingerprint exactly
response = curl_requests.get(
    url,
    impersonate="chrome120",  # JA3 matches Chrome 120
    headers=matched_headers,
    cookies=cookies,
)
```

## Implementation Plan

### Phase 1: Core TLS Matcher (Days 1-2)
1. Add `curl-cffi` as optional dependency (`pip install tokenade[runtime]`)
2. Create `tokenade/core/runtime/tls_matcher.py`
3. Map browser versions to JA3 signatures
4. Support: Chrome 109-120, Firefox 120+, Edge, Safari

### Phase 2: RuntimeEngine Integration (Day 3)
1. Extend `RuntimeEngine` to use curl-impersonate when available
2. Fallback to `requests` with warning when not available
3. Auto-detect best impersonation target from source browser

### Phase 3: Validation Integration (Day 4)
1. Add `TLSFingerprintStrategy` to `SessionValidator`
2. Test against fingerprinting services (ja3er.com, fingerprintjs.com)
3. Validate JA3 matches source browser within 5%

### Phase 4: CLI Integration (Day 5)
1. Add `--tls-match` flag to `tokenade load`
2. Add `--impersonate` option to specify target browser
3. Auto-detect from source browser if not specified

## Files

### New Files
- `tokenade/core/runtime/tls_matcher.py` - JA3/JA4 matching engine
- `tokenade/core/runtime/impersonate.py` - Browser impersonation profiles
- `tokenade/tests/test_tls_matcher.py` - Unit tests

### Modified Files
- `tokenade/core/runtime/engine.py` - Use curl-impersonate
- `tokenade/core/importer/validator.py` - Add TLS validation strategy
- `tokenade/cli.py` - Add --tls-match flag
- `setup.py` - Add curl-cffi optional dependency

## Success Criteria

- [ ] JA3 fingerprint matches Chrome 120 exactly
- [ ] HTTP/2 behavior matches browser
- [ ] Cloudflare challenge pages bypassed
- [ ] API endpoints return 200 (not 403)
- [ ] All existing tests pass
- [ ] New tests for TLS matching

## Estimated Effort

5 days for production-ready TLS fingerprint matching

## Dependencies

- `curl-cffi>=0.6.0` (optional, for JA3 matching)
- No new Python dependencies for core functionality
