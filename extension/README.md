# Tokenade browser extension (v1.4)

Export and inject portable `.tokenade` sessions directly from the browser with native WebCrypto AES-256-GCM encryption.

**Default format: `.tokenade`** — the native session jar used across the Tokenade ecosystem. You can also export/import Cookie-Editor JSON and Netscape cookie jars.

## Capabilities

| Capability | Status | Notes |
|------------|--------|-------|
| **Export active session** | **Works** | Captures cookies (incl. HttpOnly), localStorage, and sessionStorage |
| **Inject / Import session** | **Works** | Injects `.tokenade` (plaintext or encrypted) into active browser with clean-inject & auto-reload |
| **AES-256-GCM Encryption** | **Works** | Built-in WebCrypto PBKDF2-SHA256 (600k iterations) compatible with `tokenade encrypt/decrypt` |
| **Cookie Inspector** | **Works** | Live searchable cookie table with `SEC`, `HTTP`, and `SameSite` security flags |
| **Known Site Detection** | **Works** | Badges & critical cookie diagnostics for Google, Discord, Telegram, X (Twitter), GitHub, ChatGPT |
| **Proxy Bridge** | **Works** | Sends live session to local Tokenade Proxy Gateway (`http://127.0.0.1:9222`) |
| **Donor TLS fingerprint** | **Not available** | Browser extension API cannot forge TLS handshakes — use CLI `export --collect-fingerprint` |

## Workspace Tabs

1. **Export (📤)**: Extract cookies and storage from the active tab or all browser domains. Select format (`.tokenade`, Cookie-Editor, Netscape) and optionally specify a password for AES-256-GCM encryption.
2. **Inject (📥)**: Drag-and-drop or select any `.tokenade` or JSON cookie file to inject into the active browser tab. If encrypted, prompts for decryption password. Supports clean domain injection and auto-reload.
3. **Inspect (🔍)**: Search, view, and copy active domain cookies with expiration, HttpOnly, Secure, and SameSite tags.
4. **Settings (⚙️)**: Configure Tokenade Proxy Gateway bridge, switch themes (Dark, Light, System), and manage saved preferences.

## Install (Developer mode)

1. Open `chrome://extensions/` in Chrome / Brave / Edge / Vivaldi.
2. Enable **Developer mode** (top-right toggle).
3. Click **Load unpacked** and select the `extension/` directory.
4. Pin the Tokenade icon to your toolbar.

## Store Packaging

To generate ready-to-submit store packages for Chrome Web Store (`.zip`) and Firefox AMO (`.xpi`):

```bash
tokenade extension bundle --source-dir extension --out-dir dist/extension --target all
```

Related CLI: `tokenade convert`, `tokenade load`, `tokenade encrypt`, `docs/USER_GUIDE.md`.
