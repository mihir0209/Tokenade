# Tokenade 1.2.2 Post-Release Backlog

This backlog collects confirmed follow-up work after the `1.2.1` release. Do not
bump the version or schedule a patch until a reproducible issue is recorded.

## Monitoring

- [x] Review duplicate GitHub CI activity after dependency or workflow updates.
- [ ] Monitor PyPI installation reports on Linux, macOS, and Windows.
- [ ] Record any TUI layout defects with terminal name, dimensions, and screenshot.
- [x] Record browser portability failures with donor browser, target browser, site,
      and whether the Session contained local/session storage.

## Candidate Work

- [x] Expand Windows terminal QA for Vault and Settings scrolling.
- [x] Add a durable process-level multi-site proxy witness to CI where Playwright
      Chromium is available.
- [x] Fix browser-level CDP cookie injection to use `Storage.setCookies`; page-level
      stealth remains on the Playwright context/target session where the Page domain
      is valid.
- [x] Route Firefox Session loading through Playwright Firefox instead of the
      Chromium-only system CDP launcher; clean-profile cookie readback is covered by
      `scripts/witness_browser_portability.py`.
- [x] Filter v3 web-storage origins to the Session's cookie/site scope and requested
      target URL; fix argument-safe Playwright localStorage evaluation.

## Portability Evidence (2026-08-16)

- Firefox donor (`github-default.tokenade`) -> Brave clean profile: 10/10 cookies
  and 151 localStorage entries injected; product URL loaded; clean shutdown.
- Firefox donor -> Chromium clean profile: 10/10 cookies and 151 localStorage
  entries injected; product URL loaded; clean shutdown.
- Firefox donor -> Firefox target: initial system-CDP path reproduced a launch
  failure; Playwright Firefox replacement now injects 10/10 cookies and exits
  headlessly in about six seconds.
- Synthetic clean-profile cookie injection/readback passes on Firefox, Brave, and
  Chromium via `scripts/witness_browser_portability.py`.
- Real Reddit + GitHub multi-site proxy passes with browser-level
  `Storage.setCookies`; no invalid Page-domain warning or context fallback.
- [ ] Revisit the `vault_id` / `key_id` data clump only if another key-lifecycle
      change requires touching those call sites.

## Patch Gate

A `1.2.2` release requires:

1. A confirmed user-visible defect or security/reliability regression.
2. A regression test reproducing the issue.
3. Strict full suite, duplicate CI Pipeline, and Stealth Testing green.
4. A clean-wheel witness for the affected workflow.
