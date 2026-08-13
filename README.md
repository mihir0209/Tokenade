# Tokenade

<p align="center">
  <img src="docs/assets/banner.png" alt="Tokenade — portable browser sessions" width="920"/>
</p>

**Portable browser sessions.** Export cookies (and storage) from a real browser into a `.tokenade` file, then launch or proxy on another machine as that session — with TLS fingerprint matching where it matters.

[![PyPI version](https://img.shields.io/pypi/v/tokenade.svg)](https://pypi.org/project/tokenade/)
[![Python versions](https://img.shields.io/pypi/pyversions/tokenade.svg)](https://pypi.org/project/tokenade/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Downloads](https://static.pepy.tech/badge/tokenade/month)](https://pepy.tech/projects/tokenade)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

```bash
pip install tokenade
tokenade plugin sync
tokenade export --browser-name firefox --plugin discord-handler -o discord.tokenade
tokenade load --file discord.tokenade
```

> **Not a Multilogin / AdsPower replacement.** Tokenade is session **portability** (export → package → inject / proxy), not a full anti-detect browser product. Stealth is best-effort and measured — never “undetectable.”

<p align="center">
  <img src="docs/assets/logo.png" alt="Tokenade logo" width="120"/>
</p>

---

```bash
pip install 'tokenade[tui]'
tokenade tui
```

---

## Why Tokenade?

| You need… | Tokenade |
|-----------|----------|
| Move a logged-in session to another device | Export → `.tokenade` → launch or proxy |
| Keep cookies + localStorage (e.g. Telegram Web) | Full / ecosystem packaging |
| Match donor TLS on proxied traffic | CDP proxy + `curl-cffi` |
| Encrypt session files at rest | AES-256-GCM (`encrypt` / export password) |
| Extend behavior per site | Site-handler plugins (`--plugin google-handler`) |
| Interactive terminal UI | `tokenade tui` (optional extra) |
| Grab session while browser stays open | Browser extension (cookies; no fingerprint) |
| Import Cookie-Editor / Playwright / HAR dumps | `tokenade convert` or TUI **Convert** tab |
| Share a jar without a shared filesystem | `tokenade share-url` (password + optional short id) |
| In-process proxy from Python | `TokenadeClient.start_proxy(...)` / `SessionProxy` |

Self-hosted CLI. No cloud account required for the core loop.

### Why a `.tokenade` file (not raw cookies)?

Cookie dumps (Cookie-Editor JSON, Netscape, `Set-Cookie` headers, even Playwright `storageState`) are **partial** session views. Tokenade’s native jar is the **most mature, first-class format** in this project because a real login is more than a name/value list:

| Concern | Loose cookie dump | `.tokenade` |
|---------|-------------------|-------------|
| **Where to open the site** | Often missing — you guess the product URL from domains | Site / handler metadata + export path keep **product URL** intent |
| **Multi-origin storage** | Rarely complete (one tab origin, or cookies only) | Handlers declare **storage origins** (Discord, Telegram Web, …) |
| **Auth shape** | Flat list; no auth status / packaging version | Packaged session with cookies, tokens, storage, optional fingerprint |
| **Cross-tool round-trip** | Each vendor schema differs | **Convert in**, load/launch/proxy/share **out** of one format |
| **At-rest safety** | Usually plaintext JSON | Optional **AES-256-GCM** encrypt / rekey on the same file type |
| **Ops** | Ad-hoc scripts per dump type | One CLI/TUI/SDK surface: health, refresh, share-url, gateway routing |

**Honest limits:** a `.tokenade` is still only as good as the export path (CLI SQLite > extension live cookies > foreign convert). It is **not** a Multilogin profile and does not invent TLS fingerprints the donor never had.

---

## Work in progress (experimental · ~3–4 days)

These surfaces **exist and run**, but are still being hardened. Expect rough edges; core CLI export/load/share remains the stable path.

| Area | What’s real today | Still unfinished |
|------|-------------------|------------------|
| **TUI** (`tokenade tui`) | Export, Sessions, Share, Convert (file tree), Gateway, Vault/Sync, plugins, Settings | Polish and broader QA on Windows terminals |
| **Convert** | JSON, Netscape, curl, Playwright, Puppeteer, Cookie-Editor, Cypress, Selenium, Cookie/Set-Cookie headers, HAR, CSV → `.tokenade` | More exotic vendor dumps as they show up |
| **Browser extension** (`extension/`) | Live cookie export, optional tab `localStorage`, default **`.tokenade`**, Cookie-Editor/Netscape alts | Store publish, Firefox packaging, multi-origin storage parity with CLI handlers |
| **Chromium forks in CLI** | Vivaldi/Opera cookie path allowlisted | Full multi-profile battle-testing |

Install TUI when you want it:

```bash
pip install 'tokenade[tui]'
tokenade tui
```

If Textual is missing, `tokenade tui` exits with a clear `pip install 'tokenade[tui]'` message (non-zero exit).

---

## Quick start

### 1. Install

```bash
pip install tokenade
# Python 3.10+
```

Optional extras: `tokenade[tui]` (Textual UI), `tokenade[enterprise]` (LDAP — experimental).

Platform cookie backends (`pywin32` on Windows, `secretstorage` on Linux) install automatically with the core package via environment markers — no `[windows]` / `[linux]` extra required (those extras remain as no-op aliases for older scripts).

### 2. Install site plugins + export a session

```bash
tokenade plugin sync
tokenade export --list-handlers
tokenade export --list-profiles
```

**Three honest export paths** (pick one):

| Path | When | Caveat |
|------|------|--------|
| **CLI SQLite** `tokenade export --browser-name …` | Full profile + optional fingerprint + site handlers | Prefer **fully quitting** the browser so the cookie DB is not locked |
| **Extension** (`extension/`, load unpacked) | Browser stays open; quick `.tokenade` from the active tab | **No TLS fingerprint**; storage is current-tab origin only |
| **Convert** `tokenade convert -i dump.json` | You already have Cookie-Editor / Playwright / HAR / Netscape | Quality depends on the dump; not a live browser read |

```bash
# CLI — hard sites use dedicated handlers (storage origins included)
tokenade export --browser-name firefox --plugin discord-handler -o discord.tokenade

# Foreign cookie dump → .tokenade
tokenade convert -i ~/Downloads/cookies.json -o session.tokenade

# Interactive UI (after pip install 'tokenade[tui]')
tokenade tui
```

### 3. Use the session

**Load** into CloakBrowser (default automation backend):

```bash
tokenade load --file discord.tokenade
```

Show a browser window when needed:

```bash
tokenade load --file discord.tokenade --visible
```

**Proxy** (CDP reverse proxy with optional TLS impersonation):

```bash
tokenade proxy -s gmail.tokenade
# Open the local GUI / URL printed by the CLI (default port 9222)
```

**Programmatic proxy** (same stack, no second CLI process) — see [`USE-CASES.md`](USE-CASES.md):

```python
from tokenade.sdk import TokenadeClient

with TokenadeClient().start_proxy("gmail.tokenade", port=9222) as proxy:
    print(proxy.base_url)  # point scrapers / tools here
```

**Encrypt** sensitive jars before sharing or storing:

```bash
tokenade encrypt -i discord.tokenade -o discord.tokenade.enc -p "my-secret"
# or: tokenade export ... --encrypt-password '…'
```

Full command list: `tokenade --help` and `tokenade <command> -h`. Start with [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md); release hardening work is tracked in [`docs/RELEASE_HARDENING.md`](docs/RELEASE_HARDENING.md).

Mature Vault and peer Sync workflows are documented in
[`docs/VAULT_SYNC.md`](docs/VAULT_SYNC.md).

---

## What works (evidence-based)

| Capability | Status | Notes |
|------------|--------|-------|
| Cookie export (Chrome / Firefox / Brave / Edge) | **Works** | SQLite; quit browser if DB locked |
| Vivaldi / Opera cookie export | **Works** | Chromium-fork path; less field time than Chrome/Firefox |
| Load + inject via CloakBrowser | **Works** | `tokenade load --file session.tokenade` |
| Google: Firefox/Brave/Edge donor → non-Chrome target | **Works** | Multi-browser & multi-device verified (2026-07-10) |
| Google → **Chrome / Chromium** target | **Fails** | Account chooser / signed out; avoid Google-owned browsers |
| CDP proxy + session inject (Gmail, ChatGPT) | **Works** | Confirmed logged-in in real runs |
| localStorage (Discord, Telegram Web) | **Works** | Handler-declared storage origins on CLI export |
| AES-256-GCM session encryption | **Works** | Core encryptor, PBKDF2 |
| Session health scoring | **Works** | Heuristic on cookies — not live auth proof |
| TLS fingerprint matching (`curl-cffi`) | **Works** | Core dependency; use thoughtfully with `cf_clearance` |
| `tokenade convert` multi-format → `.tokenade` | **Works** | Industry dumps; see `tokenade convert -h` |
| TUI (`tokenade[tui]`) | **Works (experimental)** | Full tabs incl. Convert file picker; polish ongoing |
| Browser extension → `.tokenade` | **Works (experimental)** | Live cookies; no fingerprint; see `extension/README.md` |
| Hard bot labs / Cloudflare Turnstile | **Often fails** | Do not market as Grade A bypass |
| Enterprise LDAP / fleet / K8s generators | **Code present** | Not production-hardened product surfaces |

GitHub/Discord/Reddit from **session-only** cookies often fail when the donor never wrote durable auth cookies to disk.

---

## Core workflows

```
┌──────────────┐     export      ┌────────────────┐     launch / proxy
│ Donor browser│ ──────────────► │ .tokenade file │ ──────────────────► Target
│ (logged in)  │  cookies (+LS) │  portable jar  │  clean profile or CDP
└──────────────┘                 └────────────────┘
```

1. **Export** — read cookies and handler-declared storage from a real profile; package as `.tokenade`.
2. **Transfer** — copy the file (optionally encrypted) to another machine or process.
3. **Replay** — `load` (CloakBrowser + inject), `launch` (system browser + inject), or `proxy` (TLS-matched reverse proxy).

**Google recipe (verified):** donor **not** Chrome → target **Brave / Edge / Firefox** → **clean** `--profile-dir` → open the **product URL** (e.g. `mail.google.com`), not `accounts.google.com` after inject. Same jar can run on multiple non-Chrome browsers/devices concurrently. Vivaldi is code-supported but not battle-tested.

---

## Best practices

These matter more than flag trivia. Follow them and most “broken session” reports go away.

### Export

1. **Choose the right export path (honest tradeoffs).**
   - **CLI SQLite export:** richest jar (handlers, multi-origin storage, optional `--collect-fingerprint`). **Quit the donor browser first** when the cookie DB is locked (`database is locked` / partial dump). “Quit” means no residual process (Task Manager / `pgrep`).
   - **Browser extension:** best when you must stay logged-in in a live window. Default download is **`.tokenade`**. **Downside:** no donor TLS fingerprint and only the open tab’s `localStorage` (unless you broaden domains). For fingerprint-sensitive proxy later, re-export via CLI or accept missing `fingerprint` in metadata.
   - **Convert:** use when cookies already left the browser (Cookie-Editor, Playwright `storageState`, HAR, Netscape). Default goal is still a `.tokenade` session file.
2. **Export only the domains you need** (`--domains` or a site plugin). Smaller jars are easier to reason about and safer to share (and under share-url size caps).
3. **Prefer a stable donor** for high-value accounts. For Google, prefer Firefox / Brave / Edge — not Google Chrome — so cookies are portable.
4. **Use `--list-profiles`** when multiple profiles exist; export the one that is actually logged in.
5. **Encrypt before sharing** (`encrypt` or `--encrypt-password`). Treat `.tokenade` like a password dump.
6. **Need storage (Discord, Telegram, some SPAs)?** Prefer a **site handler** on CLI export. Handlers declare exact storage origins. The extension cannot match that map today.

### Launch & inject

7. **Always use a clean `--profile-dir` for tests and portability.** Injecting into a dirty system profile mixes old cookies, risk signals, and false failures.
8. **Navigate to the product URL**, not the IdP bounce page, after inject (e.g. inbox URL, not `accounts.google.com`).
9. **Google: avoid Chrome-family targets** (Chrome, Chromium, Canary). Non-Chrome targets work; Chrome clean profiles still fail in practice.
10. **One CDP port per concurrent browser** (`--port`). Parallel launches need distinct ports and profile dirs.
11. **Site plugins** (`--plugin discord-handler`, `--plugin telegram-handler`, `--plugin generic-handler`) keep domain filters and storage rules consistent between export and load.

### Proxy & ops

12. **Prefer `127.0.0.1` binding** for local proxy; do not expose session proxies to the network without deliberate network design.
13. **TLS fingerprint / `--fingerprint`:** useful for many anti-bot stacks; can interfere with some `cf_clearance` flows — verify per site.
14. **Refresh instead of re-login** when cookies age: `tokenade refresh-browser` or `tokenade accounts refresh` for batches.
15. **Health is a hint**, not a login proof. `tokenade health` scores cookie heuristics; confirm with a real page load when it matters.
16. **Do not commit live `.tokenade` files** to git. Add them to `.gitignore`; rotate if leaked.

### Security habits

17. Session files = full account access for cookie lifetime. Store encrypted; limit filesystem permissions.
18. Prefer short-lived copies on shared machines; delete profile dirs under `/tmp` when done.
19. For automation, pin Python and document the donor browser version you validated against.

---

## Installation (dev)

```bash
git clone https://codeberg.org/mihir0209/tokenade.git
cd tokenade
pip install -e ".[dev]"
pytest   # suite under tokenade/tests/
```

**Browser backends (know which is which):**

| Piece | Role | How you get it |
|-------|------|----------------|
| **CloakBrowser** | Default **load / launch / stealth** Chromium backend (core dependency) | Ships with `pip install tokenade`; **binary downloads on first use** when available |
| **Playwright Chromium** | Used by some **proxy / CDP / test** paths that drive stock Playwright | Optional for core CLI export; for those paths: `playwright install chromium` (add `--with-deps` on Linux CI images) |

You do **not** need `playwright install` just to export cookies or run most unit tests. Install Playwright browsers when you exercise CDP proxy, gateway runtime with a real browser, or Playwright-based integration tests.

---

## Plugins

Site handlers and other plugins customize domains, critical cookies, and launch behavior without forking core:

```bash
tokenade export --list-handlers
tokenade plugin list
tokenade launch -s gmail.tokenade --plugin google-handler --browser brave \
  --profile-dir /tmp/tokenade-brave-clean --visible
```

Authoring guide: [`docs/PLUGIN_DEVELOPMENT.md`](docs/PLUGIN_DEVELOPMENT.md). Examples: [`examples/plugins/`](examples/plugins/).

---

## Request framework

For automation and orchestration, Tokenade accepts a nested `request.json` envelope. The core validates structure only; plugin `config` is dynamic pass-through.

### Run operation

Execute plugin operations in order:

```json
{
  "version": "1",
  "operation": "run",
  "plugins": [
    {
      "name": "generic-handler",
      "required": true,
      "roles": {
        "run": {
          "method": "process"
        }
      },
      "config": {
        "session_file": "/path/to/github.tokenade",
        "site": "github"
      }
    }
  ],
  "execution": {
    "stop_on_error": true
  }
}
```

```bash
tokenade run --request request.json
```

### Gateway operation

Start a local multi-session control plane with isolated browser contexts:

```json
{
  "version": "1",
  "operation": "gateway",
  "sessions": {
    "dir": "./sessions",
    "pattern": "*.tokenade"
  },
  "gateway": {
    "host": "127.0.0.1",
    "port": 9222,
    "backend": "cdp"
  },
  "routing": {
    "object": "session",
    "strategy": "health-weighted",
    "default_scope": "activate-context",
    "switch_interval_seconds": 30,
    "sticky_by": "site",
    "failover": true,
    "drain_existing_tabs": true
  },
  "plugins": []
}
```

```bash
tokenade gateway --request request.json
```

Gateway API endpoints:
- `GET /status` — routing state and session count
- `GET /sessions` — sanitized session records (no cookies/storage)
- `POST /route/next` — select next session by strategy
- `POST /route/select` — set active session by ID/path/site
- `GET /contexts` — isolated browser context state
- `POST /contexts/lease` — keep a runtime context protected from cleanup
- `POST /contexts/release` — release a context lease
- `POST /contexts/drain` — cleanup inactive, unleased contexts
- `POST /tabs/new` — open the active session using the window policy

Route scope controls what routing does to the browser runtime: `activate-context` prepares an isolated context, `future-only` selects without browser activity, and `open-target` routes and opens the target URL. The default window policy is `reuse-active-window` to avoid tab spam.

**Privacy:** gateway outputs session metadata only (site, cookie count, health score). Never cookies, tokens, localStorage, or proxy credentials.

### Proxy resolve operation

Resolve upstream proxy provider configuration with credential redaction:

```json
{
  "version": "1",
  "operation": "proxy.resolve",
  "plugins": [
    {
      "name": "brightdata",
      "required": true,
      "roles": {
        "proxy_provider": {
          "mode": "sticky",
          "nearest_to_source": true,
          "fallback": "fail"
        }
      },
      "config": {
        "zone": "residential"
      }
    }
  ]
}
```

```bash
tokenade proxy resolve --request request.json
```

Output is redacted by default. Use `--show-secrets` to reveal credentials.

---

## Security (short)

- Treat every `.tokenade` as credentials.
- Use encryption at rest; prefer encrypt-on-export for transfers.
- Default proxy bind is loopback; SSRF protections block private/loopback targets on outbound proxy paths.
- Report security issues privately when possible; see [`docs/SECURITY.md`](docs/SECURITY.md).

---

## Terminal UI (TUI)

Optional, powerful front-end over the same CLI (subprocess argv — no parallel business logic).

```bash
pip install 'tokenade[tui]'
tokenade tui
```

| Key | Tab |
|-----|-----|
| `1` | **Export** — browser/profile discovery, domains, handlers, encrypt |
| `2` | **Sessions** — list jars, launch / load / health / share |
| `3` | **Share** — password share-url create/receive (password never uploaded) |
| `4` | **Convert** — DirectoryTree file picker + industry formats → `.tokenade` |
| `5` | **Gateway** — dropdown JSON from `~/.tokenade/requests`, browse from `~/Downloads`, launch in background, route/select/open/cleanup runtime contexts from request settings (`gateway.runtime.url`) |
| `6`–`8` / `0` | Vault, Sync, Plugins, Settings |

**Copy:** drag to select text in logs and labels. **Ctrl+C does not quit** (shows a hint). Use **Ctrl+Shift+C** (or your terminal’s copy) for selection; **Ctrl+Q** or **q** to quit.

Without the extra: `tokenade tui` prints install instructions and exits `1`. Core CLI keeps working.

## Browser extension

Load unpacked from [`extension/`](extension/) (Chromium-family). See [`extension/README.md`](extension/README.md) for limits. Not on the Web Store yet.

## Documentation

| Doc | Contents |
|-----|----------|
| [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) | Commands, share-url, TUI, convert |
| [`docs/TUTORIAL_GETTING_STARTED.md`](docs/TUTORIAL_GETTING_STARTED.md) | Gmail→Brave golden path + Windows |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | Locked DB, decrypt errors, proxy issues |
| [`extension/README.md`](extension/README.md) | Extension install + honest capability table |
| [`docs/SITE_CONFIGS.md`](docs/SITE_CONFIGS.md) | Site configs live in plugins (`site_config.json`) |
| [`docs/API.md`](docs/API.md) | Programmatic / server API |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Package layout and design |
| [`docs/PLUGIN_DEVELOPMENT.md`](docs/PLUGIN_DEVELOPMENT.md) | Plugin API |
| [`USE-CASES.md`](USE-CASES.md) | Scenarios and comparisons |
| [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) | Contribution guidelines |

CLI discovery beats a second manual: `tokenade --help`.

---

## Project stance

- **Honesty over hype** — battle-tested vs “code exists” stay separated in docs and messaging.
- **Session portability first** — plugins, stealth, fleet tooling support that core; they are not the product by themselves.
- **Evidence** — Google multi-device non-Chrome recipe verified 2026-07-10; see project notes under `.agent/` for campaign details (not required for end users).

---

## License

[MIT](LICENSE) — Copyright (c) 2026 MiHiR
