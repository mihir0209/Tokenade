# Release Hardening Plan

This document is the working checklist for hardening Tokenade after the PyPI `1.1.5` release.

Goal: make the published package installable, verifiable, and usable from a clean environment without depending on local source checkouts or hand-copied plugins.

## Ground Rules

- Verify against the published PyPI package, not `pip install -e .`.
- Verify plugins through the GitHub-backed marketplace, not a local-dev registry.
- Keep this document updated as work completes.
- If a command is broken, fix it or document the limitation explicitly.
- Prefer repeatable scripts over manual verification steps.

## Current State

- `tokenade==1.1.5` is published on PyPI.
- Clean PyPI verification passed for `tokenade==1.1.5`.
- `~/.tokenade/plugins` was removed and plugins were reinstalled through a GitHub remote registry.
- `tokenade-plugins` GitHub registry was fixed and pushed:
  - `discord-handler v1.2.0`
  - `telegram-handler v1.1.0`
  - registry versions aligned with plugin manifests
- `tokenade test` no longer fails with `No handler found` when marketplace handlers are installed.
- `docs/USER_GUIDE.md` was updated with verified command output.

## Checklist

### 1. Push Core Repo Commits And Tags

- [x] Push core branch commits to GitHub.
- [x] Push `v1.1.3` tag.
- [x] Push `v1.1.4` tag.
- [ ] Push `v1.1.5` tag.
- [x] Verify GitHub has the release commit and tags.

Commands:

```bash
git status
git log --oneline -5
git tag -l 'v1.1.*'
git push origin main
git push origin v1.1.3 v1.1.4 v1.1.5
```

### 2. Fix Or Verify Marketplace Registry Behavior

- [x] Remove any local-dev registry from Tokenade config.
- [x] Verify `official` registry points to GitHub raw `main`.
- [x] Verify `tokenade plugin search discord` shows `discord-handler v1.2.0` from official.
- [x] Verify `tokenade plugin search telegram` shows `telegram-handler v1.1.0` from official.
- [x] If raw `main` is stale, add or fix a registry refresh/no-cache path.
- [x] Decide whether pinned GitHub registry should be documented as a fallback only.

Expected user path:

```bash
rm -rf ~/.tokenade/plugins
tokenade plugin install discord-handler
tokenade plugin install telegram-handler
tokenade plugin list
```

### 3. Make `tokenade plugin sync` The Install-All Path

- [x] Test `tokenade plugin sync` from a clean `~/.tokenade/plugins` directory.
- [x] Verify it installs all official plugins.
- [x] Verify `tokenade plugin list` reports `Loaded 17/17 plugins`.
- [x] Fix `plugin sync` if it skips, fails silently, or installs stale metadata.
- [x] Update docs to prefer `tokenade plugin sync` over manual loops.

Expected user path:

```bash
rm -rf ~/.tokenade/plugins
tokenade plugin sync
tokenade plugin list
```

### 4. Reduce CLI Logging Noise

- [x] Identify why normal CLI output includes duplicate log lines.
- [x] Make default CLI output quiet.
- [x] Keep detailed plugin loader logs behind `--verbose`.
- [x] Verify docs examples do not include unnecessary logging noise.

Symptoms to eliminate in default mode:

```text
17:55:02 INFO [plugin_loader] Loaded plugin: ...
2026-07-16 17:55:02,146 [INFO] tokenade.core.integration.plugin_loader: Loaded plugin: ...
```

### 5. Improve `tokenade test` UX

- [x] Keep handler resolution fixed for marketplace `SiteHandlerPlugin`s.
- [x] Make missing `default` fingerprint actionable.
- [x] Either auto-create a temporary default fingerprint or print a clear next command.
- [x] Update docs with the final behavior.

Current behavior after `1.1.4`:

```text
Using legacy handler DiscordSiteHandlerLegacyHandler
Error: Target fingerprint not found: default
```

Updated local behavior prints the next command to run:

```text
Next step: collect or choose a fingerprint, then rerun the test:
  tokenade fingerprint collect --name default --profile-dir <browser-profile-dir>
  tokenade test -s <session.tokenade> --target-fp default
```

### 6. Add Clean PyPI Release Verification Script

- [x] Add `scripts/verify_pypi_release.sh`.
- [x] Script must create a temporary venv.
- [x] Script must install `tokenade` from PyPI.
- [x] Script must use an isolated `TOKENADE_HOME` or backup/restore `~/.tokenade`.
- [x] Script must install plugins from GitHub marketplace.
- [x] Script must run smoke tests:
  - `tokenade --version`
  - `tokenade plugin sync` or plugin install loop
  - `tokenade plugin list`
  - `tokenade plugin test` for key handlers
  - `tokenade recommend --url https://discord.com`
  - `tokenade validate -d <sessions-dir>` when fixture sessions are available
  - `tokenade health -s <session>` when fixture sessions are available
  - `tokenade encrypt/decrypt` roundtrip when fixture sessions are available
  - `tokenade cloak info`
  - `tokenade load --file <session>` when fixture sessions are available
- [x] Script should fail fast and print a compact summary.

### 7. Run Clean Verification Script

- [x] Run script against `tokenade==1.1.4`.
- [x] Record results in this document.
- [x] Fix any failures.

### 8. Update README Front Page

- [ ] README should show the verified install path:

```bash
pip install tokenade
tokenade plugin sync
tokenade export --browser-name firefox --plugin discord-handler -o discord.tokenade
tokenade load --file discord.tokenade
```

- [x] Link to `docs/USER_GUIDE.md`.
- [x] Mention CloakBrowser default behavior.
- [x] Mention plugin marketplace.

## Verification Log

Add dated entries here as hardening steps complete.

### 2026-07-16

- Published `tokenade==1.1.5` to PyPI.
- Ran `scripts/verify_pypi_release.sh 1.1.5`; it passed.
- `tokenade==1.1.5` verification confirmed default CLI logging is quiet and `tokenade test` prints missing-fingerprint next steps.
- Pushed core `main` to GitHub through commit `853adae`.
- Pushed core tags `v1.1.3` and `v1.1.4` to GitHub.
- Verified GitHub raw `main` registry caught up and shows `discord-handler v1.2.0` and `telegram-handler v1.1.0`.
- Removed pinned `github-current` registry; normal official registry is sufficient again.
- Verified `tokenade plugin sync` installs all 17 official plugins from a clean plugin directory.
- Fixed default CLI logging noise in local source: normal commands no longer print duplicate INFO logs; `--verbose` remains the detailed path.
- Improved `tokenade test` missing-fingerprint UX with explicit next commands.
- Added `scripts/verify_pypi_release.sh` for clean PyPI/package + GitHub marketplace verification.
- Ran `scripts/verify_pypi_release.sh 1.1.4`; it passed.
- Verification script notes: browser-backed `tokenade load` is skipped when the isolated HOME does not have a CloakBrowser binary installed; non-browser checks and handler resolution still run.
- Published `tokenade==1.1.4` to PyPI.
- Installed `tokenade==1.1.4` from PyPI into the system-visible command.
- Installed 17 official plugins from GitHub remote registry pinned to tokenade-plugins commit `3d546d1082b9cb9e8c5ab7eb0284227cf178cd01` while GitHub raw `main` cache was stale.
- Verified:
  - `tokenade --version` => `tokenade 1.1.4`
  - `tokenade plugin list` => `Loaded 17/17 plugins`
  - key plugin contract tests => `10 passed, 0 failed`
  - Discord export => logged-in, 8 cookies, 100 localStorage entries
  - Discord load => 7/7 cookies injected via CloakBrowser
  - encrypt/decrypt roundtrip => clean diff
  - `tokenade test` => handler resolves; missing default fingerprint is now the remaining UX issue
