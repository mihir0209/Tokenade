# Tokenade Proxy Examples

This directory contains examples demonstrating the Tokenade fingerprint proxy server.

## Prerequisites

```bash
# Install dependencies
pip install aiohttp curl-cffi

# Or install tokenade with all dependencies
pip install -e .
```

## Examples

### 1. Basic Proxy (`basic_proxy.py`)

Starts a proxy server with a sample session and opens the GUI in your browser.

```bash
python examples/basic_proxy.py
```

Then open http://127.0.0.1:9222 in your browser.

### 2. Full Workflow (`full_workflow.py`)

Demonstrates the complete workflow:
1. Export cookies from a real browser
2. Package into .tokenade format
3. Start proxy server

```bash
# Export from Firefox, proxy on port 9222
python examples/full_workflow.py --browser firefox --port 9222

# Export from Chrome with custom domain filter
python examples/full_workflow.py --browser chrome --domains ".github.com" "github.com"
```

### 3. Test Proxy (`test_proxy.py`)

Runs a test suite to verify the proxy components work correctly.

```bash
python examples/test_proxy.py
```

## Usage Modes

### GUI Mode (Default)

When you start the proxy with GUI mode enabled, it opens a web interface at http://127.0.0.1:9222 where you can:

- View session information
- Browse websites as the donor device
- Monitor request statistics

### HTTP Proxy Mode

Configure your browser or terminal to use the proxy:

```bash
# Linux/Mac
export HTTP_PROXY=http://127.0.0.1:9222
export HTTPS_PROXY=http://127.0.0.1:9222

# Windows
set HTTP_PROXY=http://127.0.0.1:9222
set HTTPS_PROXY=http://127.0.0.1:9222

# curl
curl --proxy http://127.0.0.1:9222 https://example.com
```

### CLI Usage

```bash
# Start proxy from .tokenade file
tokenade proxy --session chatgpt.tokenade --port 9222

# Start without GUI
tokenade proxy --session chatgpt.tokenade --no-gui

# Start without auto-opening browser
tokenade proxy --session chatgpt.tokenade --no-open-browser
```

## How It Works

1. **Session Loading**: The proxy loads a `.tokenade` file containing:
   - Cookies from the donor browser
   - Browser fingerprint (User-Agent, screen size, etc.)
   - TLS profile for JA3 fingerprint matching

2. **Request Interception**: When a client makes a request through the proxy:
   - The proxy replaces headers with donor-matched values
   - Injects donor cookies
   - Forwards via TLS-matched connection (curl-cffi)

3. **TLS Fingerprint Matching**: The proxy uses curl-cffi to make requests that:
   - Have the same JA3/JA4 fingerprint as the donor browser
   - Bypass Cloudflare and other anti-bot protections
   - Appear to come from the donor device

## Architecture

```
┌──────────────────────┐     HTTP/S      ┌─────────────────────────┐
│  Client Browser      │ ──────────────> │  Local Proxy            │
│  (any browser)       │ <────────────── │  127.0.0.1:9222         │
└──────────────────────┘                 │                         │
                                         │  • Donor cookies        │
                                         │  • Donor headers        │
                                         │  • Donor TLS (JA3)      │
                                         └────────────┬────────────┘
                                                      │
                                                      │ curl-cffi
                                                      ▼
                                             ┌─────────────────┐
                                             │  Remote Server   │
                                             │  sees: donor     │
                                             │  device exactly  │
                                             └─────────────────┘
```

## Troubleshooting

### Port already in use

```bash
# Find process using the port
lsof -i :9222

# Kill the process
kill -9 <PID>
```

### curl-cffi not installed

```bash
pip install curl-cffi
```

### TLS fingerprint not matching

Ensure the `.tokenade` file has a `tls_profile` section:

```json
{
  "tls_profile": {
    "browser": "chrome",
    "version": "120",
    "impersonate": "chrome120"
  }
}
```
