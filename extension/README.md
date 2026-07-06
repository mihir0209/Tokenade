# Tokenade Session Exporter — Chrome Extension

Export browser sessions as `.tokenade` files for cross-device portability.

## Installation

### From Source (Developer Mode)

1. Open Chrome and go to `chrome://extensions/`
2. Enable "Developer mode" (top right)
3. Click "Load unpacked"
4. Select this `extension/` directory
5. The Tokenade icon appears in your toolbar

### From Chrome Web Store

Coming soon.

## Usage

1. Navigate to any website where you're logged in
2. Click the Tokenade extension icon
3. See cookie count, expired count, and health score
4. Click "Download .tokenade" to save the session file
5. Transfer the file to another device
6. Use `tokenade proxy -s <file>` or `tokenade launch -s <file>` to browse

## Features

- **One-click export** — Click icon, download session
- **Domain filtering** — Auto-detects relevant cookies
- **Health scoring** — Shows cookie health (expired vs valid)
- **All-domains mode** — Option to export all cookies
- **Clipboard copy** — Copy .tokenade JSON to clipboard

## Permissions

| Permission | Why |
|-----------|-----|
| `cookies` | Read cookies for export |
| `activeTab` | Get current tab URL |
| `storage` | Store settings |
| `downloads` | Save .tokenade files |

## Development

```bash
# Load in Chrome
1. chrome://extensions/
2. Enable Developer mode
3. Load unpacked → select this directory

# Test
1. Navigate to any site
2. Click extension icon
3. Verify cookie count
4. Download and verify .tokenade format
```
