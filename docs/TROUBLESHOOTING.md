# Troubleshooting Guide

Comprehensive troubleshooting guide for Tokenade. Each section covers symptoms, causes, solutions, and prevention.

---

## Table of Contents

1. [Installation Issues](#1-installation-issues)
2. [Export Issues](#2-export-issues)
3. [CDP Proxy Issues](#3-cdp-proxy-issues)
4. [Legacy Proxy Issues](#4-legacy-proxy-issues)
5. [Forward Proxy Issues](#5-forward-proxy-issues)
6. [Multi-Site Proxy Issues](#6-multi-site-proxy-issues)
7. [Session Sync Issues](#7-session-sync-issues)
8. [Dashboard Issues](#8-dashboard-issues)
9. [Plugin Issues](#9-plugin-issues)
10. [Performance Issues](#10-performance-issues)
11. [Platform-Specific Issues](#11-platform-specific-issues)
12. [Error Code Reference](#12-error-code-reference)

---

## 1. Installation Issues

### Python version too old

**Symptoms:** `SyntaxError` or `ModuleNotFoundError` on import.

**Cause:** Tokenade requires Python 3.10+ for modern type hints (`X | Y` syntax, `match` statements).

**Solutions:**
```bash
python3 --version  # Check current version
# Install Python 3.10+:
# Ubuntu/Debian:
sudo apt install python3.11 python3.11-venv
# macOS:
brew install python@3.11
# Use pyenv:
pyenv install 3.11
```

**Prevention:** Always use Python 3.10 or newer. Check `python3 --version` before installing.

---

### pip install fails with build errors

**Symptoms:** `error: command 'gcc' failed` or `Failed building wheel for ...`

**Cause:** Missing system-level build dependencies for native extensions (e.g., `cryptography`, `curl-cffi`).

**Solutions:**
```bash
# Ubuntu/Debian:
sudo apt install python3-dev build-essential libffi-dev

# macOS:
xcode-select --install

# CentOS/RHEL:
sudo yum groupinstall "Development Tools"
sudo yum install python3-devel libffi-devel
```

**Prevention:** Install build tools before `pip install tokenade`.

---

### Missing dependencies on import

**Symptoms:** `ModuleNotFoundError: No module named 'aiohttp'` or similar.

**Cause:** Optional dependencies not installed (Tokenade uses a modular install).

**Solutions:**
```bash
pip install tokenade[full]       # Install all optional deps
# Or install specific extras:
pip install tokenade[proxy]      # For proxy features
pip install tokenade[sharing]    # For QR/email sharing
pip install "qrcode[pil]"       # For QR code generation
pip install websockets           # For extension bridge
pip install playwright           # For CDP proxy
playwright install chromium      # Install browser binaries
```

**Prevention:** Use `pip install tokenade[full]` for complete functionality.

---

## 2. Export Issues

### "No browser profiles found"

**Symptoms:**
```
No browser profiles found for firefox
```

**Cause:** Tokenade can't locate browser profile directories in standard paths.

**Solutions:**
```bash
# List discovered profiles
tokenade export --list-profiles

# Specify path manually
tokenade export --browser-name firefox --browser-path /path/to/profile

# Common profile locations:
# Chrome:    ~/.config/google-chrome/Default
# Firefox:   ~/.mozilla/firefox/*.default-release
# Brave:     ~/.config/BraveSoftware/Brave-Browser/Default
# Edge:      ~/.config/microsoft-edge/Default
# Chrome macOS: ~/Library/Application Support/Google/Chrome/Default
# Firefox macOS: ~/Library/Application Support/Firefox/Profiles/*.default-release
```

**Prevention:** Run `tokenade export --list-profiles` to verify profile detection before exporting.

---

### "Database is locked"

**Symptoms:**
```
sqlite3.OperationalError: database is locked
```

**Cause:** Browser is running and holds an exclusive lock on the cookies database.

**Solutions:**
```bash
# Close the browser completely, then retry

# Or use profile injection (works while browser is running):
tokenade inject-profile -s session.tokenade --browser firefox --profile "default"

# Tokenade auto-copies the DB, but if it fails:
# 1. Fully close the browser (check Task Manager / Activity Monitor)
# 2. Delete lock files:
rm -f ~/.config/google-chrome/Default/Cookies-journal
rm -f ~/.config/google-chrome/Default/Cookies.lock
```

**Prevention / alternatives:**
- Fully quit the target browser before CLI SQLite export, **or**
- Use the **browser extension** (live cookies, default `.tokenade`; no TLS fingerprint), **or**
- Export via **CDP** from a browser started with a remote debugging port, **or**
- Import an existing dump with `tokenade convert`.

---

### "Decryption failed"

**Symptoms:**
```
Cookie decryption: 0 succeeded, 50 failed (of 50 encrypted)
```

**Cause:** Cookie encryption key not accessible (platform keyring not available, or wrong profile).

> **Windows Chromium (Chrome / Edge / Brave v127+) — app-bound encryption:**
> If *every* cookie fails (`0 succeeded, N failed`) and values export as
> **empty**, the donor uses **app-bound encryption**: the profile's
> `Local State` contains `os_crypt.app_bound_encrypted_key`, which only the
> browser's own Elevation Service can unwrap. Quitting the browser does
> **not** help — the key itself is unreachable to third parties.
> `tokenade export` now prints an explicit `[WARN] All cookie values are
> EMPTY` diagnosis in this case. Workarounds that read live values instead
> of the SQLite file:
> - **Browser extension** (`extension/`, load unpacked) — reads cookies via
>   the extension API; no decryption needed. No TLS fingerprint.
> - **CDP export** — start the browser with `--remote-debugging-port=9222`,
>   then `tokenade export --cdp-port 9222 --domains ...`.
> - **Firefox donor** — Firefox does not use Chromium app-bound encryption.
>
> > **v20 launch rule (Windows, verified on Brave 153):** when starting the
> > browser for CDP, pass *only* `--remote-debugging-port` — do **not** pass
> > `--user-data-dir` explicitly, even with the identical path. An explicit
> > user-data-dir breaks v20 app-bound decryption in the new process
> > (observed: 80 cookies → 21, tabs render logged-out homepages), while a
> > bare `--remote-debugging-port` launch yields the full warm store.
> > Related: `export --cdp-launch` snapshots are cold by nature — the store
> > populates lazily, so always pass `--domains` (or `--plugin`, which now
> > contributes its export domains) to warm the right origins.

**Solutions:**
```bash
# Linux: Install keyring support
pip install secretstorage

# Verify encryption key is accessible:
python3 -c "
from tokenade.core.crypto.cookie_crypto import CookieCryptoFactory
crypto = CookieCryptoFactory.create()
key = crypto.get_encryption_key('/path/to/browser/profile/..')
print(f'Key found: {key is not None}')
"

# If key is None, check:
# 1. Running as same user who owns the browser profile
# 2. Linux keyring daemon is running (secretservice, gnome-keyring, kwallet)
# 3. For Snap Firefox, use the profile path from the snap
```

**Prevention:** Ensure the desktop keyring service is running and unlocked before exporting.

---

### "No cookies found" / Empty export

**Symptoms:**
```
Extracted 0 cookies from Chrome
```

**Cause:** Wrong profile path, cookies were cleared, or site filter excludes all cookies.

**Solutions:**
```bash
# Verify profile path:
tokenade export --list-profiles

# Check without site filter:
tokenade export --browser-name chrome --domains ""

# For Firefox, check correct profile:
ls ~/.mozilla/firefox/  # List all profiles

# Verify cookies DB exists:
ls -la /path/to/profile/Cookies
```

**Prevention:** Use `--list-profiles` and verify the profile contains cookies for your target site.

---

## 3. CDP Proxy Issues

### Port already in use

**Symptoms:**
```
OSError: [Errno 98] Address already in use
```

**Cause:** Another process (previous Tokenade instance, Chrome, or other service) is bound to the requested port.

**Solutions:**
```bash
# Find what's using the port:
lsof -ti:9222
# Or:
ss -tlnp | grep 9222

# Kill the occupying process:
kill $(lsof -ti:9222)

# Or use a different port:
tokenade proxy -s session.tokenade --port 9223

# Kill all lingering Chromium processes:
pkill -f chromium
pkill -f chrome
```

**Prevention:** Always stop previous proxy instances cleanly with Ctrl+C. Check ports before starting.

---

### Browser launch failed (Chromium not found)

**Symptoms:**
```
Chromium browser not found. Install it with:
  playwright install chromium
```

**Cause:** Playwright browser binaries not installed.

**Solutions:**
```bash
pip install playwright
playwright install chromium

# For system Chromium (not recommended):
# Ubuntu:
sudo apt install chromium-browser
```

**Prevention:** Always run `playwright install chromium` after installing Playwright.

---

### Browser launch timeout

**Symptoms:**
```
Chromium launch timed out. The system may be under heavy load.
```

**Cause:** System under heavy memory/CPU load, or sandbox restrictions preventing browser launch.

**Solutions:**
```bash
# Try with visible browser to diagnose:
tokenade proxy -s session.tokenade --visible

# Check system resources:
free -h
top -bn1 | head -5

# Disable sandbox (if in container/Docker):
# The --no-sandbox flag is already added by default

# Reduce system load, then retry
```

**Prevention:** Ensure adequate free memory (512MB+ for Chromium). Close unused applications.

---

### Browser launch general failure

**Symptoms:**
```
Failed to launch Chromium: <error message>

Troubleshooting:
  1. Run: playwright install chromium
  2. Check disk space and memory
  3. Try: tokenade proxy -s <session> --visible
```

**Cause:** Various system-level issues preventing Chromium from starting.

**Solutions:**
```bash
# Check disk space:
df -h /tmp /home

# Check /dev/shm (Docker environments):
mount | grep shm
# If too small, increase: --shm-size=2g

# Try visible mode to see error output:
tokenade proxy -s session.tokenade --visible

# Clear Playwright cache and reinstall:
rm -rf ~/.cache/ms-playwright
playwright install chromium
```

**Prevention:** Keep sufficient disk space and memory. Reinstall Chromium if corrupted.

---

### WebSocket connection failed

**Symptoms:**
```
WebSocket connection failed
cdp_session connection lost
```

**Cause:** CDP session disconnected from the Playwright browser instance.

**Solutions:**
```bash
# Restart the proxy cleanly:
# Ctrl+C to stop, then restart

# Check if the port is available:
lsof -ti:9223  # CDP port is proxy port + 1

# If using Docker, ensure proper networking:
# The CDP port (9223 by default) must be accessible internally

# Try with --visible flag to inspect browser state:
tokenade proxy -s session.tokenade --visible
```

**Prevention:** Don't manually close the Chromium window; stop the proxy with Ctrl+C.

---

### Cookie injection failed

**Symptoms:**
```
CDP-level injection failed, falling back to context injection
```

**Cause:** CDP session not ready or browser context not properly initialized.

**Solutions:**
```bash
# This is often a warning, not fatal — the proxy falls back automatically.

# If cookies aren't working:
# 1. Verify session file has cookies:
python3 -c "
import json
with open('session.tokenade') as f:
    s = json.load(f)
print(f'Cookies: {len(s.get(\"cookies\", []))}')
"

# 2. Check cookie domains match the site:
python3 -c "
import json
with open('session.tokenade') as f:
    s = json.load(f)
for c in s['cookies'][:10]:
    print(f'  {c[\"name\"]}: {c[\"domain\"]}')
"

# 3. Re-export with fresh cookies
```

**Prevention:** Export cookies while logged into the target site in the browser.

---

### Playwright connection issues

**Symptoms:**
```
playwright._impl._errors.Error: Browser.new_context: Target crashed
```

**Cause:** Browser process crashed due to memory pressure or bug in Playwright/Chromium.

**Solutions:**
```bash
# Kill all Chromium processes:
pkill -9 -f chromium

# Reduce memory usage — use visible mode (avoids headless overhead):
tokenade proxy -s session.tokenade --visible

# Update Playwright:
pip install --upgrade playwright
playwright install chromium

# Check for core dumps:
ls /tmp/playwright-*
```

**Prevention:** Keep Playwright updated. Avoid running too many proxy instances simultaneously.

---

## 4. Legacy Proxy Issues

### Service worker registration fails

**Symptoms:**
```
Proxy fetch failed: Service Worker not registered
```

**Cause:** Browser blocks service worker registration or stale SW intercepts requests.

**Solutions:**
```bash
# Open DevTools (F12) → Application → Service Workers
# Click "Unregister" on any existing Tokenade service workers
# Hard refresh: Ctrl+Shift+R

# Or clear service worker storage:
# DevTools → Application → Storage → Clear site data → check "Service Workers"

# The CDP proxy mode doesn't use service workers:
tokenade proxy -s session.tokenade --legacy  # to NOT use legacy
```

**Prevention:** Use CDP proxy mode (default) instead of legacy mode to avoid SW issues.

---

### Duplicate header errors

**Symptoms:**
```
Failed to strip duplicate headers, returning raw data
```

**Cause:** Stale service worker injects duplicate HTTP headers.

**Solutions:**
```bash
# Tokenade auto-strips duplicates via _LenientProtocol wrapper.
# If errors persist:
# 1. Clear service workers (see above)
# 2. Restart browser
# 3. Switch to CDP mode:
tokenade proxy -s session.tokenade  # CDP is default, --legacy for service worker
```

**Prevention:** Use CDP proxy mode which doesn't rely on service workers.

---

### Content rewriting breaks pages

**Symptoms:** Pages load but images/CSS/JS are broken, or redirects fail.

**Cause:** URL rewriting in legacy proxy mode incorrectly rewrites relative/absolute URLs.

**Solutions:**
```bash
# Switch to CDP mode (no URL rewriting needed):
tokenade proxy -s session.tokenade

# In CDP mode, the browser renders everything natively — no rewriting

# If you must use legacy mode, ensure the target URL is correct:
# Open http://127.0.0.1:9222/browse and enter the full URL
```

**Prevention:** Use CDP proxy mode (default) for proper rendering without URL rewriting.

---

## 5. Forward Proxy Issues

### CONNECT tunnel failures (502 Bad Gateway)

**Symptoms:**
```
HTTP/1.1 502 Bad Gateway
CONNECT failed to target-domain.com:443: <error>
```

**Cause:** Cannot establish TCP connection to the target host.

**Error-specific causes:**
| Error | Cause |
|-------|-------|
| `DNS resolution failed` | Target hostname doesn't resolve |
| `Connection refused` | Target server rejected connection |
| `Timed out` | Network/firewall blocking connection |
| `Network is unreachable` | No route to target |

**Solutions:**
```bash
# Check DNS resolution:
nslookup target-domain.com

# Check if port is reachable:
nc -zv target-domain.com 443

# Test with verbose logging:
tokenade -v proxy -s session.tokenade --mode forward

# If DNS fails, check /etc/resolv.conf or use 8.8.8.8

# If connection refused, the target may block non-standard clients
```

**Prevention:** Verify network connectivity before starting forward proxy.

---

### SSL interception errors

**Symptoms:**
```
SSL: CERTIFICATE_VERIFY_FAILED
ssl.SSLCertVerificationError
```

**Cause:** Forward proxy uses `ssl=False` for aiohttp, but some clients verify SSL.

**Solutions:**
```bash
# The forward proxy intentionally disables SSL verification for outgoing
# connections to avoid certificate mismatch issues.

# If your browser shows SSL errors:
# 1. Configure browser to trust the proxy:
#    Chrome: --ignore-certificate-errors
#    Firefox: about:config → security.enterprise_roots.enabled = true

# 2. Or use CDP mode instead (browser handles SSL natively):
tokenade proxy -s session.tokenade
```

**Prevention:** Use CDP mode for sites with strict SSL requirements.

---

### Cookie injection not working in forward mode

**Symptoms:** Pages load but you're logged out.

**Cause:** Forward proxy injects cookies per-domain, but domain matching may miss subdomains.

**Solutions:**
```bash
# Verify cookie domains in session file:
python3 -c "
import json
with open('session.tokenade') as f:
    s = json.load(f)
for c in s['cookies']:
    print(f'  {c[\"name\"]}: domain={c[\"domain\"]}')
"

# Re-export with correct domain filtering:
tokenade export --browser-name firefox --domains "target.com,.target.com" -o session.tokenade
```

**Prevention:** Export with comprehensive domain patterns (include leading dot for wildcards).

---

## 6. Multi-Site Proxy Issues

### SharedConnectionPool errors

**Symptoms:**
```
RuntimeError: Shared session is closed
Connection pool exhausted
```

**Cause:** All connections in the shared pool are in use or the shared session was closed.

**Solutions:**
```bash
# The pool defaults to 200 max connections, 50 per host.
# If exhausted:
# 1. Reduce number of concurrent sites
# 2. Check for connection leaks (restart proxy)

# Restart cleanly:
# Ctrl+C, then restart

# If "session is closed" persists, check for race conditions:
# Ensure all proxies share the same SharedConnectionPool instance
```

**Prevention:** Don't exceed 10-15 simultaneous sites. Monitor connection usage.

---

### Tab management / proxy port conflicts

**Symptoms:**
```
OSError: [Errno 98] Address already in use
```

**Cause:** Port conflicts when multiple proxies bind to sequential ports.

**Solutions:**
```bash
# The multi-site proxy uses base_port + 1, +2, etc.
# If port 9223 is taken:
tokenade proxy --all --port 9230  # Use a different base port

# Check which ports are in use:
ss -tlnp | grep -E '922[0-9]'

# Kill lingering processes:
pkill -f "tokenade.*proxy"
```

**Prevention:** Choose a base port that has enough free sequential ports for all sessions.

---

## 7. Session Sync Issues

### Daemon not running

**Symptoms:**
```
Sync daemon not running
Failed to connect to sync daemon
```

**Cause:** The sync daemon background process was not started or has crashed.

**Solutions:**
```bash
# Start the sync daemon:
tokenade sync start

# Check if it's running:
ps aux | grep tokenade

# View sync logs:
ls ~/.tokenade/logs/sync*.log

# Run a one-time sync instead:
tokenade sync once
```

**Prevention:** Start the daemon with `tokenade sync start` and keep it running in the background.

---

### File permission errors

**Symptoms:**
```
PermissionError: [Errno 13] Permission denied: '~/.tokenade/synced/session.tokenade'
```

**Cause:** Output directory or session files have incorrect permissions.

**Solutions:**
```bash
# Fix permissions:
chmod -R 755 ~/.tokenade/synced/
chmod 600 ~/.tokenade/synced/*.tokenade

# Or recreate the directory:
rm -rf ~/.tokenade/synced
mkdir -p ~/.tokenade/synced
```

**Prevention:** Ensure `~/.tokenade/` is owned by the current user.

---

### Domain filtering too restrictive

**Symptoms:** Sync produces empty or incomplete session files.

**Cause:** Domain filter in `SiteFilter` excludes all cookies.

**Solutions:**
```bash
# Check which domains are being filtered:
python3 -c "
from tokenade.core.importer.cookie_extractor import SiteFilter
sf = SiteFilter(['google'])
print('Domains:', sf._domain_patterns)
"

# Re-run sync without domain filtering:
tokenade sync add --name mysite --domains "*.example.com"
tokenade sync once
```

**Prevention:** Use broad domain patterns. Test with `--domains "*"` first.

---

## 8. Dashboard Issues

### API connection failed

**Symptoms:** Dashboard shows "Connection failed" or "Cannot reach proxy".

**Cause:** Proxy server not running, or wrong host/port configured.

**Solutions:**
```bash
# Verify proxy is running:
curl http://127.0.0.1:9222/status

# Check proxy output — it prints the GUI URL on startup:
# GUI: http://127.0.0.1:9222

# If using non-default port:
curl http://127.0.0.1:<port>/status

# Check firewall:
ufw status  # Ubuntu
iptables -L  # General Linux
```

**Prevention:** Confirm proxy is running before accessing the dashboard.

---

### WebSocket disconnects

**Symptoms:** Dashboard shows "Disconnected" and stops updating.

**Cause:** Network interruption, proxy restart, or WebSocket timeout.

**Solutions:**
```bash
# The dashboard auto-reconnects. If not:
# 1. Refresh the page
# 2. Check proxy is still running
# 3. Check browser console for WebSocket errors

# If using a reverse proxy (nginx, etc.), configure WebSocket headers:
# proxy_set_header Upgrade $http_upgrade;
# proxy_set_header Connection "upgrade";
```

**Prevention:** Use a stable network connection. Avoid placing WebSocket services behind proxies without proper upgrade support.

---

## 9. Plugin Issues

### Plugin not loading

**Symptoms:**
```
No plugins installed
```

**Cause:** Plugin not installed or not in discovery path.

**Solutions:**
```bash
# List installed plugins:
tokenade plugin list

# Search available plugins:
tokenade plugin list --available

# Install a plugin:
tokenade plugin install <plugin-name>

# Check plugin directory:
ls ~/.tokenade/plugins/

# Debug plugin loading:
python3 -c "
from tokenade.core.integration.plugin_loader import PluginLoader
loader = PluginLoader()
plugins = loader.discover()
print(f'Found {len(plugins)} plugins')
for p in plugins:
    print(f'  {p[\"name\"]}: {p.get(\"error\", \"OK\")}')
"
```

**Prevention:** Install plugins via `tokenade plugin install` and verify with `tokenade plugin list`.

---

### Plugin registry errors

**Symptoms:**
```
PluginError: Failed to connect to plugin registry
NetworkError: Registry request timed out
```

**Cause:** Network issue reaching the plugin registry server.

**Solutions:**
```bash
# Check internet connectivity:
ping github.com

# Check if registry is accessible:
curl -s https://registry.tokenade.dev/api/plugins | head -5

# Install from local file if registry unavailable:
pip install /path/to/plugin.whl

# Or install from git:
pip install git+https://github.com/user/plugin-repo.git
```

**Prevention:** Ensure network access to the plugin registry. Cache plugins locally.

---

## 10. Performance Issues

### Slow proxy response

**Symptoms:** Pages take 10+ seconds to load, requests timeout.

**Cause:** TLS fingerprint matching overhead, network latency, or excessive cookie checking.

**Solutions:**
```bash
# Disable TLS fingerprint matching (faster, but less stealth):
# Don't use --fingerprint flag

# Increase timeout:
tokenade proxy -s session.tokenade --timeout 60

# Reduce verbose logging in production:
tokenade proxy -s session.tokenade  # without -v

# Check for network latency:
curl -w "@curl-format.txt" -o /dev/null -s https://target.com

# Monitor proxy stats:
curl http://127.0.0.1:9222/stats
```

**Prevention:** Don't use `--fingerprint` unless needed. Keep timeout reasonable.

---

### High memory usage

**Symptoms:** Proxy consumes 1GB+ RAM, system becomes sluggish.

**Cause:** Too many open browser tabs, accumulated page data, or connection leak.

**Solutions:**
```bash
# Monitor proxy memory:
ps aux | grep chromium | grep -v grep
ps aux | grep tokenade | grep -v grep

# The CDP proxy auto-cleans pages after TTL (default 1 hour)
# Restart periodically for long-running sessions:
# Ctrl+C, then restart

# Use visible mode to inspect open tabs:
tokenade proxy -s session.tokenade --visible

# Close unused browser tabs manually in visible mode
```

**Prevention:** Restart proxy periodically. Don't open excessive tabs.

---

### Connection leaks

**Symptoms:** `Too many open files` error after prolonged use.

**Cause:** aiohttp sessions or TCP connections not properly closed.

**Solutions:**
```bash
# Check file descriptor count:
ls /proc/$(pgrep -f "tokenade proxy")/fd | wc -l

# Restart proxy to clear leaked connections:
# Ctrl+C, then restart

# Monitor connection pool stats:
curl http://127.0.0.1:9222/stats

# For multi-site proxy, check shared pool:
curl http://127.0.0.1:9222/api/sessions
```

**Prevention:** Restart proxy every few hours for long-running sessions.

---

## 11. Platform-Specific Issues

### Linux: Firefox Snap profile access

**Symptoms:**
```
Firefox cookies DB not found: /snap/firefox/common/.mozilla/firefox/.../cookies.sqlite
```

**Cause:** Snap Firefox uses a different profile path and has sandbox restrictions.

**Solutions:**
```bash
# Snap Firefox profile locations:
ls /snap/firefox/common/.mozilla/firefox/
ls ~/snap/firefox/common/.mozilla/firefox/

# Export from Snap profile:
tokenade export --browser-name firefox \
  --browser-path ~/snap/firefox/common/.mozilla/firefox/*.default-release

# Or use the classic Firefox (non-Snap):
sudo snap remove firefox
sudo apt install firefox
```

**Prevention:** Use classic Firefox or specify Snap profile path explicitly.

---

### Linux: Wayland vs X11

**Symptoms:** Visible mode shows blank browser window or crashes.

**Cause:** Playwright Chromium has limited Wayland support.

**Solutions:**
```bash
# Force X11 backend:
export DISPLAY=:0
export XDG_SESSION_TYPE=x11

# Or use headless mode (default):
tokenade proxy -s session.tokenade  # headless by default

# For visible mode on Wayland, try:
tokenade proxy -s session.tokenade --visible --host 0.0.0.0
```

**Prevention:** Use headless mode on Wayland systems. Use X11 for visible mode.

---

### macOS: App translocation

**Symptoms:**
```
"Chromium" can't be opened because Apple cannot check it for malware
```

**Cause:** macOS Gate blocks unsigned or quarantined binaries.

**Solutions:**
```bash
# Remove quarantine attribute:
xattr -d com.apple.quarantine ~/Library/Caches/ms-playwright/chromium-*/chrome-linux/chrome

# Or use Playwright's bundled Chromium:
playwright install chromium
```

**Prevention:** Keep Playwright updated. macOS may prompt to allow the binary.

---

### macOS: Port conflicts with AirPlay

**Symptoms:**
```
OSError: [Errno 48] Address already in use on port 5000/7000
```

**Cause:** macOS AirPlay Receiver uses ports 5000 and 7000.

**Solutions:**
```bash
# Disable AirPlay Receiver:
# System Settings → General → AirDrop & Handoff → AirPlay Receiver → Off

# Or use a different port:
tokenade proxy -s session.tokenade --port 9222
```

**Prevention:** Use ports above 9000 to avoid AirPlay conflicts.

---

### Windows: Path length limits

**Symptoms:**
```
OSError: [WinError 206] The filename or extension is too long
```

**Cause:** Windows 260-character path limit, deep Playwright cache paths.

**Solutions:**
```bash
# Enable long paths in Windows:
# Registry: HKLM\SYSTEM\CurrentControlSet\Control\FileSystem
# Set LongPathsEnabled = 1

# Or use shorter cache directory:
set PLAYWRIGHT_BROWSERS_PATH=C:\pw
playwright install chromium
```

**Prevention:** Use short paths. Enable long path support on Windows.

---

### Docker: Shared memory too small

**Symptoms:**
```
session crashed (page crashed)
```

**Cause:** Docker default `/dev/shm` is 64MB, Chromium needs more.

**Solutions:**
```bash
# Run Docker with larger shared memory:
docker run --shm-size=2g tokenade ...

# Or in docker-compose.yml:
# shm_size: '2gb'
```

**Prevention:** Always set `--shm-size=2g` when running Chromium in Docker.

---

## 12. Error Code Reference

### Tokenade Exception Hierarchy

| Exception | Meaning |
|-----------|---------|
| `TokenadeError` | Base exception for all Tokenade errors |
| `ExtractionError` | Cookie/session extraction failed |
| `InjectionError` | Session injection into browser failed |
| `EncryptionError` | Encryption operation failed |
| `DecryptionError` | Decryption failed (wrong password, corrupted data) |
| `SessionNotFoundError` | Session file cannot be found or loaded |
| `BrowserNotFoundError` | Browser profile cannot be discovered |
| `ProxyError` | Proxy operation failed |
| `ConfigurationError` | Configuration is invalid or missing |
| `ValidationError` | Session validation failed |
| `PluginError` | Plugin loading or execution failed |
| `NetworkError` | Network operations failed |
| `FormatError` | Format conversion failed |

### Common Error Messages and Solutions

| Error Message | Cause | Solution |
|--------------|-------|----------|
| `Playwright is required for CDP proxy` | Playwright not installed | `pip install playwright && playwright install chromium` |
| `Chromium browser not found` | Chromium binary missing | `playwright install chromium` |
| `Chromium launch timed out` | System under load | Use `--visible` flag, check resources |
| `Port already in use` | Port conflict | Use `--port <different>` or kill occupying process |
| `Session file not found` | Wrong path or file missing | Check path, export session first |
| `Permission denied` | Insufficient file access | Check file ownership, don't use sudo |
| `Failed to launch Chromium` | Various launch failures | Run `playwright install chromium`, check disk/memory |
| `Database is locked` | Browser has DB locked | Close browser before exporting |
| `Decryption failed` | Wrong key or corrupted data | Install `secretstorage`, verify profile path |
| `CONNECT failed` | HTTPS tunnel failure | Check DNS, network, firewall |
| `502 Bad Gateway` | Target unreachable | Check target server, DNS resolution |
| `URL blocked: internal/private network target` | SSRF protection | Use a public URL, not localhost/private IPs |
| `CDP-level injection failed` | CDP session not ready | Warning only — falls back to context injection |
| `Session hot-reloaded failed` | Refresh callback error | Restart proxy |

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | General error (check stderr) |
| `130` | Interrupted by user (Ctrl+C) |

---

## Debug Mode

Enable verbose logging for all operations:

```bash
# CLI flag:
tokenade -v proxy -s session.tokenade
tokenade -v export --browser-name firefox

# Environment variable:
export TOKENADE_LOG_LEVEL=DEBUG
tokenade proxy -s session.tokenade

# Check logs:
ls ~/.tokenade/logs/
tail -f ~/.tokenade/logs/tokenade.log
```

## Getting Help

```bash
# General help:
tokenade --help
tokenade export --help
tokenade proxy --help

# Check version:
tokenade --version

# Validate session:
tokenade validate -d sessions/

# Check session health:
tokenade health -s session.tokenade
```

Report issues at: https://codeberg.org/mihir0209/tokenade/issues
