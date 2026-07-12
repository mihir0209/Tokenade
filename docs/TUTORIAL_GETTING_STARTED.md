# Getting Started with Tokenade

Portable browser sessions: **export** cookies from a real browser into a `.tokenade` file, then **launch** or **proxy** on another machine as that session.

Site domains and critical cookies come from **site-handler plugins** (`site_config.json` next to `plugin.json`) — not from a folder in the Tokenade repo.

---

## Install

```bash
pip install tokenade
# Python 3.10+
```

Install the Google (and optional GitHub) site handlers:

```bash
tokenade plugin install google-handler
tokenade plugin install github-handler
# Or sync all: tokenade plugin sync
tokenade export --list-handlers
```

Each handler ships with `site_config.json` (domains, critical cookies, dashboard URL).

---

## Golden path: Gmail on Brave (proven)

### 1. Quit the donor browser

Fully quit **Firefox** (or Brave/Edge). A running browser locks the cookie database.

### 2. Export with the plugin (domains from `site_config.json`)

```bash
tokenade export --list-profiles

tokenade export --browser-name firefox \
  --plugin google-handler \
  -o gmail.tokenade
```

You should see something like:

- `Using plugin: google-handler`
- `site_config.json: google (N domains)`
- `Plugin export domains: google.com, accounts.google.com, ...`
- `Auth: logged_in`

**Donor browsers for Google:** Firefox, Brave, Edge (Vivaldi: code exists, not battle-tested)
**Avoid as donor/target:** Google Chrome / Chromium / Canary

### 3. Launch into a clean Brave profile

```bash
tokenade launch \
  --browser brave \
  --session gmail.tokenade \
  --plugin google-handler \
  --url "https://mail.google.com/mail/u/0/#inbox" \
  --profile-dir /tmp/tokenade-brave-clean \
  --port 9223 \
  --visible
```

If you omit `--profile-dir`, Tokenade creates a **clean temp profile** automatically for session inject (do not inject into a dirty system profile).

**Success:** title like `Inbox (…) - you@gmail.com - Gmail` on `mail.google.com`.

### 4. Rules that matter (Google)

| Do | Don't |
|----|--------|
| Clean `--profile-dir` | Inject into your daily Chrome/Brave profile |
| Open **mail.google.com** (product URL) | Bounce through `accounts.google.com` after inject |
| Non-Chrome targets (Brave/Edge/Firefox/Vivaldi) | Chrome-family targets (usually signed out / account chooser) |
| Reuse the same `.tokenade` on multiple non-Chrome browsers/devices | Assume “one device only” |

---

## GitHub (same pattern)

```bash
# Quit Firefox first
tokenade export --browser-name firefox --plugin github-handler -o github.tokenade

tokenade launch \
  --browser brave \
  --session github.tokenade \
  --plugin github-handler \
  --url "https://github.com" \
  --profile-dir /tmp/tokenade-gh-brave \
  --port 9224 --visible
```

Domains/critical cookies come from `~/.tokenade/plugins/github-handler/site_config.json`.

---

## Alternative: CDP proxy

```bash
tokenade proxy -s gmail.tokenade
# Open the local GUI URL printed by the CLI (default port 9222)
```

Use when you want TLS-matched proxying rather than injecting into a system browser.

---

## Windows (friend laptop) — same jar

Copy `gmail.tokenade` (optionally encrypt first). On the other machine:

```powershell
pip install tokenade
# install plugins the same way, or copy ~/.tokenade/plugins

$tokenade = "$env:USERPROFILE\Downloads\gmail.tokenade"

python -m tokenade launch --browser brave --session $tokenade `
  --plugin google-handler `
  --url "https://mail.google.com/mail/u/0/#inbox" `
  --port 9223 --profile-dir "$env:TEMP\tokenade-brave-friend" --visible

# Edge also works for Google (non-Chrome Google product)
python -m tokenade launch --browser edge --session $tokenade `
  --plugin google-handler `
  --url "https://mail.google.com/mail/u/0/#inbox" `
  --port 9224 --profile-dir "$env:TEMP\tokenade-edge-friend" --visible
```

---

## Encrypt before sharing

```bash
tokenade encrypt -s gmail.tokenade -o gmail.enc.tokenade
# or at export time:
tokenade export --browser-name firefox --plugin google-handler \
  --encrypt-password '…' -o gmail.enc.tokenade
```

Treat every `.tokenade` like a password dump. **Do not commit live session files to git.**

---

## Site plugins & `site_config.json`

```
~/.tokenade/plugins/google-handler/
├── plugin.json
├── plugin.py
└── site_config.json    ← domains, critical cookies, URLs
```

```bash
tokenade export --list-handlers
tokenade plugin list
```

Authoring: [PLUGIN_DEVELOPMENT.md](PLUGIN_DEVELOPMENT.md) · schema: [SITE_CONFIGS.md](SITE_CONFIGS.md)

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `database is locked` / empty extract | Fully quit the donor browser, then export |
| Signed out / account chooser on Google | Use Brave/Edge/Firefox — not Chrome; clean `--profile-dir` |
| Plugin not found | `tokenade plugin install google-handler` |
| Wrong domains | Use `--plugin …` so `site_config.json` drives the list |
| Port in use | `--port 9224` (unique port per concurrent browser) |

More: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

---

## Next docs

- [README](../README.md) — product overview + best practices
- [SITE_CONFIGS.md](SITE_CONFIGS.md) — plugin-owned site config
- [PLUGIN_DEVELOPMENT.md](PLUGIN_DEVELOPMENT.md) — write a handler
- [API.md](API.md) — programmatic use
