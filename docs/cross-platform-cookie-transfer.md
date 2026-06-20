# Cross-Platform Cookie Transfer & OAuth Token Refresh

## The Problem

Modern web platforms (Google, Microsoft, etc.) have a paradox:

1. **Automated tools can't log in** — Google, Microsoft, etc. block automated logins (Playwright, Selenium)
2. **Manual login is tedious** — When managing 5+ accounts, manually refreshing JWT tokens daily is unsustainable
3. **Cookies expire** — Platforms like Google Force expire cookies after ~24 hours
4. **The only reliable path** — Transfer cookies FROM a legitimate browser TO the automated tool

### Real-World Use Case: Google Flow

```
Legitimate Browser (Chrome/Firefox)
    │
    │  tokenade export --browser-name firefox --domains "google.com,flow.google.com"
    ▼
.tokenade file (cookies + tokens + metadata)
    │
    │  tokenade proxy -s google.tokenade
    ▼
Automated Tool (Playwright/CDP Proxy)
    │
    │  Uses cookies to authenticate
    ▼
Platform sees "legitimate" session
```

## How Tokenade Solves This

### Current Capabilities

| Feature | Status | What It Does |
|---------|--------|--------------|
| Cookie extraction | ✅ Done | Extracts from Chrome/Firefox/Edge/Brave (encrypted) |
| Cross-platform transfer | ✅ Done | Export from Linux, import to macOS/Windows |
| CDP proxy | ✅ Done | Injects cookies into Chromium, bypasses bot detection |
| Session refresh | ✅ Done | Re-exports from source browser when cookies expire |
| OAuth2 handler | ✅ Done | Generic OAuth2 with token refresh (Discord, Reddit) |
| Health monitoring | ✅ Done | Tracks cookie expiry, alerts before expiration |
| Session rotation | ✅ Done | Rotates between multiple sessions |

### What's Missing (The Gap)

| Gap | Impact | Solution |
|-----|--------|----------|
| No per-site `refresh_url` config | Can't auto-refresh specific tokens | Add `oauth_config` to .tokenade format |
| No cookie→token conversion | Cookies don't automatically become API tokens | Build OAuth token exchange pipeline |
| No CI/CD scheduling | Manual refresh still needed | GitHub Actions / cron integration |
| No multi-account orchestration | Managing 5+ accounts is manual | Batch refresh with rate limiting |

## Architecture: OAuth Token Refresh Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                    TOKENADE REFRESH PIPELINE                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. SOURCE BROWSER (Legitimate Login)                        │
│     └─ Cookies extracted via SQLite/CDP                      │
│                                                              │
│  2. SESSION PACKAGE (.tokenade file)                         │
│     ├─ cookies[]          (browser cookies)                  │
│     ├─ tokens[]           (access/refresh tokens)            │
│     ├─ oauth_config{}     (refresh_url, client_id, etc.)    │
│     └─ metadata{}         (expiry, refresh_count, etc.)      │
│                                                              │
│  3. TOKEN REFRESH ENGINE                                     │
│     ├─ Check cookie expiry                                   │
│     ├─ If expired: use refresh_token + refresh_url           │
│     ├─ POST to token_endpoint with:                          │
│     │   grant_type=refresh_token                             │
│     │   refresh_token=<stored_refresh_token>                 │
│     │   client_id=<from oauth_config>                        │
│     └─ Store new access_token + new refresh_token            │
│                                                              │
│  4. PROXY INJECTION                                          │
│     ├─ Inject refreshed cookies into Chromium                │
│     ├─ CDP proxy serves requests with valid session          │
│     └─ WebSocket notifies connected clients                  │
│                                                              │
│  5. CI/CD SCHEDULER (GitHub Actions / Cron)                  │
│     ├─ Runs every N hours                                    │
│     ├─ Checks all .tokenade files                            │
│     ├─ Refreshes expiring sessions                           │
│     └─ Commits updated .tokenade files back                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Enhanced .tokenade Format (Proposed)

```json
{
  "version": "2.1",
  "created_at": "2026-06-20T12:00:00Z",
  "site_name": "google",
  "auth_status": "logged_in",
  "cookies": [...],
  "tokens": [
    {
      "type": "access_token",
      "value": "ya29...",
      "expires_at": 1781900000
    },
    {
      "type": "refresh_token",
      "value": "1//0g...",
      "expires_at": null
    }
  ],
  "oauth_config": {
    "token_endpoint": "https://oauth2.googleapis.com/token",
    "client_id": "xxxx.apps.googleusercontent.com",
    "client_secret": "GOCSPX-...",
    "scopes": ["openid", "email", "profile"],
    "refresh_grant_type": "refresh_token"
  },
  "refresh_strategy": "oauth2",
  "metadata": {
    "last_refreshed_at": "2026-06-20T12:00:00Z",
    "refresh_count": 5,
    "source_browser": "firefox",
    "platform": "Linux"
  }
}
```

## Cross-Platform Transfer Guide

### Export (Source Machine)

```bash
# Linux → macOS
# On Linux (where browser is running):
tokenade export --browser-name firefox \
  --domains "google.com,accounts.google.com,flow.google.com" \
  -o google.tokenade

# Verify the session
tokenade health -s google.tokenade

# Check what's inside
tokenade sessions list -d .
```

### Import (Target Machine)

```bash
# On macOS (where Playwright runs):
# Option 1: Use the proxy directly
tokenade proxy -s google.tokenade --port 9222

# Option 2: Inject into browser profile
tokenade inject-profile \
  -s google.tokenade \
  -p ~/Library/Application\ Support/Google/Chrome/Default \
  --browser chrome

# Option 3: Load into Playwright context
tokenade load -f google.tokenade
```

### Automated Refresh (CI/CD)

```bash
# GitHub Actions workflow
name: Refresh Sessions
on:
  schedule:
    - cron: '0 */6 * * *'  # Every 6 hours

jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install Tokenade
        run: pip install tokenade
      - name: Refresh all sessions
        run: |
          for f in sessions/*.tokenade; do
            tokenade refresh -s "$f" --source-browser firefox
          done
      - name: Commit updated sessions
        run: |
          git config user.name "tokenade-bot"
          git config user.email "bot@tokenade.dev"
          git add sessions/
          git diff --staged --quiet || git commit -m "auto-refresh sessions"
          git push
```

## Google-Specific: The OAuth Refresh Flow

```
┌──────────────────────────────────────────────────────────┐
│              GOOGLE OAUTH2 TOKEN REFRESH                  │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  1. Extract cookies from Firefox/Chrome                   │
│     SID, HSID, SSID, APISID, SAPISID, __Secure-1PSID    │
│                                                           │
│  2. Use cookies to authenticate to Google                 │
│     GET https://myaccount.google.com                     │
│     Cookie: SID=...; HSID=...; SSID=...                  │
│                                                           │
│  3. If authenticated, extract OAuth tokens                │
│     From localStorage: access_token, refresh_token        │
│                                                           │
│  4. When access_token expires (1 hour):                   │
│     POST https://oauth2.googleapis.com/token              │
│     Content-Type: application/x-www-form-urlencoded       │
│     Body:                                                 │
│       grant_type=refresh_token                            │
│       refresh_token=1//0g...                              │
│       client_id=xxxx.apps.googleusercontent.com           │
│       client_secret=GOCSPX-...                            │
│                                                           │
│  5. Response:                                             │
│     {                                                     │
│       "access_token": "ya29...",                          │
│       "expires_in": 3600,                                 │
│       "refresh_token": "1//0g..."  // may be same         │
│     }                                                     │
│                                                           │
│  6. Use new access_token for API calls                    │
│     Authorization: Bearer ya29...                         │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

## Limitations & Workarounds

### What Works Today

| Scenario | How |
|----------|-----|
| Transfer cookies Linux→macOS | Export .tokenade, copy file, use proxy |
| Transfer cookies Linux→Windows | Same as above |
| Auto-refresh from source browser | `tokenade refresh --source-browser firefox` |
| Multi-account rotation | `tokenade proxy --all --rotate` |
| Health monitoring | `tokenade monitor start --sessions-dir ./sessions` |

### What Needs Work

| Scenario | Blocker | Solution |
|----------|---------|----------|
| Cookie→OAuth token conversion | No token endpoint config in .tokenade | Add `oauth_config` field |
| Auto-refresh without source browser | Need refresh_token + token_endpoint | OAuth2 refresh pipeline |
| CI/CD without source browser | Same as above | OAuth2 refresh in GitHub Actions |
| Google account in Playwright | Google blocks automated logins | Cookie transfer is the ONLY solution |
| Rate limiting across accounts | No built-in rate limiter | Add per-account refresh intervals |

## The Breakthrough

The **cookie transfer** approach solves the fundamental problem:

> "Google blocks automated logins, but cookies from a legitimate browser session ARE the login."

Tokenade's CDP proxy + stealth injection makes these cookies appear as if they come from a real browser. The platform can't tell the difference.

**The missing piece**: Automating the refresh cycle so cookies never expire. This requires:
1. OAuth token endpoint configuration per site
2. Scheduled refresh (cron/CI/CD)
3. Multi-account orchestration

This is the **exact use case** that started the project — and it's 80% there.
