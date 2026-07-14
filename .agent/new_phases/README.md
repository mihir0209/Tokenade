# API 1.3.0 Plugin Overhaul

This directory is the working memory for the generalized plugin execution
overhaul. Each phase has a separate file with scope, references, acceptance
criteria, and dependencies.

## Delivery Cadence

Work proceeds in sessions of at most three phases. A phase is complete only
after implementation, focused tests, and a review have passed. Do not begin a
fourth phase in the same session.

## Phase Order

1. `phase-01-api-contract.md` - API 1.3.0 contract and shared schema helpers
2. `phase-02-plugin-runner.md` - lifecycle-aware execution engine
3. `phase-03-cli-run.md` - generalized `tokenade run` command
4. `phase-04-plugin-migration.md` - migrate every marketplace plugin
5. `phase-05-registry-repair.md` - regenerate and validate registry metadata
6. `phase-06-marketplace-release.md` - commit and publish marketplace changes
7. `phase-07-local-reinstall.md` - reset and reinstall selected plugins
8. `phase-08-terminal-verification.md` - terminal, browser, and regression QA

## Global Constraints

- Canonical plugin API version is `1.3.0`.
- Plugins are installed and discovered from `~/.tokenade/plugins/`.
- `tokenade/plugins/` is a development workspace only; migrated plugins are
  removed from it.
- External execution is opt-in through an executable `run` manifest section.
- Runner-owned arguments are limited to `--input` and the optional method
  positional argument.
- Input is a flat JSON object; unknown fields are rejected.
- Explicit CLI method selection overrides the manifest default method.
- JSON results go to stdout; diagnostics go to stderr.
- Exit code `0` means plugin success, `1` means plugin failure, and `2` means
  runner, manifest, schema, loading, or invocation failure.
- Never delete `~/.tokenade` until replacement marketplace data is committed,
  published, and ready for reinstall.
- Preserve unrelated or pre-existing worktree changes.
