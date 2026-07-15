# Phase 8: Terminal and System Verification

## Goal

Verify the generalized runner and the complete plugin ecosystem from the
terminal and through real browser workflows.

## Scope

- Build a flat JSON request for `google-flow-handler`.
- Run `tokenade run google-flow-handler --input request.json`.
- Verify stdout is valid JSON and exit code is correct.
- Verify output `.tokenade` loading and metadata.
- Run Playwright headless end-to-end with the real Google source session.
- Run CloakBrowser when installed and compare behavior.
- Test an internal-only plugin rejection.
- Test malformed input, unknown fields, method selection, and plugin failure.
- Run the full Tokenade and marketplace test suites.

## References

- `.agent/new_phases/phase-03-cli-run.md`
- `.agent/new_phases/phase-07-local-reinstall.md`
- `tests/test_oauth_automation.py`
- `tokenade/core/importer/session_packager.py`

## Acceptance Criteria

- Terminal invocation works from a clean installation.
- JSON stdout is machine-readable with no log contamination.
- Google Flow produces a valid target session.
- The target session can authenticate the tested labs.google API request.
- Full regression tests pass, with documented environment-only skips.

## Dependencies

- Phases 1-7.

## Current Verification Note

As of 2026-07-15, the clean registry installation and generalized runner are
verified. `tokenade run google-flow-handler --input request.json` produces
exactly one JSON line on stdout, sends diagnostics to stderr, and returns exit
code 1 for a plugin failure. The current Playwright run reaches a valid Google
provider session and `labs.google/fx/tools/flow`, but the OAuth click does not
produce `__Secure-next-auth.session-token` and `EMAIL`; the plugin correctly
rejects the transient 7-cookie package instead of reporting false success.

The remaining blocker is the real OAuth exchange in the clean installed
environment. CloakBrowser is not installed yet, so the next diagnostic path is
to repeat this phase after CloakBrowser installation, then compare browser
network/navigation behavior if the target cookies are still absent.

## Playwright Rerun: 2026-07-15

The clean installed `google-flow-handler` was updated through the published
registry to `1.0.3` and rerun with `/tmp/google-session`.

- Source session: 180 cookies, non-expired Google auth cookies, metadata email
  `mihirpatil128@gmail.com`.
- Provider probe: passed at `https://myaccount.google.com`.
- Target navigation: passed with `domcontentloaded`.
- OAuth button: clicked successfully.
- Browser trace: only the landing analytics event was emitted; no OAuth,
  NextAuth callback, or sign-in request was observed.
- Target cookies: only transient CSRF/state/PKCE and analytics cookies.
- Required cookies absent: `__Secure-next-auth.session-token`, `EMAIL`.
- Terminal result: exactly one JSON line on stdout, diagnostics on stderr,
  exit code `1`, plugin error explaining the missing target session.

This is a reproducible external-flow blocker, not a runner or installation
failure. CloakBrowser status at this point is `installed=false`,
`binary_ready=false`; a separate CloakBrowser comparison remains pending.
