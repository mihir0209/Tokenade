# Tokenade — Working Notes

## Release Policy

**DO NOT create releases or tags per feature.**

- Development happens on `main` — commit directly
- Version bumps in `pyproject.toml` are only done when explicitly asked
- **No GitHub releases or tags** until features are battle-tested with positive real-world results
- Only after confirmed working results (manual testing with real sites) should a version be tagged and released
- PyPI publishes only happen when user explicitly requests it
- This keeps the repo clean and avoids premature versioning

## Current State (2026-06-17)

### Version: 5.0.0 (released)
- **PyPI:** https://pypi.org/project/tokenade/5.0.0/
- **GitHub:** https://github.com/mihir0209/Tokenade/releases/tag/v5.0.0
- 1632 tests passing, 7 skipped, 0 failures
- Coverage: 84%
- Features built: CDP proxy (with CDP WebSocket injection), forward proxy, multi-site proxy, session refresh, sharing, encryption, health scoring, advanced validation, browser extension, web dashboard, session sync daemon, dashboard with WebSocket/diff/timeline/quick-actions

### Battle-Tested (confirmed working)
- ChatGPT: 68 cookies, CDP proxy, confirmed logged-in user
- Gmail: 149 cookies, CDP proxy, confirmed logged-in user
- Gmail persistence: 5/5 runs, no session invalidation
- Firefox extraction: Working
- Brave extraction: 111 cookies from 46 domains, 34 critical, auth=logged_in (2026-06-15)
- GitHub E2E: 15 cookies from Firefox, export → load → auth=logged_in (2026-06-15)
- Reddit E2E: 10 cookies from Firefox, export → load → auth=logged_in (2026-06-15)
- YouTube: 22 cookies from Playwright, CDP proxy, logged_in=True (2026-06-15)
- Session sharing encryption: AES-256-GCM, password-protected shares verified (2026-06-15)

### CDP Proxy Battle-Tested (2026-06-17)
- **External CDP connections:** Playwright `connect_over_cdp` now works via `/json/version` passthrough
- **Cookie injection via raw CDP:** `Storage.setCookies` injects 123/123 cookies at browser level, visible to ALL CDP clients
- **Gmail via external CDP:** PASS — 123 cookies, logged in as mihirpatil128@gmail.com (3,605 unread)
- **Bot detection via external CDP:** ALL GREEN — webdriver=None, chrome=True, chromeRuntime=True, plugins=3 (Chrome PDF Plugin), UA=Chrome/120, languages=['en-US','en'], connection=True, screen=1920x1080

### Stealth Architecture (Key Discovery)
- `ctx.add_init_script()` on the external CDP context works perfectly for stealth injection
- The proxy's own `add_init_script` does NOT persist to external CDP connections (by design)
- **Architecture:** Proxy handles cookies + TLS + session management; Client handles stealth/fingerprint via `ctx.add_init_script()` + `Emulation.setUserAgentOverride`
- `/stealth.js` endpoint now serves the comprehensive stealth script for easy client injection

### All Phases Complete
- Phase 1: Battle-tested all 6 core features ✅
- Phase 2: Fixed Chrome validation, session loader, site configs ✅
- Phase 3: Better errors, progress indicators, config file ✅
- Phase 4: Documentation (README, SITE_CONFIGS, TROUBLESHOOTING) ✅
- Phase 5: Safari decryption, extension bridge, plugin enable/disable ✅
- Phase 6: Quality/refactor/dashboard/docs ✅
  - Fixed API endpoint import bug, 45 session_sync tests, 9 flaky tests fixed
  - Refactored cdp_proxy.py (1870→477 lines, -75%): split into 6 modules
  - Refactored server.py (1295→384 lines, -70%): split into 4 modules
  - Dashboard expanded: WebSocket, session diff, timeline, quick actions
  - Docs: API.md, ARCHITECTURE.md, TUTORIALS.md, TROUBLESHOOTING.md

### New Features (2026-06-17)
- Session sync daemon: `tokenade sync add/remove/list/once/start`
- Local fingerprint proxy already existed (server.py, forward_proxy.py)
- Better error messages: CDP proxy launch, port-in-use, CLI catch-all, unsupported browser, no profile
- Dashboard: WebSocket real-time updates, session diff view, session timeline, quick actions
- Refactored CDP proxy: cdp_stealth.py, cdp_injection.py, cdp_gui.py, cdp_routing.py, cdp_api.py
- Refactored legacy proxy: server_utils.py, server_gui.py, server_routing.py
- Comprehensive docs: API.md, ARCHITECTURE.md, TUTORIALS.md, TROUBLESHOOTING.md

### Forward Proxy Battle-Tested (2026-06-17)
- **HTTPS CONNECT tunneling:** Google 200/82KB, DuckDuckGo 200/169KB
- **HTTP forwarding:** example.com 200/388B
- **Architecture fix:** Replaced `loop.sock_recv` on Protocol transport with stream-based bidirectional piping
- **Crash fix:** Null check on `_cookie_jar` before `get_for_request()` in HTTP handler

### Multi-Site Proxy Battle-Tested (2026-06-17)
- **2 sessions loaded:** GitHub (port 9221, 9 cookies) + Gmail (port 9222, 123 cookies)
- **SharedConnectionPool:** Thread-safe connection sharing between sessions
- **Master GUI:** Combined session UI on base port

### Stealth Script Battle-Tested (2026-06-17)
- **`/stealth.js` endpoint:** Serves comprehensive stealth script as JavaScript
- **Bot detection:** ALL GREEN on bot.sannysoft.com
  - navigator.webdriver: None (hidden)
  - window.chrome: object with runtime (real Chrome)
  - navigator.plugins: 3 (Chrome PDF Plugin, Chrome PDF Viewer, Native Client)
  - navigator.userAgent: Chrome/120 (not HeadlessChrome)
  - navigator.languages: ['en-US', 'en']
  - screen: 1920x1080
  - WebGL: Intel UHD Graphics 630

### Other Battle-Tests (2026-06-17)
- **Health check:** 97.6% score, 3 expired cookies on Gmail session
- **Session merge:** Gmail (123 cookies) + GitHub (9 cookies) → 94 merged (deduplicated), all domains from both present
- **Profile injection:** Direct Brave profile injection working
- **Twitter/X:** 40 cookies from Firefox, CDP proxy, logged in as donor user — PASS
- **LinkedIn:** 161 cookies from Firefox, CDP proxy, logged in as donor user — PASS (re-exported after user re-logged in)
- **Netflix:** Skipped (user not logged in Firefox)

### What's Next
- Phase 7: Coverage push to 90%+ (see `.agent/plans/phase7-plan.md`)
- Core crypto modules need more tests (cookie_crypto 68%, encryptor 68%)
- Integration modules need tests (kubernetes 20%, docker 55%, webhooks 39%)
- Feature modules need tests (advanced_validator 50%, fingerprint/manager 65%)

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
| Twitter/X | `twitter.com,x.com,api.twitter.com` |
| LinkedIn | `linkedin.com,www.linkedin.com` |
| Netflix | `netflix.com,api.netflix.com` |

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

### Architecture (v4.1.0+)

```
External CDP Client (Playwright/Puppeteer)
        │
        │ connect_over_cdp("http://127.0.0.1:9222")
        ▼
   aiohttp server (Tokenade)
        │
        │ GET /json/version → forwards to browser CDP port
        │ GET /json/list → forwards to browser CDP port
        ▼
   Playwright Chromium (headless, --remote-debugging-port=9223)
        │
        │ Storage.setCookies → 123/123 cookies injected at browser level
        │ Client calls ctx.add_init_script(stealth) for fingerprint spoofing
        ▼
   Target server (chatgpt.com, gmail.com, etc.)
        │
        │ Response
        ▼
   Client renders page with donor session + stealth
```

### Key Points
- Proxy handles: cookies, TLS fingerprint matching, session management, auto-refresh
- Client handles: stealth/fingerprint injection via `ctx.add_init_script()` + CDP `Emulation.setUserAgentOverride`
- Cookies are injected at browser level via raw CDP WebSocket (visible to ALL connections)
- Stealth script is injected per-context by the client (not persisted by proxy)
- `/json/version` and `/json/list` endpoints forward to the actual Chrome CDP port

### External CDP Client Integration

```python
from playwright.async_api import async_playwright

    STEALTH_JS = requests.get("http://127.0.0.1:9222/stealth.js").text  # From proxy's /stealth.js endpoint

async with async_playwright() as p:
    browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = browser.contexts[0]
    
    # Inject stealth (required for bot detection bypass)
    await ctx.add_init_script(STEALTH_JS)
    
    page = await ctx.new_page()
    cdp = await ctx.new_cdp_session(page)
    await cdp.send("Emulation.setUserAgentOverride", {
        "userAgent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "platform": "Linux x86_64",
    })
    
    await page.goto("https://mail.google.com")
    # Logged in with donor's session!
```

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

### CDP connection issues
- If `connect_over_cdp` fails, check that port 9222 (proxy) and 9223 (browser CDP) are accessible
- The proxy must be running before connecting via CDP
- Use `curl http://127.0.0.1:9222/json/version/` to verify CDP passthrough is working

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

### CDP External Connection Test (2026-06-17)
- Gmail via external Playwright CDP: PASS — 123 cookies, 82 visible, logged in as mihirpatil128@gmail.com
- Bot detection via external CDP: ALL GREEN
  - navigator.webdriver: None (correctly hidden)
  - window.chrome: object with runtime (real Chrome appearance)
  - navigator.plugins: 3 (Chrome PDF Plugin, Chrome PDF Viewer, Native Client)
  - navigator.userAgent: Chrome/120 (not HeadlessChrome)
  - navigator.languages: ['en-US', 'en']
  - navigator.connection: present (4g, rtt=50, downlink=10)
  - window.outerWidth/outerHeight: 1920/1080 (not 0)
  - WebGL: Intel UHD Graphics 630 (realistic vendor/renderer)

### Forward Proxy Test (2026-06-17)
- Google HTTPS (connect_over_cdp → CONNECT tunnel): 200, 82KB
- DuckDuckGo HTTPS: 200, 169KB
- example.com HTTP: 200, 388B

### Multi-Site Proxy Test (2026-06-17)
- 2 sessions: GitHub (9 cookies, port 9221) + Gmail (123 cookies, port 9222)
- SharedConnectionPool: Thread-safe, working
- Master GUI: Combined session UI on base port

### Health Check Test (2026-06-17)
- Gmail session: 97.6% health score, 3 expired cookies
- Report generated with recommendations

### Session Merge Test (2026-06-17)
- Gmail (123) + GitHub (9) → 94 cookies (deduplicated)
- All domains from both sessions preserved (28 unique domains)

### Twitter/X Test (2026-06-17)
- 40 cookies from Firefox, CDP proxy on port 9222
- Auth status: logged_in (user confirmed visually)
- Domains: twitter.com, x.com, abs.twimg.com

### LinkedIn Test (2026-06-17)
- 161 cookies from Firefox, CDP proxy on port 9222
- Auth status: logged_in (user confirmed visually, re-exported after fresh login)
- Domains: linkedin.com, www.linkedin.com, media.licdn.com

### Visible Mode Fix (2026-06-17)
- `--headless=new` was hardcoded in CDP proxy args even when `--visible` flag was passed
- Fixed: only append `--headless=new` when `config.headless=True`
- Result: `--visible` now properly shows Chromium window

## Files Modified

- `tokenade/cli.py` — Added `--cdp`/`--legacy` flags, `--domains` for export, updated help
- `tokenade/core/proxy/cdp_proxy.py` — Slim orchestrator (477 lines), delegates to cdp_stealth/injection/gui/routing/api modules. Re-exports backward-compat constants.
- `tokenade/core/proxy/cdp_stealth.py` — NEW: Stealth script, URL safety, blocked networks, site URLs
- `tokenade/core/proxy/cdp_injection.py` — NEW: CDP/WebSocket/localStorage injection
- `tokenade/core/proxy/cdp_gui.py` — NEW: GUI HTML templates
- `tokenade/core/proxy/cdp_routing.py` — NEW: Request routing, forwarding via curl-cffi/aiohttp
- `tokenade/core/proxy/cdp_api.py` — NEW: CDP API endpoints (json/version, json/list, stealth.js, status, stats)
- `tokenade/core/proxy/server.py` — Slim orchestrator (384 lines), delegates to server_utils/gui/routing modules
- `tokenade/core/proxy/server_utils.py` — NEW: ProxyResponse, URL rewriting, content rewriting
- `tokenade/core/proxy/server_gui.py` — NEW: Legacy proxy GUI templates
- `tokenade/core/proxy/server_routing.py` — NEW: Legacy proxy request forwarding
- `tokenade/core/proxy/forward_proxy.py` — Fixed CONNECT tunneling (stream-based piping), fixed HTTP handler crash
- `tokenade/core/proxy/__init__.py` — Exports CDPProxy as primary
- `tokenade/core/api/server.py` — Added /api/sync and /api/sync/run endpoints (fixed missing `from aiohttp import web` import)
- `tokenade/core/api/dashboard/index.html` — Modern dashboard with WebSocket, session diff, timeline, quick actions
- `tokenade/core/importer/session_sync.py` — NEW: Session sync daemon
- `tokenade/cli/proxy.py` — Better error messages (port-in-use, missing session, missing playwright)
- `tokenade/cli/__init__.py` — CLI catch-all shows error message + log path + --verbose hint, sync command
- `tokenade/cli/session.py` — No profile found suggests --list-profiles
- `tokenade/cli/management.py` — Sync daemon CLI commands
- `tokenade/core/importer/cookie_extractor.py` — Shows supported browsers on unsupported input
- `tokenade/tests/test_session_sync.py` — NEW: 45 tests for session_sync module
- `tokenade/tests/test_api_monitoring.py` — Fixed version assertion
- `tokenade/tests/test_proxy_modules.py` — Fixed ExtensionBridge broadcast tests
- `tokenade/tests/test_performance.py` — Fixed ConnectionPool/RateLimiter tests
- `tokenade/tests/test_api_server_comprehensive.py` — Fixed endpoints count assertion
- `tokenade/tests/test_proxy.py` — Updated to test extracted module functions
- `pyproject.toml` — Added `asyncio_default_fixture_loop_scope = "function"`
- `README.md` — Rewritten with step-by-step procedure
- `docs/API.md` — NEW: Comprehensive API documentation
- `docs/ARCHITECTURE.md` — NEW: Architecture documentation
- `docs/TUTORIALS.md` — NEW: 10 comprehensive tutorials
- `docs/TROUBLESHOOTING.md` — NEW: Troubleshooting guide
- `.agent/working.md` — This file
