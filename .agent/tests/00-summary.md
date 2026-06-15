# E2E Test Summary — v4.1.0 Published Package

## Date: 2026-06-16

## Package
- **Version:** 4.1.0
- **PyPI:** https://pypi.org/project/tokenade/4.1.0/
- **GitHub:** https://github.com/mihir0209/Tokenade/releases/tag/v4.1.0

## Test Results

| # | Test | Result | Notes |
|---|------|--------|-------|
| 01 | PyPI Package Installation | PASS | Installed from PyPI, CLI works |
| 02 | Firefox ChatGPT Export + Proxy | PASS | 31 cookies, logged in as Mihir Patil |
| 03 | Firefox Gmail Export + Proxy | PASS | 123 cookies, 3,594 unread emails visible |
| 04 | Health Check | PASS | 97.6% Gmail, 80.6% ChatGPT, 92.1% merged |
| 05 | Session Management | PASS | List, merge (154→114 deduped), diff |
| 06 | Encrypt/Decrypt | PASS | Roundtrip preserves data (17081→17147→17081) |
| 07 | Session Sharing | PASS | AES-256-GCM encrypted, password protected |
| 08 | Config Management | PASS | ~/.tokenade/config.json loaded correctly |
| 09 | Plugin System | PASS | List command works (empty registry) |
| 10 | TLS Fingerprint Matching | PASS | Chrome/120.0.0.0 JA3 hash, curl-cffi working |

## Battle-Tested Sites

| Site | Browser | Cookies | Auth Status | Verified |
|------|---------|---------|-------------|----------|
| ChatGPT | Firefox | 31 | logged_in (Mihir Patil) | Screenshot |
| Gmail | Firefox | 123 | logged_in (Mihir Patil, 3,594 unread) | Screenshot |

## Commands Used

### Export
```bash
tokenade export --browser-name firefox --domains "chatgpt.com,openai.com,cdn.openai.com" -o /tmp/e2e_chatgpt.tokenade
tokenade export --browser-name firefox --domains "google.com,accounts.google.com,mail.google.com" -o /tmp/e2e_gmail.tokenade
```

### Proxy
```bash
tokenade proxy -s /tmp/e2e_chatgpt.tokenade --port 9222 --no-open-browser
tokenade proxy -s /tmp/e2e_gmail.tokenade --port 9222 --no-open-browser
```

### Health
```bash
tokenade health -s /tmp/e2e_gmail.tokenade
tokenade health -s /tmp/e2e_chatgpt.tokenade
```

### Merge
```bash
tokenade sessions merge /tmp/e2e_chatgpt.tokenade /tmp/e2e_gmail.tokenade -o /tmp/e2e_merged.tokenade --site-name combined
```

### Diff
```bash
tokenade diff /tmp/e2e_chatgpt.tokenade /tmp/e2e_gmail.tokenade
```

### Encrypt/Decrypt
```bash
tokenade encrypt --input /tmp/e2e_chatgpt.tokenade --output /tmp/e2e_chatgpt_enc.tokenade --password testpassword123
tokenade decrypt --input /tmp/e2e_chatgpt_enc.tokenade --output /tmp/e2e_chatgpt_dec.tokenade --password testpassword123
```

### Share
```bash
tokenade share --session /tmp/e2e_chatgpt.tokenade --password test123 --format url
```

### Config
```bash
tokenade config show
```

### Plugin
```bash
tokenade plugin list
```

### Validate
```bash
tokenade validate -d /tmp/
```

## Known Limitations
1. **Cloudflare:** Headless Chromium triggers Cloudflare "Verify you are human" challenge on subsequent loads (first load succeeds)
2. **Browser version warning:** Gmail shows "This browser version is no longer supported" for headless Chromium (cosmetic only)

## Overall Verdict: ALL TESTS PASS
