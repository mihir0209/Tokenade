# Tokenade browser extension (experimental)

Export the **active tab’s** cookies (and optional page `localStorage`) as a portable session file.

**Default format: `.tokenade`** — the same JSON session jar the CLI uses (richest option we ship).  
You can also export Cookie-Editor-style JSON or a Netscape jar for other tools.

## Status (honest)

| Capability | Status |
|------------|--------|
| Cookies for current site / all sites | **Works** (Chrome `cookies` API, includes HttpOnly) |
| Optional `localStorage` for the **current tab origin** | **Works** when enabled (`scripting` + active tab) |
| Download / clipboard | **Works** |
| Default export = `.tokenade` v3-shaped | **Works** |
| Cookie-Editor / Netscape alternate formats | **Works** |
| Donor **TLS fingerprint** / JA3 | **Not available** in an extension — use CLI `tokenade export --collect-fingerprint` |
| Full multi-origin storage map like CLI `--full` + site handlers | **Partial** — only the open tab’s origin unless you visit others |
| Firefox / Safari store listing | **Not shipped** — load unpacked Chromium-family for now |
| Chrome Web Store | **Not published** |

This path is under active polish (~days, not a finished product surface). Prefer CLI/TUI export when you need fingerprints, multi-profile SQLite dumps, or site-handler storage origins.

## Why use the extension vs CLI?

| | Extension | CLI `tokenade export` |
|--|-----------|------------------------|
| Browser must be quit? | **No** — reads live cookies | **Usually yes** — SQLite lock if browser holds the DB |
| Fingerprint in jar | **No** | Optional (`--collect-fingerprint`) |
| Site-handler origins | **No** | **Yes** (`--plugin …`) |
| Best when… | Quick grab while logged in | Full portable jar + stealth/TLS later |

Convert foreign dumps (Cookie-Editor, Playwright, HAR, …) with:

```bash
tokenade convert -i cookies.json -o session.tokenade
# or TUI → Convert tab
```

## Install (developer mode)

1. Chromium / Chrome / Brave / Edge → `chrome://extensions/`
2. Enable **Developer mode**
3. **Load unpacked** → select this `extension/` directory
4. Pin the Tokenade icon; open a normal https tab (not `chrome://`)

## Usage

1. Log into the site in a normal tab  
2. Click the extension icon  
3. Leave format on **`.tokenade (recommended)`** unless you need another tool’s format  
4. Optionally enable **all domains** or **localStorage**  
5. **Download** or **Copy**  
6. On another machine: `tokenade load --file site.tokenade` or `tokenade launch -s site.tokenade`

## Permissions

| Permission | Why |
|------------|-----|
| `cookies` | Read cookies (including HttpOnly) |
| `activeTab` | Current tab URL / scripting |
| `scripting` | Optional `localStorage` from the page |
| `storage` | Reserved for settings |
| `downloads` | Save export files |

## Development

Reload the extension from `chrome://extensions` after edits. No build step.

Related CLI: `tokenade convert`, `tokenade tui` (Convert tab), `docs/USER_GUIDE.md`.
