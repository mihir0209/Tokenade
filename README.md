# Tokenade

**Portable browser sessions.** Export cookies (and storage) from a real browser into a `.tokenade` file, then launch or proxy on another machine as that session — with TLS fingerprint matching where it matters.

[![PyPI version](https://img.shields.io/pypi/v/tokenade.svg)](https://pypi.org/project/tokenade/)
[![Python versions](https://img.shields.io/pypi/pyversions/tokenade.svg)](https://pypi.org/project/tokenade/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/tokenade.svg)](https://pypi.org/project/tokenade/)
[![CI](https://img.shields.io/github/actions/workflow/status/mihir0209/tokenade/ci.yml?branch=main&label=CI)](https://github.com/mihir0209/tokenade/actions)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

```bash
pip install tokenade
```

> **Not a Multilogin / AdsPower replacement.** Tokenade is session **portability** (export → package → inject / proxy), not a full anti-detect browser product. Stealth is best-effort and measured — never “undetectable.”

---

## Why Tokenade?

| You need… | Tokenade |
|-----------|----------|
| Move a logged-in session to another device | Export → `.tokenade` → launch or proxy |
| Keep cookies + localStorage (e.g. Telegram Web) | Full / ecosystem packaging |
| Match donor TLS on proxied traffic | CDP proxy + `curl-cffi` |
| Encrypt session files at rest | AES-256-GCM (`encrypt` / export password) |
| Extend behavior per site | Site-handler plugins (`--plugin google-handler`) |

Self-hosted CLI. No cloud account required for the core loop.

---

## Quick start

### 1. Install

```bash
pip install tokenade
# Python 3.10+
```

Optional extras: `tokenade[tui]`, `tokenade[linux]`, `tokenade[enterprise]` (LDAP — experimental).

### 2. Install site plugins + quit the donor browser

```bash
tokenade plugin install google-handler   # ships site_config.json
tokenade export --list-handlers
```

Fully quit the browser first (see [Best practices](#best-practices)). A running browser locks the cookie database.

```bash
tokenade export --list-profiles

# Domains / critical cookies come from the plugin's site_config.json
tokenade export --browser-name firefox --plugin google-handler -o gmail.tokenade
```

### 3. Use the session

**Launch** (inject into a clean profile — preferred for interactive use):

```bash
tokenade launch \
  --browser brave \
  --session gmail.tokenade \
  --plugin google-handler \
  --url "https://mail.google.com/mail/u/0/#inbox" \
  --profile-dir /tmp/tokenade-brave-clean \
  --port 9223 --visible
```

Omit `--profile-dir` and Tokenade still uses a **clean temp profile** for session inject.

**Proxy** (CDP reverse proxy with optional TLS impersonation):

```bash
tokenade proxy -s gmail.tokenade
# Open the local GUI / URL printed by the CLI (default port 9222)
```

**Encrypt** sensitive jars before sharing or storing:

```bash
tokenade encrypt -s gmail.tokenade -o gmail.enc.tokenade
# or: tokenade export ... --encrypt-password '…'
```

Full command list: `tokenade --help` and `tokenade <command> -h`. Deep dives live under [`docs/`](docs/).

---

## What works (evidence-based)

| Capability | Status | Notes |
|------------|--------|-------|
| Cookie export (Chrome / Firefox / Brave / Edge) | **Works** | SQLite extraction; quit browser first |
| Launch + inject (Gmail, multi-browser) | **Works** | Prefer clean `--profile-dir` |
| Google: Firefox/Brave/Edge donor → non-Chrome target | **Works** | Multi-browser & multi-device verified (2026-07-10) |
| Google → **Chrome / Chromium** target | **Fails** | Account chooser / signed out; avoid Google-owned browsers |
| CDP proxy + session inject (Gmail, ChatGPT) | **Works** | Confirmed logged-in in real runs |
| localStorage (e.g. Telegram Web) | **Works** | Use `--full` / storage flags when needed |
| AES-256-GCM session encryption | **Works** | Core encryptor, PBKDF2 |
| Session health scoring | **Works** | Heuristic on cookies — not live auth proof |
| TLS fingerprint matching (`curl-cffi`) | **Works** | Core dependency; use thoughtfully with `cf_clearance` |
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

1. **Export** — read cookies (and optional storage) from a real profile; package as `.tokenade`.
2. **Transfer** — copy the file (optionally encrypted) to another machine or process.
3. **Replay** — `launch` (system browser + inject) or `proxy` (TLS-matched reverse proxy).

**Google recipe (verified):** donor **not** Chrome → target **Brave / Edge / Vivaldi / Firefox** → **clean** `--profile-dir` → open the **product URL** (e.g. `mail.google.com`), not `accounts.google.com` after inject. Same jar can run on multiple non-Chrome browsers/devices concurrently.

---

## Best practices

These matter more than flag trivia. Follow them and most “broken session” reports go away.

### Export

1. **Fully quit the donor browser before export.**
   Chrome/Firefox/Brave hold exclusive locks on the cookies SQLite DB. “Quit” means no residual process in Task Manager / Activity Monitor / `pgrep`. Otherwise you get `database is locked` or a partial/stale dump.
2. **Export only the domains you need** (`--domains` or a site plugin). Smaller jars are easier to reason about and safer to share.
3. **Prefer a stable donor** for high-value accounts. For Google, prefer Firefox / Brave / Edge — not Google Chrome — so cookies are portable.
4. **Use `--list-profiles`** when multiple profiles exist; export the one that is actually logged in.
5. **Encrypt before sharing** (`encrypt` or `--encrypt-password`). Treat `.tokenade` like a password dump.
6. **Need storage (Telegram, some SPAs)?** Use `--full` or `--extract-local-storage` instead of cookies-only.

### Launch & inject

7. **Always use a clean `--profile-dir` for tests and portability.** Injecting into a dirty system profile mixes old cookies, risk signals, and false failures.
8. **Navigate to the product URL**, not the IdP bounce page, after inject (e.g. inbox URL, not `accounts.google.com`).
9. **Google: avoid Chrome-family targets** (Chrome, Chromium, Canary). Non-Chrome targets work; Chrome clean profiles still fail in practice.
10. **One CDP port per concurrent browser** (`--port`). Parallel launches need distinct ports and profile dirs.
11. **Site plugins** (`--plugin google-handler`) keep domain filters and launch URLs consistent between export and launch.

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
git clone https://github.com/mihir0209/tokenade.git
cd tokenade
pip install -e ".[dev]"
playwright install chromium --with-deps
pytest   # suite under tokenade/tests/
```

CloakBrowser (stealth Chromium backend) is a core dependency; its binary downloads on first use when available.

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

## Security (short)

- Treat every `.tokenade` as credentials.
- Use encryption at rest; prefer encrypt-on-export for transfers.
- Default proxy bind is loopback; SSRF protections block private/loopback targets on outbound proxy paths.
- Report security issues privately when possible; see [`docs/SECURITY.md`](docs/SECURITY.md).

---

## Documentation

| Doc | Contents |
|-----|----------|
| [`docs/TUTORIAL_GETTING_STARTED.md`](docs/TUTORIAL_GETTING_STARTED.md) | Gmail→Brave golden path + Windows |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | Locked DB, decrypt errors, proxy issues |
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
