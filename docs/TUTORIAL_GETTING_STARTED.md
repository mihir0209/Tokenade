# Getting Started with Tokenade

## What is Tokenade?

Tokenade extracts browser sessions from one device, packages them into portable `.tokenade` files, and lets you browse as the donor on another device using a CDP reverse proxy with TLS fingerprint matching.

## Installation

```bash
pip install tokenade
playwright install chromium --with-deps
```

## Quick Start (3 commands)

### Step 1 — Export cookies from your browser

```bash
# See what browsers are installed
tokenade export --list-profiles

# Export ChatGPT session from Firefox
tokenade export --browser-name firefox --domains "chatgpt.com,openai.com" -o chatgpt.tokenade

# Export Gmail session from Chrome
tokenade export --browser-name chrome --domains "google.com,accounts.google.com" -o gmail.tokenade
```

### Step 2 — Start the proxy

```bash
# Start CDP proxy (default — recommended)
tokenade proxy -s chatgpt.tokenade

# Custom port, visible browser
tokenade proxy -s gmail.tokenade --port 8080 --visible
```

### Step 3 — Browse

Open `http://127.0.0.1:9222`, enter the target URL, and click Browse.

You're now browsing as the donor user.

## Key Concepts

### Session Files (.tokenade)

A `.tokenade` file contains:
- **Cookies** — All session cookies from the browser
- **Fingerprint** — Browser user agent, platform, language
- **TLS Profile** — Browser version for TLS fingerprint matching
- **Metadata** — Site name, auth status, creation time

### CDP Proxy

The proxy intercepts all browser requests and forwards them with the donor's TLS fingerprint. This bypasses Cloudflare, DataDome, and other anti-bot systems.

### TLS Fingerprint Matching

curl-cffi impersonates Chrome's TLS handshake (JA3 hash), so servers see the donor's fingerprint, not yours.

## Common Tasks

### Check Session Health

```bash
tokenade health -s session.tokenade
```

### Encrypt Session Files

```bash
tokenade encrypt -s session.tokenade -o encrypted.tokenade
tokenade decrypt -s encrypted.tokenade -o session.tokenade
```

### Share Sessions

```bash
# Create password-protected share link
tokenade share -s session.tokenade --password mypassword --expiry 48

# Generate QR code for mobile
tokenade share -s session.tokenade --format qr -o qr.png
```

### Multi-Site Mode

```bash
# Serve multiple sessions with tabbed GUI
tokenade proxy --all -d ./sessions/
```

## Troubleshooting

### "No browser profiles found"

Make sure your browser is installed and has been used at least once. Tokenade looks for browser profiles in standard locations.

### "Proxy failed — check port is available"

Another process is using the port. Try a different port:
```bash
tokenade proxy -s session.tokenade --port 9223
```

### "Extraction failed"

- Close the browser before extracting (or use a copy of the profile)
- Make sure you have read access to the browser profile directory

## Next Steps

- [Plugin Development](PLUGIN_DEV.md) — Create custom handlers and validators
- [Enterprise Deployment](ENTERPRISE.md) — Audit logging, RBAC, LDAP
- [API Reference](API.md) — REST API and Python SDK
