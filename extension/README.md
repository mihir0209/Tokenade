# Tokenade Browser Extension

Export browser sessions directly from Chrome or Firefox to Tokenade format.

## Features

- Export cookies from current tab
- Export localStorage data
- Send sessions directly to Tokenade proxy
- Password protection for exported sessions
- Context menu integration

## Installation

### Chrome

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable "Developer mode" (toggle in top right)
3. Click "Load unpacked"
4. Select the `extension/` directory
5. The Tokenade icon should appear in your toolbar

### Firefox

1. Open Firefox and navigate to `about:debugging#/runtime/this-firefox`
2. Click "Load Temporary Add-on"
3. Select `extension/manifest.json`
4. The Tokenade icon should appear in your toolbar

## Usage

### Export Session

1. Navigate to the website you want to export
2. Click the Tokenade icon in the toolbar
3. (Optional) Check "Include localStorage" if the site uses it
4. (Optional) Check "Encrypt session" and enter a password
5. Click "Export Session"
6. A `.tokenade` file will be downloaded

### Send to Proxy

1. Start the Tokenade proxy: `tokenade proxy -s session.tokenade`
2. Navigate to the website you want to export
3. Click the Tokenade icon in the toolbar
4. Enter the proxy URL (default: `http://127.0.0.1:9222`)
5. Click "Send to Proxy"
6. The session will be sent to the running proxy

### Context Menu

- Right-click on any page
- Select "Export session with Tokenade" to download
- Select "Send session to Tokenade proxy" to send directly

## API

The extension injects a `window.Tokenade` object into web pages:

```javascript
// Get cookies for current page
const cookies = await window.Tokenade.getCookies();

// Get localStorage for current page
const localStorage = await window.Tokenade.getLocalStorage();

// Send session to proxy
const result = await window.Tokenade.sendSession({
  cookies: cookies,
  localStorage: localStorage,
  site_name: 'example_com',
}, 'http://127.0.0.1:9222');
```

## Permissions

- `cookies`: Read browser cookies
- `storage`: Save extension settings
- `activeTab`: Access current tab
- `scriptInjection`: Inject content scripts

## Limitations

- Cannot read HttpOnly cookies (browser security restriction)
- localStorage may be restricted by same-origin policy
- Some sites may block extension access

## Development

1. Make changes to extension files
2. Reload the extension in `chrome://extensions/` or `about:debugging`
3. Test on a website

## Privacy

This extension:
- Does not send data to any external servers
- Only communicates with your local Tokenade proxy
- All data stays on your machine
