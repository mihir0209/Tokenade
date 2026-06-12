# Tokenade Competitor Analysis

*Generated: June 2026*

## Category 1: TLS Fingerprint Proxies (Direct Competitors)

These tools solve the same core problem as Tokenade's proxy mode: making HTTP requests that appear to come from a real browser at the TLS/HTTP fingerprint level.

### 1. alterego (Go)
- **Repo**: github.com/covertchannelblog/alterego
- **Stars**: ~1 | License: MIT
- **What it does**: MITM HTTP/HTTPS proxy that clones TLS fingerprints using uTLS. Captures ClientHello from downstream browser, replays upstream.
- **Key features**:
  - Automatic ClientHello learning from downstream browser
  - ~50 built-in browser profiles (Chrome, Firefox, Safari, Edge, iOS, Android)
  - Shared cookie jar (browser + automation share cookies)
  - User-Agent inheritance from first downstream request
  - WebSocket support, SOCKS5 upstream, TUI dashboard
- **vs Tokenade**: alterego is a pure TLS proxy (no session packaging, no encryption, no site config). It's closer to what Tokenade's proxy mode does. Key difference: alterego requires a real browser connected downstream to learn the fingerprint; Tokenade packages the fingerprint into a `.tokenade` file.
- **Takeaway**: The shared cookie jar + fingerprint learning approach is elegant. We could add "live learning" mode where the proxy captures the fingerprint from a connected browser in real-time, in addition to our packaged approach.

### 2. thermoptic (Node.js/Docker)
- **Repo**: github.com/mandatoryprogrammer/thermoptic
- **Stars**: ~500+ | Most mature competitor
- **What it does**: HTTP stealth proxy that uses a real Chrome instance via CDP to make requests. All requests are replayed through the actual browser, so JA4/JA4H/JA4X/JA4T fingerprints are byte-perfect.
- **Key features**:
  - Browser-parity proxying (uses real Chrome for ALL requests)
  - JA4+ fingerprint suite spoofing (TLS, HTTP, X509, TCP)
  - Hook framework (before/after request, on-start)
  - Web UI at :14111 for manual browser control
  - Docker health checks, upstream proxy support
  - Hybrid scraping (browser + curl through same proxy)
- **vs Tokenade**: thermoptic is the gold standard for fingerprint accuracy because it uses a real browser. But it's heavyweight (Docker + Chrome), requires significant resources, and can't package/export sessions. Tokenade's advantage is lightweight packaging and portability.
- **Takeaway**: Their hook framework is powerful - we should consider adding pre/post request hooks for custom automation. Also, their approach of using the browser itself for requests (rather than trying to mimic it) is the most reliable approach. We could offer a "thermoptic mode" that uses Playwright internally.

### 3. CycleTLS-Proxy (Go)
- **Repo**: github.com/Danny-Dasilva/CycleTLS-Proxy
- **Stars**: ~200+
- **What it does**: High-performance HTTP proxy with TLS fingerprint spoofing. Header-based configuration (X-URL, X-IDENTIFIER, X-SESSION-ID).
- **Key features**:
  - 9 browser profiles (Chrome, Firefox, Safari, Edge, OkHttp, mobile)
  - Session management with connection reuse
  - Docker ready with health checks
  - Upstream proxy support
  - Simple HTTP API (any language can use it)
- **vs Tokenade**: CycleTLS is API-focused (header-based routing). Tokenade is session-focused (package and transfer login state). Different use cases but overlapping TLS spoofing.
- **Takeaway**: Their header-based API (`X-URL`, `X-IDENTIFIER`) is a clean interface pattern. We should support similar header-based control for programmatic use.

### 4. fingerproxy (Go)
- **Repo**: github.com/gospider007/fingerproxy
- **Stars**: ~17
- **What it does**: Forward proxy with automatic fingerprint switching based on User-Agent. Supports HTTP/1, HTTP/2, WebSockets, SOCKS5.
- **Key features**:
  - Auto-switch fingerprint based on User-Agent
  - TCP stream compression (zstd, br, gzip, snappy)
  - HTTP/2 fingerprint simulation
  - Header order simulation
- **vs Tokenade**: fingerproxy is a pure forward proxy. Tokenade adds session packaging, encryption, and the reverse proxy GUI mode.
- **Takeaway**: Their auto-switching based on User-Agent is clever - we could detect the User-Agent and auto-select the matching fingerprint.

### 5. TLSMask (Docker)
- **Repo**: github.com/tlsmask/tlsmask
- **Stars**: ~50+
- **What it does**: Upstream proxy that takes JA3/JA4_r values from Wireshark and reproduces them exactly.
- **Key features**:
  - Paste hex ClientHello from Wireshark
  - Exact cipher suite and extension ordering
  - HTTP/2 SETTINGS frame shaping
  - Docker-based, ~29MB image
- **vs Tokenade**: TLSMask is for pentesters who capture fingerprints from Wireshark. Tokenade is for users who want to transfer sessions between browsers.
- **Takeaway**: Wireshark hex import is a powerful feature for advanced users. We could add a "capture from Wireshark" mode.

### 6. proxy-mcp (Node.js)
- **Repo**: github.com/yfe404/proxy-mcp / github.com/CrackerCat/proxy-mcp
- **Stars**: Growing
- **What it does**: MCP server with MITM proxy, TLS fingerprint spoofing via impit (Rust), browser automation via CDP.
- **Key features**:
  - Full TLS + HTTP/2 fingerprint spoofing via impit (native Rust)
  - Browser stealth mode (cloakbrowser + Camoufox)
  - Chrome UA Client Hints normalization
  - Session capture and replay
  - HAR import/export
- **vs Tokenade**: proxy-mcp is MCP-focused (AI agent integration). Tokenade is CLI/package-focused. Their impit-based spoofing is more accurate than curl-cffi.
- **Takeaway**: The impit (Rust TLS impersonation) library is worth investigating as a replacement for curl-cffi. It's native and more accurate.

### 7. ViperTLS (Pure Python)
- **Repo**: github.com/walterwhite-69/vipertls
- **Stars**: New, growing
- **What it does**: Pure Python HTTP client with TLS fingerprint spoofing, browser challenge fallback, and clearance caching.
- **Key features**:
  - JA4 fingerprint family (JA4, JA4_r, JA4H, JA4S, JA4L)
  - HTTP/3/QUIC via aioquic
  - Browser fallback (Playwright Chromium) for JS challenges
  - Clearance caching (solve once, reuse)
  - Local proxy server mode
- **vs Tokenade**: ViperTLS is the closest Python competitor. It solves TLS + browser challenges. Tokenade adds session packaging and portability.
- **Takeaway**: Their TLS-first-then-browser escalation approach is smart. We should implement a similar fallback chain: try TLS spoofing first, fall back to browser if challenged.

### 8. TLS-Chameleon (Python)
- **Repo**: github.com/zinzied/TLS-Chameleon
- **Stars**: ~100+
- **What it does**: Python HTTP client with 45+ browser profiles, fingerprint randomization, auto-rotation on blocks.
- **Key features**:
  - 45+ browser profiles (Chrome, Firefox, Safari, Edge across OS)
  - Fingerprint randomization
  - Auto-rotation on 403/429/Cloudflare
  - Magnet module for data extraction
  - Ghost mode (stealth traffic shaping)
- **vs Tokenade**: TLS-Chameleon is a scraping library. Tokenade is a session portability tool.
- **Takeaway**: Their auto-rotation and block detection is useful. We could add auto-retry with fingerprint rotation when blocked.

---

## Category 2: Session/Cookie Transfer Tools (Adjacent Competitors)

These tools solve the "transfer login state between browsers" problem but without TLS fingerprint matching.

### 1. Session Importer (Firefox Extension)
- **URL**: addons.mozilla.org/firefox/addon/session-importer
- **What it does**: Export/import LocalStorage, SessionStorage, Cookies as JSON. Cross-browser transfer.
- **Takeaway**: Their one-click export UI is excellent. We could build a browser extension that exports directly to `.tokenade` format.

### 2. Portal (Chrome Extension)
- **URL**: chromewebstore.google.com/detail/portal-transfer-site-data
- **What it does**: Cross-device session migration. Generates transfer codes for cookies, localStorage, sessionStorage, IndexedDB.
- **Takeaway**: Transfer code approach (clipboard-based) is simple and works without servers. We could add a similar clipboard-based transfer mode.

### 3. cookie-share (Tampermonkey + Cloudflare Worker)
- **Repo**: github.com/fangyuan99/cookie-share
- **What it does**: Tampermonkey script for one-click cookie send/receive. Self-hosted backend (CF Worker or Node.js).
- **Takeaway**: Their "local-only mode" (no backend) is smart for single-device use. We should support offline `.tokenade` file transfer.

### 4. SyncMyCookie (Chrome Extension + Gist)
- **Repo**: github.com/kainy/sync-my-cookie-V3
- **What it does**: Sync cookies across browsers via encrypted GitHub Gist. Auto-push/auto-merge.
- **Takeaway**: Gist-based sync is clever but has GitHub dependency. Our `.tokenade` file approach is more portable.

### 5. SessionSync (Chrome Extension, E2E Encrypted)
- **URL**: chromewebstore.google.com/detail/sessionsync
- **What it does**: E2E encrypted session sync with AES-256-GCM + PBKDF2. No registration required.
- **Takeaway**: Their encryption approach (PBKDF2 600K iterations, write-protected tokens) matches our security model. We're already doing this.

### 6. agentcookie (macOS, Tailscale)
- **URL**: agentcookie.dev
- **What it does**: Continuous cookie sync from laptop to agent Mac via Tailscale. AES-256-GCM encryption. Supports bearer tokens + API keys.
- **Takeaway**: Their continuous sync model (fsnotify on Chrome's Cookies file) is the future. We could add a "watch mode" that auto-syncs when cookies change.

### 7. browser-pack (CLI + Cloud)
- **Repo**: github.com/nguyendinhphongdx/browser-pack
- **What it does**: Pack browser profiles into encrypted archives, push to cloud, pull on another machine.
- **Takeaway**: Their pack/push/pull workflow is similar to our export/import. We should compare encryption approaches (they use Argon2id, we use PBKDF2).

---

## Category 3: Anti-Detect Browsers (Indirect Competitors)

These are full browser solutions with fingerprint spoofing at the engine level.

### 1. ShardBrowser / ShardX (Chromium fork)
- **Repo**: github.com/ProxyShard/ShardBrowser
- **What it does**: Patched Chromium 148 with 170+ device profiles. Engine-level fingerprint spoofing (WebGL, WebGPU, Client Hints, fonts, TLS).
- **Takeaway**: Their engine-level approach is the most thorough but requires maintaining a browser fork. We take a different approach (proxy-level spoofing).

### 2. CloakBrowser (Chromium fork)
- **Repo**: github.com/CloakHQ/CloakBrowser-Manager
- **What it does**: 32 source-level C++ patches, passes Cloudflare Turnstile, 0.9 reCAPTCHA v3 score.
- **Takeaway**: Their patch list is a reference for what anti-bot systems actually check.

---

## Key Takeaways for Tokenade

### What We Should Adopt
1. **Live fingerprint learning** (from alterego): Allow the proxy to capture fingerprint from a connected browser in real-time
2. **Hook framework** (from thermoptic): Pre/post request hooks for custom automation
3. **Auto-retry with rotation** (from TLS-Chameleon): Detect blocks and rotate fingerprints
4. **Header-based API** (from CycleTLS): Clean programmatic interface
5. **Browser fallback chain** (from ViperTLS): TLS spoofing → browser fallback → cache clearance
6. **Wireshark import** (from TLSMask): Import captured ClientHello for exact fingerprinting

### What Makes Us Unique
1. **Session packaging** (.tokenade files): No competitor packages sessions as portable, encrypted files
2. **Site config abstraction**: JSON-based site detection rules (no hardcoded site names)
3. **Composable validation**: Multiple strategies (CSS, URL, API, content, cookie, localStorage)
4. **Cross-browser portability**: Extract from Firefox, inject into Brave/Chrome/Edge
5. **Encrypted transfer**: AES-256-GCM with PBKDF2 (military-grade)

### Our Weaknesses to Address
1. **TLS accuracy**: curl-cffi is less accurate than impit (Rust) or real browser (thermoptic)
2. **Firefox impersonation**: curl-cffi doesn't support Firefox TLS profiles
3. **Browser challenges**: No automatic Cloudflare Turnstile/JA3 challenge solving
4. **HTTP/3 QUIC**: Not supported yet (ViperTLS has this)
5. **Session persistence**: No auto-sync when cookies change (agentcookie has this)
