# Test 03: Firefox Gmail Cookies Export + CDP Proxy

## Date: 2026-06-16

## Step 1: Export Gmail Cookies
```bash
tokenade export --browser-name firefox --domains "google.com,accounts.google.com,mail.google.com" -o /tmp/e2e_gmail.tokenade
```
Result:
- Extracted 3094 cookies from Firefox
- Filtered to 123 cookies for google domains
- Auth status: logged_in
- Critical cookies: 33
- Session saved: `/tmp/e2e_gmail.tokenade`

## Step 2: Start CDP Proxy
```bash
nohup tokenade proxy -s /tmp/e2e_gmail.tokenade --port 9222 --no-open-browser > /tmp/proxy_gmail.log 2>&1 & disown
```
Result:
- Proxy started on 127.0.0.1:9222
- Dashboard title: "Tokenade CDP Proxy - google"
- HTTP 200 response confirmed

## Step 3: Verify Gmail Loads via Proxy
Used Playwright to navigate to `http://127.0.0.1:9222/`, filled Gmail URL, clicked Browse.

### Screenshot Result
Gmail loaded successfully showing:
- Gmail logo and "Mihir Patil" profile in top right
- Inbox with 3,594 unread emails
- 1-50 of 4,942 total emails
- Primary tab with 50 new, Promotions with 50 new, Social with 29 new, Updates with 50 new
- Recent emails from:
  - LinkedIn (Yugandhara Patil and others)
  - Reddit ("Is my boyfriend cheating on me??")
  - Myntra (Father's Day Treat)
  - ant.wilson (Supabase Project)
  - GitGuardian Team (internal incident detected)
  - Bharatiya Antariksh (Team Joining Request)
  - GitHub (personal access token about to expire)
  - MongoDB Community Hub
  - Name.com Support (verification code)
  - Zoom (Registration Confirmed)
  - Ente (7-day reminder)
- Sidebar: Compose, Inbox, Starred, Snoozed, Sent, Drafts, Purchases (180), Labels
- Warning: "This browser version is no longer supported" (expected for headless Chromium)

### Verification
- **Logged in: YES** (Mihir Patil profile visible)
- **Cookies injected: YES** (123 cookies from google.com)
- **Session valid: YES** (Gmail inbox loaded with all emails)
- **Real emails visible: YES** (GitGuardian, GitHub, LinkedIn, Reddit, etc.)

## Verdict: PASS
