# Tokenade Continuation: CLI Surface Audit

Date: 2026-07-17
Repo: `/home/ghostrider/Projects/tokenade`
Marketplace repo: `/home/ghostrider/Projects/tokenade-plugins`
Current package: `tokenade==1.1.53`
Latest pushed commit: `24c5937 ci: smoke test installed wheel`

This file supersedes the old `1.0.0` continuation notes. The active focus is CLI surface cleanup, command polishing, and `.tokenade` metadata improvements after the PyPI hardening work.

## Current Verified State

- `tokenade==1.1.53` is the current verified PyPI release.
- `tokenade==1.1.52` is superseded and must not be recommended; it shipped a runtime import regression in `tokenade test`.
- CI is green on `main` after `24c5937`.
- Installed-wheel CI guard is in place:
  - `scripts/check_wheel_contents.py` verifies the wheel excludes `tokenade/tests/`.
  - `scripts/smoke_installed_wheel.py` installs the built wheel into a clean venv and verifies `tokenade --version`, `import tokenade.core.portability`, and `tokenade test -s minimal.tokenade` reaches handler resolution.
- `tokenade plugin sync` is the preferred install-all path and loads 17/17 marketplace plugins.
- Discord and Telegram hard-site exports are verified through marketplace Site Handlers with handler-declared storage origins.

## New Product Gap: Export Handler Metadata

When `tokenade export` uses a Plugin/Site Handler, the produced `.tokenade` file currently does not record which Plugin or handler performed the export.

Why this matters:

- `load`, `validate`, `test`, `health`, `recommend`, `autopsy`, and future refresh flows can make better decisions if the session file declares its export lineage.
- A session exported by `discord-handler v1.2.0` should carry that information for supportability and reproducibility.
- Handler-declared storage origins should be auditable from the `.tokenade` file.
- Plugin-owned sessions should be distinguishable from default cookie-only exports.

Likely implementation seam:

- `tokenade/core/importer/session_packager.py:SessionPackager.package()` already writes a `metadata` dict.
- `tokenade/cli/session_export.py:cmd_export()` knows `site_handler`, explicit `--plugin`, auto-discovered handler, export domains, and storage origins.
- `tokenade/core/importer/plugin_export.py:PluginExporter._export_with_plugin()` also packages handler-backed exports and should populate the same metadata.

Proposed metadata shape:

```json
{
  "metadata": {
    "extraction_method": "site_handler" | "sqlite_direct" | "cdp" | "file_import",
    "site_handler": {
      "plugin_name": "discord-handler",
      "plugin_version": "1.2.0",
      "handler_name": "discord-handler",
      "handler_class": "DiscordHandler",
      "export_domains": ["discord.com", "discordapp.com"],
      "storage_origins": ["https://discord.com"],
      "auto_discovered": false
    }
  }
}
```

Design notes:

- Keep this backward-compatible by only adding metadata fields.
- Do not rename existing top-level fields in the `3.0` format yet.
- Avoid storing plugin local paths unless explicitly needed; plugin name/version/handler class are enough for support.
- Downstream commands should prefer `metadata.site_handler.plugin_name` when selecting a handler, then fall back to `site_name`/domain recommendation.

First implementation ticket:

1. Add optional `metadata` or `handler_metadata` argument to `SessionPackager.package()`.
2. Populate it in `cmd_export()` when `site_handler` is present.
3. Populate it in `PluginExporter._export_with_plugin()`.
4. Add tests that exported Discord/Telegram-style packages contain handler metadata and storage origins.
5. Update `tokenade recommend -s <session>` to surface the embedded handler when present.

## CLI Surface Audit Summary

Static audit found 60 registered top-level commands. `tokenade <command> --help` does not crash for any top-level command, but many command surfaces are stale, low-evidence, duplicated, or inconsistent with current product language.

Primary issue: the package has a hardened core loop, but the CLI still exposes broad historical scaffolding as if it is all equally production-ready.

Visibility rule from grilling session:

- Default `tokenade --help` should show only real-world witnessed commands.
- Unit tests, local integration tests, and clean-install tests are necessary but not enough for default visibility.
- Do not publish separate experimental PyPI releases for unfinished command surfaces.
- Future ideas should stay hidden, planned, or eventually moved under an explicit experimental surface until they are witnessed end-to-end.
- First cleanup slice: remove `patch-chrome`; hide `container`, `serve`, and `sync` from default help while keeping the hidden commands callable during transition.

Core loop that should remain first-class:

- `export`: Session Packager entry point.
- `load`: Session Loader entry point.
- `launch`: Browser/CloakBrowser launch with session.
- `proxy`: CDP/proxy replay path.
- `plugin`: Plugin marketplace and Site Handler install/test/sync path.
- `recommend`: site/plugin/browser recommendation.
- `health`: heuristic session health.
- `validate`: directory/session structural validation.
- `test`: portability testing, needs fingerprint UX polish.
- `encrypt`, `decrypt`, `rekey`: session-file protection.
- `sessions`: local multi-session listing/merge/rotation/stats.
- `cloak`: CloakBrowser management.
- `logs`: support/debugging surface.

## Command Direction After User Review

Important correction: a command being incomplete today does not automatically mean it should be removed. Some surfaces are product ideas worth keeping and building properly.

### Keep And Build Properly

These commands are weak today, but aligned with Tokenade's product direction.

### `fleet`

- Keep as a product idea.
- Original intent: orchestrate multiple session files the way Kubernetes orchestrates workloads.
- Reframe around session fleets, not Docker/Kubernetes internals.
- Possible model: `tokenade fleet create`, `fleet status`, `fleet health`, `fleet rotate`, `fleet refresh`, `fleet run` over a directory or registry of `.tokenade` files.
- Do not make it depend on the current rough `container` implementation.

### `mobile-import`

- Keep as a long-term high-value capability.
- It is useful for a session portability product, but needs honest platform constraints.
- Requires a proper design for Android/iOS access modes: rooted Android, adb backup where possible, app-specific browser profiles, iOS backup extraction, and explicit unsupported cases.
- Should be marked experimental until verified on real devices.

### `clone-profile`

- Keep as a session portability adjacent capability.
- It should not claim complete browser cloning until storage, cookies, encryption, and profile metadata are handled correctly per browser.
- Likely reposition as profile portability / profile template cloning, with session injection as a separate step.

### `analytics`

- Keep and wire into real event capture.
- Product intent: collect export/load/health/test/refresh success and failure history under `~/.tokenade`, then show it in the TUI.
- Needed work: structured local event store, lifecycle hooks in core commands, TUI views, cleanup/retention controls, privacy controls.

### `k8s`

- Undecided.
- Potentially useful, but overlaps with `ci`/`cicd` automation and may not belong in the core CLI yet.
- Decision needed: either make it an advanced deployment command backed by real Secrets/ConfigMaps/session fleet semantics, or move it out of the default surface.

### `profile`

- Needs investigation before deciding.
- Current unclear value: manages Tokenade browser profile metadata, but primary workflows use browser discovery and `--profile-dir`.
- Decision question: should Tokenade have first-class profile identities, or should profile handling stay as explicit paths and CloakBrowser/runtime concerns?

## Strong Decommission Candidates

These should be removed, hidden, or replaced because they are duplicated, risky, or not aligned with the current architecture.

### `container`

- File: `tokenade/cli/handlers/infrastructure.py:cmd_container`
- Status: likely decommission candidate.
- Reason: current Docker orchestration surface is not useful enough and distracts from the session-fleet idea.

### `serve`

- File: `tokenade/cli/__init__.py:cmd_serve`
- Status: likely decommission candidate.
- Reason: API server appears to start aiohttp and return, so the process may exit immediately; endpoints shell out to CLI and can expose session payloads.

### `patch-chrome`

- File: `tokenade/cli/handlers/browser_ops.py:cmd_patch_chrome`
- Status: likely decommission candidate.
- Reason: risky Chrome/Chromium binary patching for `cdc_` artifacts; conflicts with CloakBrowser-as-default positioning.

### `sync`

- File: `tokenade/cli/handlers/session_ops.py:cmd_sync`
- Status: likely decommission candidate unless productized.
- Reason: mtime polling daemon overlaps export/refresh; CLI lacks stop/status; profile path construction appears fragile.

## Keep But Polish

These are useful but need UX, naming, or correctness work.

### `cloak`

- Critical polish item.
- Need excellent first-run UX when CloakBrowser binary is missing, unavailable, or not installed in isolated HOME.
- `tokenade load` should explain exactly what to run, why fallback happened, and whether Playwright/system browser fallback was used.

### `stealth`

- Keep if consolidated around Stealth Level and CloakBrowser.
- Avoid “undetectable browser” language.
- `stealth deps` duplicates `deps`; keep one canonical dependency surface.

### `deps`

- Keep one dependency check/install command.
- Decide whether `tokenade deps` is canonical and `tokenade stealth deps` becomes an alias, or vice versa.

### `ci`

- Concrete utility: reads `tokenade.yml`, validates/lints/runs CI checks.
- Keep, but decide if it belongs in core docs or advanced docs.

### `cicd`

- Workflow generator is useful but scaffold-like.
- Consider moving under `ci generate` or marking experimental.

### `autopsy`

- Keep as diagnostic command.
- Must present itself as heuristic analysis, not live auth proof.

### `monitor`

- Core monitor library is real.
- CLI lifecycle is weak: `stop` expects a PID file, but `start` does not write one; `history` in a new process cannot see prior in-memory history.

### `share`, `unshare`, `import`

- Keep only with strong security caveats.
- Current self-contained URLs can embed decryptable payload/key material; local `unshare` cannot revoke already-distributed self-contained URLs.
- Consider password-required sharing by default.

### `versions`, `rollback`, `session-diff`

- Keep as local safety tools.
- Polish around when versions are automatically created.
- Avoid confusion with `diff`, which compares two files.

### `completion`

- Keep, but command lists are hardcoded and stale.
- Should generate from parser or be updated after cleanup.

## Legacy Or Duplicative Commands Needing Decisions

### `extract`

- Help: “Extract tokens”.
- Status: likely legacy and confusing.
- It overlaps modern `export` and conflicts with current “Session Packager” language.

### `transfer`

- Status: likely legacy overlap with `load`/`launch`.
- Uses legacy handler resolution and odd parser option `('-', '--fingerprint')`.

### `setup`

- Status: legacy account/password setup.
- Parser registers no `--encrypt`, but implementation tells users to run `tokenade setup --encrypt`.

### `validate`, `validate-session`, `validate-rules`

- Status: useful but crowded.
- Need one clear matrix:
  - `validate`: user-facing session/directory validation.
  - `validate-session`: CI-specific gate, or merge into `ci validate`.
  - `validate-rules`: advanced custom rules, possibly nested under `validate rules`.

### `diff` and `session-diff`

- `diff`: compare two session files.
- `session-diff`: compare versions of the same managed session.
- Keep both only if help and docs make this distinction obvious.

## Stale Help And Language Issues

- Main help epilog is incomplete and stale.
- Shell completions hardcode old command lists and omit many registered commands.
- Avoid “undetectable browser”; use CloakBrowser and Stealth Level.
- Avoid “site plugin”; use Site Handler or Plugin depending on meaning.
- Avoid “cookie file/token file/auth data”; use session and `.tokenade` file.
- `launch` and `refresh-browser` help use “undetectable”; update.
- `export` still says “Extract cookies” in some help text; use Session Packager language while still being concrete about cookies/storage.

## Suggested Cleanup Order

1. Add export handler metadata to `.tokenade` files.
2. Make downstream `recommend`/`load`/`test` read embedded handler metadata when present.
3. Fix CloakBrowser first-run and missing-binary UX for `load` and `cloak`.
4. Remove or hide obvious dead/duplicate commands first: `container`, `serve`, `patch-chrome`, and likely `sync`.
5. Design proper futures for `fleet`, `mobile-import`, `clone-profile`, and `analytics` instead of deleting them.
6. Decide `k8s` and `profile` after a focused design pass.
7. Decide legacy fate for `extract`, `transfer`, and `setup`; keep the most mature path and remove duplicates.
8. Consolidate validation commands.
9. Consolidate `stealth`/`cloak`/`deps` language.
10. Regenerate or simplify shell completions.
11. Run one command-family QA pass at a time, starting with `encrypt/decrypt/rekey`, then `health/validate/test`, then `plugin`, then `cloak/load/launch`.

## Deferred Polish Ideas

These were intentionally deferred until after CLI surface cleanup.

- Close the remaining release-hardening doc checklist item and record the installed-wheel smoke CI guard.
- Run a new-user-from-zero README audit in a fresh venv and isolated HOME.
- Polish `tokenade plugin sync` output with installed/skipped/loaded counts and next-step suggestions.
- Add `docs/TROUBLESHOOTING.md` for browser locks, missing handlers, missing fingerprints, CloakBrowser setup, health-vs-live-auth mismatch, and storage-only sessions.
- Continue improving docs once the CLI surface is honest and smaller.

## Commands Verified In This Audit

- `git status --short`: clean before audit edits.
- `gh run list --limit 5`: CI and Stealth Testing green on `24c5937`.
- `python3 -m tokenade --help`: showed the full registered command surface.
- `python3 -m tokenade <command> --help` for every top-level command: 60 commands, 0 help failures.

## Do Not Forget

- Plugin edits belong in `/home/ghostrider/Projects/tokenade-plugins`.
- Core package edits belong in `/home/ghostrider/Projects/tokenade`.
- Keep the domain language from `CONTEXT.md` intact.
- CloakBrowser is the project-wide default for automation; Playwright fallback; Chrome/system browser last.
- CloakBrowser `add_init_script` takes `(script: str, path=None)`, no `arg=` kwarg.
