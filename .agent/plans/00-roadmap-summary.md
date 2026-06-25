# Tokenade Development Roadmap — Phases 46-50

## Context
User insights led to strategic pivot:
1. **Session marketplace → Plugin marketplace** (identity impersonation risk)
2. **Match competitor features** (AdsPower, Multilogin, GoLogin)
3. **Better stealth approaches** (playwright-stealth, Docker, dependencies)
4. **Cloudflare/Akamai bypass** (IP checking, residential proxies)

## Phase Overview

| Phase | Name | Effort | Priority | Dependencies |
|-------|------|--------|----------|--------------|
| 46 | Enhanced Browser Stealth | 2-3 weeks | HIGH | None |
| 47 | Cloudflare & Akamai Bypass | 3-4 weeks | HIGH | Phase 46 |
| 48 | Plugin Marketplace Enhancement | 4-6 weeks | MEDIUM | Phase 46, 47 |
| 49 | Competitor Feature Parity | 6-8 weeks | MEDIUM | Phase 46, 47 |
| 50 | Stealth Testing & Validation | 2-3 weeks | HIGH | Phase 46, 47 |

## Recommended Execution Order

```
Phase 46 (Stealth) ──┬──> Phase 47 (Cloudflare) ──┬──> Phase 48 (Plugins)
                      │                              │
                      └──> Phase 50 (Testing) ──────┘
                                                       │
                                                       └──> Phase 49 (Competitor Features)
```

**Rationale:**
1. Phase 46 must come first — stealth patches are foundation
2. Phase 47 builds on stealth — Cloudflare bypass needs stealth
3. Phase 50 validates stealth — testing framework needed early
4. Phase 48 can start in parallel — plugin types need stealth/CAPTCHA APIs
5. Phase 49 last — features depend on stealth working

## Total Effort Estimate
- Phase 46: 8-10 days
- Phase 47: 8-11 days
- Phase 48: 12-17 days
- Phase 49: 14-18 days
- Phase 50: 8-10 days
- **Total: 50-66 days (10-13 weeks)**

## Key Decisions

1. **Stealth library choice:** `playwright-stealth` (Python) as base, supplement with custom patches
2. **TLS fingerprinting:** `curl-cffi` for Chrome/Firefox impersonation
3. **Proxy strategy:** Residential proxies for Cloudflare bypass, not datacenter
4. **Plugin architecture:** New types (stealth, proxy, captcha) added to existing plugin system
5. **Competitor features:** Focus on session portability (unique value), not antidetect browser
6. **Testing:** Automated detection testing in CI/CD, fail if score drops

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Stealth patches break websites | Configurable patches, disable individually |
| Cloudflare patches detection | Regular testing against test sites |
| Plugin marketplace security | SHA256 verification, checksums |
| Competitor feature scope creep | Focus on session portability unique value |
| Docker dependency overhead | Optional, not required |

## Success Metrics

| Metric | Target |
|--------|--------|
| bot.sannysoft.com score | > 90% |
| pixelscan.net score | > 80% |
| Google cookie search | No CAPTCHA |
| Cloudflare bypass rate | > 70% |
| Plugin count | 20+ |
| Test count | > 5000 |
