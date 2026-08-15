# Tokenade 1.2.2 Post-Release Backlog

This backlog collects confirmed follow-up work after the `1.2.1` release. Do not
bump the version or schedule a patch until a reproducible issue is recorded.

## Monitoring

- [ ] Review duplicate GitHub CI activity after dependency or workflow updates.
- [ ] Monitor PyPI installation reports on Linux, macOS, and Windows.
- [ ] Record any TUI layout defects with terminal name, dimensions, and screenshot.
- [ ] Record browser portability failures with donor browser, target browser, site,
      and whether the Session contained local/session storage.

## Candidate Work

- [ ] Expand Windows terminal QA for Vault and Settings scrolling.
- [ ] Add a durable process-level multi-site proxy witness to CI where Playwright
      Chromium is available.
- [ ] Investigate the CDP injection warning before context fallback; fallback is
      currently successful, but the direct injection path should be measured.
- [ ] Revisit the `vault_id` / `key_id` data clump only if another key-lifecycle
      change requires touching those call sites.

## Patch Gate

A `1.2.2` release requires:

1. A confirmed user-visible defect or security/reliability regression.
2. A regression test reproducing the issue.
3. Strict full suite, duplicate CI Pipeline, and Stealth Testing green.
4. A clean-wheel witness for the affected workflow.
