# Tokenade — Next Steps (Updated)

## Release Policy
**No releases or tags until features are battle-tested with positive real-world results.**

## What's Done (This Session)
- ✅ Forward proxy HTTPS CONNECT tunneling (fixed)
- ✅ Multi-site proxy `_run_async` crash (fixed)
- ✅ Auto-refresh config timing (fixed)
- ✅ Session sharing encryption (AES-256-GCM)
- ✅ Brave extraction battle-tested (111 cookies)
- ✅ GitHub E2E battle-tested (15 cookies)
- ✅ Reddit E2E battle-tested (10 cookies)
- ✅ Session load E2E battle-tested (Playwright Chromium)

## What's Next — Battle-Test These

### 1. Forward Proxy HTTPS
Test: `export HTTP_PROXY=http://127.0.0.1:9223 && curl https://example.com`

### 2. Multi-Site Proxy
Test: `tokenade proxy --all -d ./sessions/`

### 3. Session Refresh
Test: `tokenade proxy -s session.tokenade --auto-refresh`

### 4. Profile Injection
Test: `tokenade inject-profile -s session.tokenade --browser firefox --profile /path/to/profile`

### 5. Health Check
Test: `tokenade health -s session.tokenade`

### 6. Session Merge/Rotate
Test: `tokenade sessions merge -d ./sessions/`

## Then Fix Issues
- Chrome cookie validation (silent decryption failures)
- Add site configs (GitHub, Discord, Reddit)
- Session loader cleanup (browser process leak)
- Better error messages
- Config file support

## Then Document
- README update
- Site config docs
- Troubleshooting guide
