# Tokenade User Guide

Browser session portability — extract, transfer, and inject logged-in states across machines and browsers.

## Installation

```bash
pip install tokenade
```

Verify:

```bash
tokenade --version
# tokenade 1.1.53
```

This guide was verified against the published PyPI package `tokenade==1.1.53`, not an editable source checkout.

## Quick Start

```bash
# 1. Export from Firefox
tokenade export --browser-name firefox --domains "google.com,accounts.google.com" -o google.tokenade

# 2. Transfer the .tokenade file to another machine
scp google.tokenade user@newmachine:~/

# 3. Load into a stealth browser on the new machine
tokenade load --file google.tokenade
```

## Commands

### `tokenade export`

Extract cookies (and optionally localStorage) from a browser into a `.tokenade` file.

```bash
# Basic export — cookie-only sites
tokenade export --browser-name firefox --domains "github.com" -o github.tokenade

# Export with plugin (required for hard sites like Discord, Telegram)
tokenade export --browser-name firefox --plugin discord-handler -o discord.tokenade

# List available handlers
tokenade export --list-handlers

# List browser profiles found on your system
tokenade export --list-profiles
```

**`--list-handlers` output:**

```
🔌 Available site handlers (12):

   discord v1.2.0 — Site handler for Discord (discord.com, discordapp.com)
   generic v2.0.0 — Multi-site handler: cookie-simple sites via sites/*.json
   google-flow v1.0.3 — OAuth automation for labs.google/fx/tools/flow
   generic_oauth v1.0.0 — Generic OAuth2 authorization code flow with PKCE
   telegram v1.1.0 — Site handler for Telegram Web (auth in localStorage)
   ...
```

**`--list-profiles` output:**

```
📁 Found 5 profile(s):

   Browser: firefox
   Profile: default
   Path: /home/user/snap/firefox/common/.mozilla/firefox/xxxx.default

   Browser: brave
   Profile: Default
   Path: /home/user/.config/BraveSoftware/Brave-Browser/Default
```

### `tokenade load`

Load a `.tokenade` session file into a browser (CloakBrowser by default).

```bash
# Headless (default)
tokenade load --file session.tokenade

# Visible window
tokenade load --file session.tokenade --visible

# With validation after injection
tokenade load --file session.tokenade --validate

# With specific stealth level
tokenade load --file session.tokenade --stealth-level maximum
```

### `tokenade validate`

Validate session files in a directory.

```bash
tokenade validate -d ~/sessions/
```

**Output:**

```
================================================================================
TOKENADE - Session Validation
================================================================================

📁 Checking: chatgpt.tokenade
   ✅ 33 cookies
   ✅ Status: logged_in

📁 Checking: discord.tokenade
   ✅ 9 cookies
   ✅ Status: logged_in

📁 Checking: github.tokenade
   ✅ 9 cookies
   ✅ Status: logged_in

📁 Checking: google.tokenade
   ✅ 177 cookies
   ✅ Status: logged_in

📁 Checking: telegram.tokenade
   ⚠️  No cookies
   ⚠️  Status: logged_out

📊 Summary: 6 valid, 1 invalid
```

### `tokenade health`

Check session health with scoring.

```bash
# Single session
tokenade health -s session.tokenade

# All sessions in a directory
tokenade health -d ~/sessions/
```

**Output:**

```
================================================================================
TOKENADE - Session Health Check
================================================================================

📁 Checking: discord-fixed.tokenade
Status: ✅ HEALTHY
Health Score: 100.0%

📁 Checking: discord.tokenade
Status: ❌ UNHEALTHY
Health Score: 88.9%
Issues:
  • 1 expired cookies
Recommendations:
  • Re-export session from browser

📁 Checking: github.tokenade
Status: ✅ HEALTHY
Health Score: 100.0%

📁 Checking: google.tokenade
Status: ❌ UNHEALTHY
Health Score: 99.4%
Issues:
  • 1 expired cookies

================================================================================
SUMMARY: 2 healthy, 5 unhealthy
```

### `tokenade encrypt` / `tokenade decrypt`

Encrypt a session file for safe transport.

```bash
# Encrypt
tokenade encrypt -i session.tokenade -o session.tokenade.enc -p "my-secret"

# Decrypt
tokenade decrypt -i session.tokenade.enc -o session.tokenade -p "my-secret"
```

**Output:**

```
✅ Encrypted successfully
   Output: session.tokenade.enc
   Size: 55216 -> 55282 bytes

✅ Decrypted successfully
   Output: session.tokenade
   Size: 55282 -> 55216 bytes
```

### `tokenade sessions`

Manage multiple sessions.

```bash
# List all sessions in a directory
tokenade sessions list -d ~/sessions/
```

**Output:**

```
======================================================================
Site                 Cookies    Browser      Size       Path
======================================================================
discord              7          firefox      3.0K       discord-fixed.tokenade
discord              9          firefox      53.9K      discord.tokenade
github               9          firefox      2.9K       github.tokenade
google               177        firefox      62.5K      google.tokenade
openai               33         firefox      18.1K      chatgpt.tokenade
unknown              2          firefox      22.6K      telegram_web.tokenade
unknown              0          firefox      22.1K      telegram.tokenade

======================================================================
Total: 7 sessions
======================================================================
```

### `tokenade recommend`

Get recommendations for which plugin, browser, and site to use.

```bash
# By URL
tokenade recommend --url https://discord.com

# By session file
tokenade recommend --session discord.tokenade
```

**Output:**

```
  site:     discord
  plugin:   discord-handler
  browser:  cloak
  confidence: 0.80

  reasons:
    - site matched from URL host: 'https://discord.com'
    - plugin = 'discord-handler' (site_config.preferred_plugin)
    - browser = 'cloak'
    - per-site override (discord -> cloak)
```

### `tokenade diff`

Compare two session files.

```bash
tokenade diff session_a.tokenade session_b.tokenade
```

**Output:**

```
======================================================================
SESSION COMPARISON
======================================================================

  A: /path/to/discord.tokenade
  B: /path/to/discord-fixed.tokenade

  ──────────────────────────────────────────────────
  Cookies only in A: 1
  Cookies modified: 3
  Metadata differences: ['created_at']
```

### `tokenade plugin`

Manage site handler plugins.

```bash
# List installed plugins
tokenade plugin list

# Test a plugin's contract
tokenade plugin test discord-handler

# Install a plugin
tokenade plugin install discord-handler

# Install all official plugins
tokenade plugin sync

# Search marketplace
tokenade plugin search telegram
```

Recommended first-time setup:

```bash
rm -rf ~/.tokenade/plugins
tokenade plugin sync
tokenade plugin list
```

If GitHub's `main` raw-content cache is stale immediately after a marketplace update, add a pinned GitHub registry for the current commit and install from it:

```bash
tokenade plugin registry add github-current \
  https://raw.githubusercontent.com/mihir0209/tokenade-plugins/<commit-sha>

tokenade plugin install discord-handler --registry github-current
```

**`plugin list` output:**

```
📦 Installed plugins:
   • auto-refresh v1.2.0 (session_refresh) — CloakBrowser live session revalidation
   • bulk-export v1.0.0 (export_format) — Export all sessions from all browsers
   • cookie-export v1.1.0 (export_format) — Multi-format cookie export
   • discord-handler v1.2.0 (handler) — Site handler for Discord
   • generic-handler v2.0.0 (handler) — Multi-site handler: chatgpt, github, google, reddit
   • google-flow-handler v1.0.3 (handler) — OAuth automation for labs.google
   • oauth-flow-handler v1.0.0 (handler) — Generic OAuth2 with PKCE
   • oauth2 v1.2.0 (session_refresh) — OAuth2 token refresh
   • proxy-health v1.0.0 (proxy) — Monitor proxy health
   • proxy-rotate v1.1.0 (proxy) — Rotating proxy support
   • session-backup v1.0.1 (handler) — Auto-backup with rotation
   • session-encrypt v1.2.0 (session_refresh) — AES-256-GCM encryption
   • session-expiry-alert v1.0.0 (notification) — Expiry alerts
   • session-merge v1.0.0 (handler) — Merge duplicate sessions
   • session-share v1.1.0 (session_refresh) — Encrypted URL/QR sharing
   • telegram-handler v1.1.0 (handler) — Site handler for Telegram Web
   • webhook-notify v1.2.0 (notification) — Webhook notifications

📦 Loaded 17/17 plugins
```

**`plugin test` output:**

```
Results: 10 passed, 0 failed
```

### `tokenade cloak`

CloakBrowser stealth browser management.

```bash
# Show CloakBrowser status
tokenade cloak info

# Install/update CloakBrowser binary
tokenade cloak install
```

**`cloak info` output:**

```
============================================================
CLOAKBROWSER STATUS
============================================================
  Package installed: Yes
  Binary installed:  Yes
  Binary version:    146.0.7680.177.5
  Platform:          linux-x64
  License tier:      free
  Binary path:       /home/user/.cloakbrowser/chromium-146.0.7680.177.5/chrome
============================================================
```

### `tokenade launch`

Launch a browser with session injection.

```bash
# Launch CloakBrowser (default)
tokenade launch

# Launch with session injection
tokenade launch --session session.tokenade

# Launch visible with a specific URL
tokenade launch --visible --url https://discord.com
```

### `tokenade test`

Run portability tests against a session file.

```bash
tokenade test -s session.tokenade
```

`tokenade test` uses saved browser fingerprints. If no default fingerprint exists yet, the command resolves the handler correctly but reports the missing fingerprint:

```
⚠️  Using legacy handler DiscordSiteHandlerLegacyHandler (prefer site plugins + site_config.json for new work)
PORTABILITY TEST REPORT
Total Tests: 1
   Error: Target fingerprint not found: default
```

Create or collect a fingerprint first:

```bash
tokenade fingerprint collect --name default --profile-dir <browser-profile-dir>
tokenade test -s session.tokenade --target-fp default
```

### Other Commands

| Command | Description |
|---------|-------------|
| `tokenade inject-profile` | Inject cookies directly into browser profile |
| `tokenade refresh` | Refresh session from source browser |
| `tokenade batch-export` | Export multiple sites at once |
| `tokenade batch-load` | Load multiple sessions |
| `tokenade share` | Create shareable session link or QR code |
| `tokenade unshare` | Revoke a shared session |
| `tokenade import` | Import a shared session from URL |
| `tokenade proxy` | Start CDP proxy with donor session |
| `tokenade monitor` | Monitor session health in real-time |
| `tokenade analytics` | Session usage analytics |
| `tokenade completion` | Generate shell completion scripts |
| `tokenade refresh-oauth` | Refresh OAuth tokens |
| `tokenade daemon` | Auto-refresh daemon (background) |
| `tokenade versions` | Session versioning |
| `tokenade rollback` | Rollback session to a version |
| `tokenade logs` | View structured logs |
| `tokenade serve` | Start API server |

## Plugin Types

| Type | Description | Example |
|------|-------------|---------|
| `handler` | Site-specific extraction/injection | discord-handler, telegram-handler |
| `session_refresh` | Token refresh logic | auto-refresh, oauth2, session-encrypt |
| `notification` | Expiry alerts, webhooks | session-expiry-alert, webhook-notify |
| `proxy` | Proxy rotation, health | proxy-health, proxy-rotate |
| `export_format` | Custom export formats | bulk-export, cookie-export |

## Configuration

Config file: `~/.tokenade/config.yaml`

```yaml
automation_browser: cloak     # default browser for automation
default_browser: firefox      # browser to export from
plugin_dir: ~/.tokenade/plugins
```

## Supported Sites

### Cookie-Simple (via `generic-handler`)

- ChatGPT / OpenAI
- GitHub
- Google (basic export)
- Reddit

### Hard Sites (dedicated handlers)

- **Discord** (`discord-handler` v1.2.0) — uses localStorage token
- **Telegram** (`telegram-handler` v1.1.0) — uses localStorage auth keys

### OAuth Sites

- Google OAuth (`google-flow-handler` v1.0.3)
- Generic OAuth2 (`oauth-flow-handler` v1.0.0)

## Troubleshooting

**"Browser is running" error during export:**
Close the browser before exporting, or use CDP mode.

**Plugin not found:**
```bash
tokenade plugin install <plugin-name>
```

**Session marked unhealthy:**
Re-export from the browser. Expired cookies reduce health score.

**Handler not found for site:**
```bash
tokenade recommend --url https://yoursite.com
```
This tells you which plugin to install.

## Python API

```python
from tokenade.core.recommend import recommend_site, recommend_plugin, recommend_browser

# Get recommendation
result = recommend_site(url="https://discord.com")
print(result.site)       # "discord"
print(result.plugin)     # "discord-handler"
print(result.browser)    # "cloak"
```

## License

MIT License
