# Tokenade — Working Notes

## Release Policy

**DO NOT create releases or tags per feature.**

- Development happens on `main` — commit directly
- Version bumps in `pyproject.toml` are only done when explicitly asked
- **No GitHub releases or tags** until features are battle-tested with positive real-world results
- Only after confirmed working results (manual testing with real sites) should a version be tagged and released
- PyPI publishes only happen when user explicitly requests it
- This keeps the repo clean and avoids premature versioning

## Current State (2026-06-15)

### Version: 4.1.0 (unreleased — pending battle testing)
- 1370 tests passing, 23 skipped, 0 failures
- Coverage: 81%
- Features built: CDP proxy, forward proxy, multi-site proxy, session refresh, sharing, encryption, health scoring, advanced validation, browser extension, web dashboard

### Battle-Tested (confirmed working)
- ChatGPT: 68 cookies, CDP proxy, confirmed logged-in user
- Gmail: 149 cookies, CDP proxy, confirmed logged-in user
- Gmail persistence: 5/5 runs, no session invalidation
- Firefox extraction: Working
- Brave extraction: 111 cookies from 46 domains, 34 critical, auth=logged_in (2026-06-15)
- GitHub E2E: 15 cookies from Firefox, export → load → auth=logged_in (2026-06-15)
- Reddit E2E: 10 cookies from Firefox, export → load → auth=logged_in (2026-06-15)
- Session sharing encryption: AES-256-GCM, password-protected shares verified (2026-06-15)

### Known Broken (needs fixing)
1. Forward proxy: No HTTPS CONNECT tunneling (only HTTP works)
2. Multi-site proxy: Calls `proxy._run_async()` which doesn't exist on CDPProxy
3. Auto-refresh: Config applied after `proxy.start()` already called
4. Session sharing: Base64 only, NOT encrypted (security issue)
5. Safari decryption: No-op (returns encrypted values)

### Untested (exists but never verified)
- Chrome/Edge/Brave cookie extraction
- Session load into browser
- Profile injection
- Health check command
- Session refresh command
- Session merge/rotate
- Advanced validation rules
- Format export/import
- Mobile extraction (Android/iOS)

### Next Steps
See `.agent/plans/next-steps.md` for detailed plan.

CDP proxy is working end-to-end. Tested with ChatGPT (68 cookies, logged in as mihirpatil128@gmail.com).

## Manual Step-by-Step Procedure

### Step 1: Find your browser profile

```bash
tokenade export --list-profiles
```

This shows all detected browser profiles. Note the `Browser` and `Path` values.

Example output:
```
Browser: firefox
Profile: nj40lj6y.default
Path: /home/ghostrider/snap/firefox/common/.mozilla/firefox/nj40lj6y.default
```

### Step 2: Export cookies to .tokenade file

```bash
tokenade export --browser-name firefox --domains "DOMAIN1,DOMAIN2" -o output.tokenade
```

Replace:
- `firefox` with your browser (chrome, firefox, edge, brave)
- `DOMAIN1,DOMAIN2` with the target site's domains
- `output.tokenade` with your desired filename

**Common domain patterns:**

| Site | Domains |
|------|---------|
| ChatGPT | `chatgpt.com,openai.com,cdn.openai.com` |
| Gmail | `google.com,accounts.google.com,mail.google.com` |
| GitHub | `github.com,api.github.com` |
| Discord | `discord.com,discordapp.com` |
| Reddit | `reddit.com,old.reddit.com,www.reddit.com` |

**Examples:**

```bash
# ChatGPT from Firefox
tokenade export --browser-name firefox --domains "chatgpt.com,openai.com,cdn.openai.com" -o chatgpt.tokenade

# Gmail from Firefox
tokenade export --browser-name firefox --domains "google.com,accounts.google.com,mail.google.com" -o gmail.tokenade

# Gmail from Chrome
tokenade export --browser-name chrome --domains "google.com,accounts.google.com" -o gmail.tokenade

# GitHub from a specific profile
tokenade export --browser-name firefox --profile "2P8fh3oV.Profile 3" --domains "github.com" -o github.tokenade
```

### Step 3: Start the proxy

```bash
tokenade proxy -s output.tokenade
```

This:
1. Loads the .tokenade file
2. Launches Playwright Chromium (headless)
3. Injects donor cookies into the browser
4. Starts an HTTP server on port 9222
5. Opens `http://127.0.0.1:9222` in your default browser

**Options:**

```bash
# Show the Chromium window (non-headless)
tokenade proxy -s session.tokenade --visible

# Custom port
tokenade proxy -s session.tokenade --port 8080

# Don't auto-open browser
tokenade proxy -s session.tokenade --no-open-browser
```

### Step 4: Browse

1. Open `http://127.0.0.1:9222` in your browser
2. Enter the target URL (e.g., `https://chatgpt.com` or `https://mail.google.com`)
3. Click "Browse"
4. You should see the page loaded with the donor's session

## How the CDP Proxy Works

```
Your Browser (Brave/Firefox/Chrome)
        │
        │ HTTP request to 127.0.0.1:9222
        ▼
   aiohttp server (Tokenade)
        │
        │ Creates Playwright page
        │ page.route("**/*") intercepts ALL requests
        ▼
   route_handler(request)
        │
        │ Extracts URL, method, headers, body
        ▼
   curl-cffi (TLS fingerprint matched)
        │
        │ Forwards with Chrome JA3 hash + donor cookies
        ▼
   Target server (chatgpt.com, gmail.com, etc.)
        │
        │ Response
        ▼
   route.fulfill(response)
        │
        │ Browser receives response, renders normally
        ▼
   Your Browser renders the page
```

Key points:
- The browser makes the requests (not the proxy)
- curl-cffi provides Chrome TLS fingerprint (JA3 match)
- Donor cookies are injected into the browser context
- No URL rewriting needed — browser handles everything natively
- Works with SPAs (React, Next.js, etc.)

## Troubleshooting

### "No cookies found"
- Make sure you're logged into the site in your browser
- Check that the `--domains` flag matches the site's cookie domains
- Try `--list-profiles` to verify the correct browser/profile

### Page loads but not logged in
- The cookies may have expired
- Re-export from the browser (cookies change frequently)
- Check `tokenade health -s session.tokenade`

### Slow loading
- First request is slow (TLS handshake + page load)
- Subsequent requests are fast (connection pooling)
- Increase timeout: `tokenade proxy -s session.tokenade --timeout 60`

### Google/Gmail specific notes
- Google invalidates sessions after ~5 device changes
- The proxy uses a different IP than your usual location
- Google may show "New device sign-in" email — this is normal
- If Google blocks the session, re-export from your browser

## Test Results

### ChatGPT (2026-06-11)
- 68 cookies extracted from Firefox default profile
- Auth status: logged_in
- CDP proxy: 232 requests, 494KB page, user mihirpatil128@gmail.com confirmed
- All checks pass: title, profile image, email, logged_in indicator, textarea

### Gmail (2026-06-11)
- 149 cookies extracted from Firefox default profile
- Auth status: logged_in, 49 critical cookies
- CDP proxy: 10 requests, 255KB page, user email confirmed

### Login Persistence Test (Gmail, 5 runs)
- Run 1: OK (255KB, 0 errors)
- Run 2: OK (254KB, 0 errors)
- Run 3: OK (254KB, 0 errors)
- Run 4: OK (254KB, 0 errors)
- Run 5: OK (255KB, 0 errors)
- **Result: 5/5 — Session persisted across all 5 logins, NO INVALIDATION**
- Google did NOT invalidate the session despite different IP/user-agent

## Files Modified

- `tokenade/cli.py` — Added `--cdp`/`--legacy` flags, `--domains` for export, updated help
- `tokenade/core/proxy/cdp_proxy.py` — New CDP proxy (Playwright + curl-cffi)
- `tokenade/core/proxy/__init__.py` — Exports CDPProxy as primary
- `README.md` — Rewritten with step-by-step procedure
- `.agent/working.md` — This file
