# Tokenade Use Cases & Competitor Comparison

> Every distinct way Tokenade can be used, with real-world scenarios and how it compares to existing tools.

---

## Table of Contents

- [Use Cases](#use-cases)
  - [Web Scraping & Data Extraction](#1-web-scraping--data-extraction)
  - [E-Commerce & Price Monitoring](#2-ecommerce--price-monitoring)
  - [Social Media & Multi-Account](#3-social-media--multi-account)
  - [Security Testing & Penetration Testing](#4-security-testing--penetration-testing)
  - [Cross-Device Session Transfer](#5-cross-device-session-transfer)
  - [Browser Fingerprint Spoofing](#6-browser-fingerprint-spoofing)
  - [QA & Automated Testing](#7-qa--automated-testing)
  - [Developer Workflow Integration](#8-developer-workflow-integration)
  - [Enterprise & Compliance](#9-enterprise--compliance)
  - [AI & Automation](#10-ai--automation)
  - [Content & Research](#11-content--research)
- [Competitor Comparison](#competitor-comparison)
  - [Cookie Editor Extensions](#cookie-editor-extensions)
  - [Antidetect Browsers](#antidetect-browsers)
  - [Cloud Browser Platforms](#cloud-browser-platforms)
  - [Stealth Automation Tools](#stealth-automation-tools)
  - [Session Sharing & Security](#session-sharing--security)
- [Feature Matrix](#feature-matrix)

---

## Use Cases

### 1. Web Scraping & Data Extraction

#### 1.1 Authenticated Web Scraping
**Scenario:** Scrape data behind login walls — job boards, analytics dashboards, SaaS admin panels, membership sites.

**How Tokenade helps:**
```bash
# Export logged-in session from your browser
tokenade export --browser-name firefox --domains "linkedin.com" -o linkedin.tokenade

# Start proxy — browse as authenticated user
tokenade proxy -s linkedin.tokenade
# → All requests to LinkedIn carry your session cookies
# → Use with any scraping tool pointed at the proxy
```

**vs. Competitors:**
| Tool | Approach | Limitation |
|------|----------|-----------|
| `requests.Session()` | Python-only, no browser | Can't handle JS-rendered pages |
| Playwright `storageState` | Save/load browser state | No cross-browser transfer |
| Browserbase | Cloud browser | $20+/mo, data on their servers |
| **Tokenade** | **CLI + proxy** | **Free, self-hosted, cross-browser** |

#### 1.2 Anti-Bot / Cloudflare Bypass
**Scenario:** Access sites protected by Cloudflare, DataDome, PerimeterX using TLS fingerprint matching.

**How Tokenade helps:**
- TLS fingerprint matching via `curl-cffi` impersonates Chrome's JA3 hash
- Extract `cf_clearance` cookie from real browser → inject into proxy
- CDP artifact removal removes automation signatures

**Note:** TLS fingerprint matching via `curl-cffi` helps with some anti-bot stacks; results vary by site and are not guaranteed.

#### 1.3 Multi-Domain Authenticated Scraping
**Scenario:** Scrape across multiple authenticated domains simultaneously (e.g., Google Workspace + GitHub + Jira).

**How Tokenade helps:**
```bash
# Multi-site mode
tokenade proxy --all -d ./sessions/
# → Tabbed GUI, each tab uses different session
# → Simultaneous access to multiple authenticated services
```

#### 1.4 Cookie Consent Automation
**Scenario:** Handle GDPR consent popups before scraping.

**How Tokenade helps:** Export session after manually accepting consent — cookies persist across exports.

---

### 2. E-Commerce & Price Monitoring

#### 2.1 Price Monitoring at Scale
**Scenario:** Monitor competitor prices across 1000s of products. Amazon changes prices **2.5 million times/day**.

**How Tokenade helps:**
```bash
# Export session from logged-in account
tokenade export --browser-name chrome --domains "amazon.com" -o amazon.tokenade

# Use with price monitoring script
# → Session carries your auth cookies
# → No CAPTCHA challenges (TLS fingerprint matches)
```

**Business impact:** Data-backed price management yields **2-7% margin increase**, **200-350% ROI** over 12 months.

#### 2.2 B2B/Wholesale Price Access
**Scenario:** Some B2B sites show pricing only after login.

**How Tokenade helps:** Export wholesale account session → access B2B pricing programmatically.

#### 2.3 Supplier Price Tracking
**Scenario:** Track supplier portal prices across multiple accounts.

**How Tokenade helps:** Separate `.tokenade` files per supplier account, rotate between them.

---

### 3. Social Media & Multi-Account

#### 3.1 Multi-Account Management
**Scenario:** Manage 10+ social media accounts without cross-contamination.

**How Tokenade helps:**
```bash
# Each account gets its own session file
tokenade export --browser-name firefox --domains "instagram.com" -o ig_account1.tokenade
tokenade export --browser-name firefox --domains "instagram.com" -o ig_account2.tokenade

# Use anti-detection features
tokenade proxy -s ig_account1.tokenade --port 9222
```

**Why Tokenade beats extensions:** Extensions share browser fingerprint — accounts get linked. Tokenade isolates sessions into separate `.tokenade` files.

#### 3.2 Content Scheduling & Posting
**Scenario:** Schedule posts across Instagram, TikTok, LinkedIn, Twitter.

**How Tokenade helps:** Export sessions from each platform → automation tools use proxy for authenticated API calls.

#### 3.3 LinkedIn Lead Generation
**Scenario:** Generate 50+ leads/day from LinkedIn.

**How Tokenade helps:** Session persistence across multi-step workflows. Use real browser sessions — no fake profiles needed.

**Competitor:** GoLogin ($24/mo) offers this but requires cloud sync. Tokenade is free and local.

#### 3.4 Ad Management Across Platforms
**Scenario:** Manage Facebook Ads, Google Ads, TikTok Ads from one workflow.

**How Tokenade helps:** Separate session per platform, all accessible via proxy.

---

### 4. Security Testing & Penetration Testing

#### 4.1 Session Hijacking Testing
**Scenario:** Test if applications are vulnerable to session token theft.

**How Tokenade helps:**
```bash
# Export target session
tokenade export --browser-name firefox --domains "target.com" -o target.tokenade

# Use in testing environment
tokenade proxy -s target.tokenade
# → Verify session remains valid after export
# → Test session invalidation mechanisms
```

**Key stat:** 87% of successful attacks in 2024 involved post-MFA session hijacking.

#### 4.2 JWT Token Vulnerability Testing
**Scenario:** Test for `alg:none` bypass, weak HMAC, signature verification flaws.

**How Tokenade helps:** Export sessions containing JWTs → analyze token structure → test vulnerabilities.

#### 4.3 Cookie Attribute Security Audit
**Scenario:** Verify Secure, HttpOnly, SameSite, Domain, Path directives.

**How Tokenade helps:**
```bash
# Health check shows cookie flags
tokenade health -s session.tokenade
# → Reports missing HttpOnly, Secure flags
# → OWASP-based scoring
```

#### 4.4 CSRF Testing
**Scenario:** Test cross-site request forgery via cookie inclusion.

**How Tokenade helps:** Export authenticated session → replay requests from different origins.

#### 4.5 Session Fixation Testing
**Scenario:** Force known session ID before auth, hijack after login.

**How Tokenade helps:** Export session → verify session ID changes after re-authentication.

---

### 5. Cross-Device Session Transfer

#### 5.1 Device Migration
**Scenario:** Moving from old laptop to new laptop — transfer all logged-in sessions.

**How Tokenade helps:**
```bash
# Old device: export all sessions
tokenade export --browser-name firefox -o all_sessions.tokenade

# New device: import and proxy
tokenade proxy -s all_sessions.tokenade
# → All sites you were logged into now work on new device
```

**vs. Firefox Sync:** Firefox Sync requires same account. Tokenade works cross-browser (Firefox → Chrome).

#### 5.2 Browser Profile Synchronization
**Scenario:** Share browser state between Chrome and Firefox.

**How Tokenade helps:** Extract from Chrome → export as Playwright storageState → load into Firefox-based automation.

#### 5.3 Private Data Sync (No Server)
**Scenario:** Sync browser sessions without cloud services.

**How Tokenade helps:** `.tokenade` files are self-contained — transfer via USB, encrypted email, or local network.

**vs. Chrome Sync:** Chrome Sync stores data on Google servers. Tokenade keeps data local.

#### 5.4 Team Session Delegation
**Scenario:** Share authenticated access with team members without sharing credentials.

**How Tokenade helps:**
```bash
# Create password-protected share link
tokenade share -s session.tokenade --password team123 --expiry 48

# Team member imports
tokenade load -s <shared_link>
```

**vs. Sendwin:** Sendwin is a paid platform ($10+/mo). Tokenade is free and self-hosted.

---

### 6. Browser Fingerprint Spoofing

#### 6.1 Canvas Fingerprint Rotation
**Scenario:** Evade canvas-based tracking across websites.

**How Tokenade helps:** Identity profile system bundles cookies + fingerprint + TLS profile for consistent, believable identity.

#### 6.2 WebGL/GPU Spoofing
**Scenario:** Spoof GPU vendor/renderer to appear as different hardware.

**How Tokenade helps:** Fingerprint manager captures and replays WebGL parameters.

#### 6.3 AudioContext Fingerprinting Evasion
**Scenario:** Evade audio fingerprinting used by 15% of top 10K sites.

**How Tokenade helps:** Behavioral injection modifies AudioContext output.

#### 6.4 Multi-Layer Identity Consistency
**Scenario:** Anti-bot systems now check TLS + HTTP headers + JS execution + behavioral signals simultaneously.

**How Tokenade helps:**
- TLS fingerprint matches Chrome (JA3/JA4)
- CDP artifacts removed (no `window.cdc_*`)
- Behavioral signals injected (mouse paths, scroll timing)
- Consistent identity across all layers

**Key insight from research:** "Simple fingerprint rotation is now flagged as bot behavior. Consistent, believable identity profiles are required."

---

### 7. QA & Automated Testing

#### 7.1 Pre-Authenticated Test Setup
**Scenario:** Save login state once, reuse across test suites.

**How Tokenade helps:**
```bash
# Export admin session
tokenade export --browser-name chrome --domains "app.example.com" -o admin.tokenade

# Tests use proxy with admin session
tokenade proxy -s admin.tokenade --port 9222
# → All test requests are authenticated as admin
```

**vs. Playwright `storageState`:** Tokenade works with any tool (curl, requests, Selenium), not just Playwright.

#### 7.2 CI/CD Session Persistence
**Scenario:** Store auth state in CI artifacts for parallel test execution.

**How Tokenade helps:** `.tokenade` files are portable — store in CI secrets, inject into test environments.

#### 7.3 Test Data Isolation
**Scenario:** Each test gets fresh browser context to prevent cookie leakage.

**How Tokenade helps:** Create separate `.tokenade` files per test suite → parallel execution with isolated sessions.

#### 7.4 Cross-Browser Testing
**Scenario:** Test same session across Chrome, Firefox, Edge.

**How Tokenade helps:** Extract from Firefox → export as Playwright storageState → inject into any Chromium-based browser.

---

### 8. Developer Workflow Integration

#### 8.1 Playwright Session Injection
**Scenario:** Use Tokenade-exported sessions in Playwright tests.

**How Tokenade helps:**
```python
import json
from playwright.sync_api import sync_playwright

# Load Tokenade export
with open("storage_state.json") as f:
    state = json.load(f)

with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(storage_state=state)
    page = context.new_page()
    # → Already logged in
```

#### 8.2 Puppeteer Cookie Injection
**Scenario:** Use Tokenade-exported cookies in Puppeteer.

**How Tokenade helps:**
```python
import json
from pyppeteer import launch

with open("puppeteer_cookies.json") as f:
    cookies = json.load(f)

browser = await launch()
page = await browser.newPage()
await page.setCookie(*cookies)
# → Authenticated
```

#### 8.3 Python `requests` Session
**Scenario:** Use Tokenade-exported cookies in Python requests.

**How Tokenade helps:**
```python
import requests

# Load cookie header from Tokenade
with open("cookie_header.txt") as f:
    cookie_header = f.read()

response = requests.get(
    "https://api.example.com/data",
    headers={"Cookie": cookie_header}
)
```

#### 8.4 cURL Integration
**Scenario:** Use Tokenade-exported Netscape cookies with cURL.

**How Tokenade helps:**
```bash
# Export Netscape format
tokenade export --browser-name firefox --format netscape -o cookies.txt

# Use with curl
curl -b cookies.txt https://target.com/api/data
```

---

### 9. Enterprise & Compliance

#### 9.1 Session Audit Logging
**Scenario:** Track all session operations for SOC 2 / GDPR compliance.

**How Tokenade helps:**
```python
from tokenade.core.security.audit import AuditLogger

logger = AuditLogger()
logger.log_event("session_export", user="alice", session_id="s1")
logger.log_event("session_share", user="alice", session_id="s1", method="email")
# → Full audit trail in JSONL format
```

#### 9.2 Role-Based Access Control
**Scenario:** Restrict who can export/share/refresh sessions.

**How Tokenade helps:**
```python
from tokenade.core.security.audit import RoleManager

rbac = RoleManager()
rbac.assign_role("admin@company.com", "admin")
rbac.assign_role("intern@company.com", "viewer")
# → Intern can view but not export or share
```

#### 9.3 SSO Session Management
**Scenario:** Manage sessions across SSO-integrated applications.

**How Tokenade helps:** Export session after SSO login → proxy carries SSO cookies → access all integrated apps.

#### 9.4 Multi-Device Session Control
**Scenario:** Limit session usage to specific devices.

**How Tokenade helps:** Session vault with ACLs — only authorized users can access specific sessions.

#### 9.5 Refresh Token Rotation Compliance
**Scenario:** OWASP requires session regeneration after login and privilege changes.

**How Tokenade helps:** Session rotation monitor detects login events → triggers automatic re-export from source browser.

---

### 10. AI & Automation

#### 10.1 AI Agent Session Persistence
**Scenario:** AI agents (Browser Use, Stagehand) need persistent browser sessions across tool calls.

**How Tokenade helps:**
```python
from tokenade.sdk import TokenadeClient

client = TokenadeClient()
session = client.load("agent_session.tokenade")
# → Agent maintains login state across multiple tool calls
```

**Competitor:** Afina ($9/mo) is the only antidetect with MCP server for AI agents. Tokenade does this for free.

#### 10.2 MCP Session Reuse
**Scenario:** Multi-step AI workflows need persistent `--user-data-dir`.

**How Tokenade helps:** Export session → AI agent loads → maintains context across tool calls.

#### 10.3 Automated Web Interaction
**Scenario:** Automate complex web workflows (form filling, multi-step processes).

**How Tokenade helps:** Export mid-workflow session → continue automation from that point.

---

### 11. Content & Research

#### 11.1 SEO Rank Tracking (Multi-Location)
**Scenario:** Track search rankings from different geographic locations.

**How Tokenade helps:** Export sessions from different locations → each proxy uses local cookies → accurate local rankings.

#### 11.2 Ad Verification
**Scenario:** Verify ads are displayed correctly to target audiences.

**How Tokenade helps:** Export session from target demographic → view ads as intended audience.

#### 11.3 Financial Data Extraction
**Scenario:** Extract data from banking/brokerage dashboards.

**How Tokenade helps:** Export authenticated session → access financial data programmatically.

**Security note:** Tokenade encrypts session files with AES-256-GCM. Use `tokenade encrypt` for sensitive data.

#### 11.4 Real Estate Listing Monitoring
**Scenario:** Track new listings across multiple platforms.

**How Tokenade helps:** Separate sessions per platform → monitor without re-login.

#### 11.5 Job Board Data Extraction
**Scenario:** Extract job listings from authenticated portals.

**How Tokenade helps:** Export session → scrape job data with full authentication.

#### 11.6 Sports Betting Odds Monitoring
**Scenario:** Track odds across betting platforms (often require login).

**How Tokenade helps:** Export session → monitor odds in real-time via proxy.

#### 11.7 Court Record / Public Data Scraping
**Scenario:** Access court records behind login walls.

**How Tokenade helps:** Export authenticated session → access public records programmatically.

---

## Competitor Comparison

### Cookie Editor Extensions

| Feature | EditThisCookie | Cookie-Editor | CookieJar | **Tokenade** |
|---------|---------------|---------------|-----------|-------------|
| **Type** | Browser extension | Browser extension | Browser extension | **CLI + Proxy** |
| **Users** | 400K+ (removed) | 97K+ | New | **N/A (CLI)** |
| **Cross-browser** | ❌ Single browser | ❌ Single browser | ❌ Single browser | **✅ Any browser** |
| **Import/Export** | JSON, Netscape | JSON, Netscape, Header | JSON, Netscape | **JSON, Netscape, Header, Playwright, Puppeteer** |
| **Edit cookies** | ✅ | ✅ | ✅ | ❌ (extraction only) |
| **Encryption** | ❌ | ✅ Basic | ✅ | **✅ AES-256-GCM** |
| **TLS matching** | ❌ | ❌ | ❌ | **✅ JA3/JA4** |
| **Session sharing** | ❌ | ✅ Basic | ❌ | **✅ Email, Webhook, QR, HMAC** |
| **Stealth** | ❌ | ❌ | ❌ | **Best-effort (CDP cleanup, not undetectable)** |
| **CLI/Scriptable** | ❌ | ❌ | ❌ | **✅ Full CLI** |
| **Self-hosted** | N/A | N/A | N/A | **✅ No servers** |
| **Price** | Free | Free / Premium | Free | **Free** |

**Key advantage:** Tokenade is the only tool that works across browsers, matches TLS fingerprints, and is fully scriptable.

### Antidetect Browsers

| Feature | Multilogin | GoLogin | AdsPower | Dolphin Anty | **Tokenade** |
|---------|-----------|---------|----------|-------------|-------------|
| **Starting price** | €29/mo | $24/mo | $9/mo | $10/mo | **Free** |
| **Free plan** | Trial $2/3d | 3 profiles | 2 profiles | 5 profiles | **Unlimited** |
| **Profiles** | 10-10K | 3-100K+ | 2-5K+ | 5-∞ | **Unlimited** |
| **Engine** | Chromium + Firefox | Chromium | Chrome + Firefox | Chromium | **Any browser** |
| **API/Automation** | Selenium, Playwright | API, Puppeteer | Local API + RPA | API, Puppeteer | **CLI, SDK, API** |
| **Session extraction** | ❌ | ❌ | ❌ | ❌ | **✅ From real browser** |
| **TLS matching** | ✅ Built-in | ✅ Built-in | ✅ Built-in | ✅ Built-in | **✅ Via curl-cffi** |
| **Fingerprint spoofing** | ✅ Full | ✅ ML-based | ✅ Full | ✅ Full | **✅ Canvas, WebGL, Audio** |
| **Mobile profiles** | ❌ | ✅ Mobile app | ❌ | ❌ | **✅ ADB extraction** |
| **Self-hosted** | ❌ Cloud | ❌ Cloud | ✅ Local | ❌ Cloud | **✅ Local** |
| **Data on servers** | ✅ Yes | ✅ Yes | ✅ Local | ✅ Yes | **❌ Never** |
| **KYC required** | ✅ Yes | ❌ No | ❌ No | ❌ No | **❌ No** |

**Key advantage:** Antidetect browsers create fake profiles. Tokenade extracts **real sessions** from your actual browser — no profile creation needed.

### Cloud Browser Platforms

| Feature | Browserbase | Browserless | **Tokenade** |
|---------|-------------|-------------|-------------|
| **Price** | Free/$20/$99+ | Usage-based | **Free** |
| **Concurrency** | 3-250+ | Scalable | **Unlimited (local)** |
| **Session duration** | 15-60 min | Configurable | **Unlimited** |
| **Data storage** | Their servers | Their servers | **Your machine** |
| **Compliance** | SOC-2, HIPAA | — | **Self-hosted** |
| **Stealth mode** | ✅ | ❌ | **✅ CDP cleanup** |
| **CAPTCHA solving** | ✅ | ❌ | **❌ (use real cookies)** |
| **Offline use** | ❌ | ❌ | **✅** |

**Key advantage:** Cloud platforms require internet and store your data. Tokenade works offline and keeps data local.

### Stealth Automation Tools

| Feature | Camoufox | Nodriver | Patchright | **Tokenade** |
|---------|---------|----------|------------|-------------|
| **Detection score** | 0% | 67% | 67% | **Best-effort (measured, not undetectable)** |
| **Engine** | Firefox (C++) | Chromium | Chromium | **Any browser** |
| **Session extraction** | ❌ | ❌ | ❌ | **✅ From real browser** |
| **CLI/Scriptable** | ❌ Python API | ❌ Python API | ❌ Python API | **✅ Full CLI** |
| **Session sharing** | ❌ | ❌ | ❌ | **✅ Encrypted links** |
| **Health monitoring** | ❌ | ❌ | ❌ | **✅ OWASP scoring** |
| **Price** | Free | Free | Free | **Free** |

**Key advantage:** Stealth tools help you *appear* as a real browser. Tokenade *uses* real browser sessions — no stealth needed.

### Session Sharing & Security

| Feature | Sendwin | Flare (threat intel) | FlareSolverr | **Tokenade** |
|---------|---------|---------------------|--------------|-------------|
| **Type** | Sharing platform | Threat intel | CF bypass proxy | **CLI + Proxy** |
| **Price** | $10+/mo | Enterprise | Free | **Free** |
| **Share sessions** | ✅ | ❌ | ❌ | **✅ Encrypted** |
| **Password protection** | ✅ | N/A | N/A | **✅** |
| **Expiry** | ✅ | N/A | N/A | **✅ Configurable** |
| **Audit logging** | ✅ | ✅ | ❌ | **✅** |
| **Self-hosted** | ❌ | ❌ | ✅ | **✅** |
| **Cookie extraction** | ❌ | ❌ | ❌ | **✅ From any browser** |
| **TLS matching** | ❌ | ❌ | ✅ Basic | **✅ JA3/JA4** |

**Key advantage:** Sendwin shares sessions but doesn't extract them. Tokenade extracts + shares + proxies + monitors.

---

## Feature Matrix

| Category | Feature | Tokenade | Best Competitor |
|----------|---------|----------|-----------------|
| **Extraction** | Cross-browser extraction | ✅ | HackBrowserData (Go) |
| | Playwright storageState export | ✅ | cookie-extractor (Python) |
| | Puppeteer/CDP export | ✅ | — |
| | Netscape/curl export | ✅ | Cookie-Editor |
| | HTTP header export | ✅ | Cookie-Editor |
| | Import from other formats | ✅ | — |
| **Security** | AES-256-GCM encryption | ✅ | Multilogin (paid) |
| | HMAC-SHA256 signatures | ✅ | — |
| | Password-protected shares | ✅ | Sendwin (paid) |
| | RBAC | Code present | — |
| | LDAP/SSO | Code present | — |
| | Audit logging | Code present | Browserbase (paid) |
| **Performance** | TLS fingerprint matching | ✅ | Multilogin (€29/mo) |
| | Connection pooling | ✅ | — |
| | LRU session caching | ✅ | — |
| | Parallel extraction | ✅ | — |
| **Stealth** | CDP artifact removal | Best-effort | Camoufox (C++ fork) |
| | Canvas/WebGL patches | Best-effort | Multilogin (paid) |
| **Session Lifecycle** | Health scoring (OWASP) | ✅ | — |
| | Auto-refresh | ✅ | — |
| | Login/logout detection | ✅ | — |
| | Session vault + versioning | ✅ | — |
| **Integration** | REST API | ✅ | Browserbase ($20/mo) |
| | Python SDK | ✅ | — |
| | Docker/K8s | ✅ | Browserbase (paid) |
| | GitHub Actions CI/CD | ✅ | — |
| | Slack/Discord/Teams webhooks | ✅ | — |
| | Plugin system | ✅ | — |
| **Browser Support** | Chrome/Edge/Brave | ✅ | Most tools |
| | Firefox | ✅ | Camoufox, Multilogin |
| | Safari | ✅ | — |
| | Tor Browser | ✅ | — |
| | Arc/Opera/Vivaldi | ✅ | — |
| | Android (ADB) | ✅ | GoLogin (paid) |
| | iOS | Partial | — |

---

## Summary: Why Tokenade?

| Question | Answer |
|----------|--------|
| **What does Tokenade do?** | Extract, package, share, and proxy browser sessions with TLS fingerprint matching |
| **Who is it for?** | Security testers, QA engineers, developers, researchers, automation engineers |
| **What makes it unique?** | Only free tool combining cross-browser extraction + TLS matching + multi-format export + session portability |
| **What replaces with Tokenade?** | Paid session sharing tools, cloud browsers ($20-99/mo), cookie extensions (limited) |
| **Is it safe?** | Self-hosted, AES-256-GCM encryption, audit logging, RBAC |
| **What's the cost?** | Free forever. No accounts, no servers, no limits |
