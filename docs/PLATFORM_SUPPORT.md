# Platform Support Matrix

What is verified where. Entries marked **verified** were proven on that
platform; everything else is code-shared but untested — please report gaps.

## Windows (verified on Win10 + Brave 153 / Edge 153, Sep 2026)

| Capability | Chrome-family (Chrome/Brave/Edge) | Firefox |
|---|---|---|
| Cookie export (SQLite) | Names only — **app-bound encryption** (`v20` blobs, `os_crypt.app_bound_encrypted_key`) defeats third-party reads. Do not rely on values. | Works (own profile format) |
| Storage export (LevelDB) | **Works**, locked or quit, via the built-in pure-Python reader (`core/importer/leveldb.py`, no `plyvel`). Verified byte-identical vs in-page read (9 origins, 94 Discord keys incl. token) | Works (SQLite `ls/data.sqlite`) |
| CDP export (`--cdp-port`) | Works from a running browser. Launch with **bare** `--remote-debugging-port` only — an explicit `--user-data-dir` breaks v20 decryption (80 → 21 cookies). `--cdp-launch` snapshots are cold: always pass `--domains`/`--plugin` to warm origins | N/A |
| Extension export/inject | Works (only path that sees storage Discord hides from automation) | Works (`.xpi` bundle) |
| `load` / `refresh-browser` | GitHub: portable ✅ · Google: rejected (`accountchooser`, device-bound — use OAuth automation) · Discord: needs token + document-start injection | Same per-site behavior |

Notes:

- Windows Chromium donors are **surrogacy-first**: prefer them as load
  targets; prefer extension/CDP-LevelDB for extraction, never raw SQLite
  for values.
- `refresh-browser` never overwrites its input (writes
  `<name>.refreshed.tokenade`); login verdict is URL + title + DOM
  logout selectors with a settle re-read.
- Discord deletes `window.localStorage` post-boot (anti-token-grabber);
  only document-start injection and the extension observe the token.

## Linux (repo CI + historical; re-verify on a live box)

- Full gate green in CI; Firefox Snap donor path documented (`CONTEXT.md`).
- `plyvel` path still preferred when installed; the pure reader is the
  fallback everywhere (also used when the profile is locked).
- Chrome-on-Linux donor/load matrix has not been re-proven recently —
  Google-from-Chrome transfers fail (device binding, same as Windows);
  other sites are expected to work. Needs a live pass.

## macOS

- Untested. Code paths are platform-gated (`CookieCryptoFactory`,
  pure-Python LevelDB, no `plyvel` requirement), but no live profile has
  validated them. Keychain-backed OSCrypt is the expected risk area.

## Not supported anywhere (by vendor design)

- Raw SQLite cookie *values* from Chromium 127+ (app-bound encryption).
- Cookie-replay portability for Google (device-bound sessions).
- Storage reads via automation on pages that neuter Web Storage
  post-boot (Discord) — extension or document-start injection only.
