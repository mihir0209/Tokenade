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
