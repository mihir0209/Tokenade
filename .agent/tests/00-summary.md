# Manual Test Summary

**Date:** 2026-06-14
**Version:** v3.4.0
**Total Tests:** 35 manual tests across 8 categories

## Results Summary

| Category | Tests | Pass | Fail | Notes |
|----------|-------|------|------|-------|
| Cookie Extraction | 5 | 5 | 0 | Firefox (3043), Brave (105) |
| Format Export | 7 | 7 | 0 | Playwright, Puppeteer, Netscape, Header |
| CDP Proxy | 3 | 3 | 0 | Injects 158/167 cookies |
| Health Scoring | 3 | 3 | 0 | OWASP scoring works (74.7/100) |
| Session Vault | 5 | 5 | 0 | ACLs, versioning, expiry |
| Anti-Detection | 6 | 6 | 0 | CDP cleaner, behavioral, forks |
| CLI/API/SDK | 9 | 9 | 0 | All commands work |
| Enterprise | 6 | 6 | 0 | Audit, RBAC, K8s, Docker |
| **Total** | **35** | **35** | **0** | |

## Key Findings

### Firefox (Snap)
- Profile: `~/.snap/firefox/common/.mozilla/firefox/nj40lj6y.default`
- Total cookies: 3043
- Google cookies: 166 (logged_in)
- GitHub cookies: 9 (logged_in)

### Brave
- Profile: `~/.config/BraveSoftware/Brave-Browser/Default`
- Total cookies: 105
- Uses Chrome extractor (`browser='chrome'`)

### CDP Proxy
- Successfully starts and injects cookies
- Auto-refresh monitor activates
- Binds to 127.0.0.1:9222

### Health Scoring
- OWASP-based scoring provides actionable insights
- Entropy scoring: 23.2/25 (good token values)
- Flag scoring: 16.5/25 (some cookies missing HttpOnly)
- Freshness: 25.0/25 (recently created session)

### Anti-Detection
- 5 stealth scripts for CDP artifact removal
- Bezier curve mouse paths (101 points)
- Ease-out scroll patterns
- Chromium fork detection works (Brave detected)

## Git Tags Created

```
v3.0.0 - Dev Tooling
v3.1.0 - Security & Multi-Format
v3.2.0 - Session Lifecycle
v3.3.0 - CLI & Testing
v3.4.0 - Browser & Ecosystem
```

All tags point to commit `2ef32f8`.
