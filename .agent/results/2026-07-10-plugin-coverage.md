# Plugin coverage & override behavior

**Date:** 2026-07-10  
**Install root:** `~/.tokenade/plugins`  
**Loaded:** 22 plugins

## Override principle (required)

Site / feature plugins must **override** the default worker when they match:

| Flow | Default worker | Plugin override |
|------|----------------|-----------------|
| `export` | SQLite extract + user `--domains` | Handler `get_export_domains()` when `--plugin` or auto-match; `generic-handler` does **not** win over specific handlers |
| `launch` | CDP inject + user `--url` | Handler `get_dashboard_url()`, cookie filter, forced via `--plugin` |
| `refresh-browser` / accounts | Browser refresh | `session_refresh` plugins (`--plugin oauth2`, etc.) |

### Fixes verified this run

- `PluginExporter.find_handler()` prefers specific site handlers over `generic-handler` (`can_handle` always true).  
- `export --plugin google-handler` prints override + uses plugin domain list (243 cookies vs generic domain filter).  
- `launch --plugin google-handler` uses plugin dashboard URL (`https://mail.google.com`) + filter; Brave inbox OK.

## Site handlers (coverage)

| Plugin | Domains / sites | Notes |
|--------|-----------------|-------|
| **google-handler** v2.0 | google.com, accounts, mail, drive, docs, youtube | Export domains, critical cookies, dashboard → Gmail; **tested** export+launch |
| **github-handler** v1.1 | github.com, gist | Site-specific |
| **discord-handler** v1.1 | discord.com, discordapp.com | Site-specific |
| **reddit-handler** v1.0 | reddit.com, old.reddit.com | Site-specific |
| **telegram-handler** v1.0 | Telegram Web (localStorage auth) | Storage-heavy |
| **generic-handler** v1.1 | *any* URL | Fallback only; must not override specific handlers |

**Gaps (no dedicated site plugin yet):** ChatGPT/OpenAI, WhatsApp Web, LinkedIn, Microsoft/Outlook, Slack, X/Twitter, Facebook, Instagram, etc. (may still work via generic domains + site_configs).

## Feature / functionality plugins

| Plugin | Type | Role |
|--------|------|------|
| **cookie-export** | export_format | Netscape / JSON / curl cookie dumps |
| **bulk-export** | handler | Export all browsers/sessions at once |
| **session-health** | validator | Health scoring / expiry signals |
| **session-encrypt** | session_refresh | AES-GCM at-rest helpers |
| **session-share** | session_refresh | Share links / QR |
| **session-backup** | handler | Encrypted archive rotation |
| **session-merge** | handler | Merge jars for same site |
| **session-expiry-alert** | handler | Expiry alerts |
| **auto-refresh** | session_refresh | Daemon-oriented refresh helper |
| **multi-account** | session_refresh | Parallel multi-account refresh |
| **oauth2** | session_refresh | OAuth2 refresh (Google/GitHub/Microsoft providers) |
| **proxy-rotate** | session_refresh | Proxy rotation during refresh |
| **proxy-health** | handler | Proxy health monitoring |
| **webhook-notify** | session_refresh | Webhooks on refresh/expiry/error |
| **browser-stealth** | handler | JS stealth overrides (typed as handler today) |
| **fingerprint-rotate** | handler | Fingerprint rotation between sessions |

## Built-in base classes (today)

From `tokenade.plugin` / loader types:

- `SiteHandlerPlugin` — sites (extract/inject/validate + export domains)  
- Export format plugins  
- Validator plugins  
- Session refresh plugins  
- Stealth / proxy / captcha / notification hooks (registry exists; marketplace depth varies)

## Future (not built yet)

User direction: more base classes for **non-site** features (fleet, storage backends, auth strategies, CI gates, etc.) so the ecosystem is not only “one plugin per website”.

## Commands

```bash
tokenade export --list-handlers
tokenade export --browser-name firefox --plugin google-handler -o gmail.tokenade
tokenade launch -b brave -s gmail.tokenade --plugin google-handler --profile-dir /tmp/t-clean --visible
tokenade plugin list   # if available in installed CLI
```
