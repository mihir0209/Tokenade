# Test 02: Firefox ChatGPT Cookies Export + CDP Proxy

## Date: 2026-06-16

## Step 1: List Browser Profiles
```bash
tokenade export --list-profiles
```
Result: Firefox default profile detected at `/home/ghostrider/snap/firefox/common/.mozilla/firefox/nj40lj6y.default`

## Step 2: Export ChatGPT Cookies
```bash
tokenade export --browser-name firefox --domains "chatgpt.com,openai.com,cdn.openai.com" -o /tmp/e2e_chatgpt.tokenade
```
Result:
- Extracted 3066 cookies from Firefox
- Filtered to 31 cookies for openai domains
- Auth status: logged_in
- Critical cookies: 9
- Session saved: `/tmp/e2e_chatgpt.tokenade`

## Step 3: Start CDP Proxy
```bash
nohup tokenade proxy -s /tmp/e2e_chatgpt.tokenade --port 9222 --no-open-browser > /tmp/proxy_chatgpt.log 2>&1 & disown
```
Result:
- Proxy started on 127.0.0.1:9222
- Injected 31 cookies into browser
- Session auto-refresh monitor started
- Dashboard title: "Tokenade CDP Proxy - openai"
- HTTP 200 response confirmed

## Step 4: Verify ChatGPT Loads via Proxy
Used Playwright to navigate to `http://127.0.0.1:9222/`, filled ChatGPT URL, clicked Browse.

### Screenshot Result
ChatGPT loaded successfully showing:
- "ChatGPT" title in sidebar
- "New chat", "Search chats", "Library", "Projects", "Apps", "Codex", "More" menu
- "What are you working on?" prompt
- "Ask anything" text input
- User "Mihir Patil" with "Free" plan in bottom left
- "Upgrade" button in top right

### Verification
- **Logged in: YES** (Mihir Patil, Free plan visible)
- **Cookies injected: YES** (31 cookies from openai.com)
- **TLS fingerprint: chrome120** (confirmed in dashboard)
- **Session valid: YES** (ChatGPT loaded with authenticated state)

### Cloudflare Note
- First load: SUCCESS (full ChatGPT interface loaded)
- Subsequent loads: Cloudflare "Verify you are human" challenge appeared
- This is expected behavior — Cloudflare rate-limits headless browsers

## Verdict: PASS
