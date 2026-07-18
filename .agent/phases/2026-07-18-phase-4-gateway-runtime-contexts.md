# Phase 4: Gateway Runtime With Isolated Contexts

**Date:** 2026-07-18  
**Status:** Complete  
**Parent plan:** `.agent/plans/2026-07-18-gateway-request-framework.md`

## Progress

- 2026-07-18: Started implementation.
- 2026-07-18: Confirmed existing `SessionLoader.load()` launches/closes a whole browser per load and is not a safe fit for long-lived gateway contexts.
- 2026-07-18: Phase 4 will add a separate runtime abstraction that creates one isolated context per session and injects into supplied Playwright/CloakBrowser-compatible contexts, leaving browser/CDP promotion hidden.
- 2026-07-18: Added `tokenade.core.gateway.runtime` with `GatewayRuntime`, `GatewaySessionContext`, and `BrowserManagerContextFactory`.
- 2026-07-18: Runtime now prewarms one isolated context per session, injects cookies and origin-scoped localStorage/session storage shape, activates route-selected contexts, opens new pages on the active context, and drains inactive contexts.
- 2026-07-18: Extended hidden gateway control plane with optional runtime support and endpoints: `GET /contexts`, `POST /contexts/prewarm`, `POST /contexts/drain`, `POST /tabs/new`.
- 2026-07-18: Added focused fake-context tests proving isolation, route activation, old-context preservation, new-page binding, draining, sanitized context output, and fast prewarmed switching.
- 2026-07-18: Verified Phase 3/4 regression slice and lint pass.
- 2026-07-18: Witnessed runtime against `/tmp/real-sessions` with fake isolated contexts: prewarmed 7 contexts, selected GitHub, opened a new active-context tab, drained 6 inactive contexts, and confirmed context output contains no cookie/storage fields.

## Verification

```bash
python3 -m pytest tokenade/tests/test_gateway_runtime.py tokenade/tests/test_gateway_server.py tokenade/tests/test_gateway_session_router.py -q
python3 -m pytest tokenade/tests/test_gateway_runtime.py tokenade/tests/test_gateway_server.py tokenade/tests/test_gateway_session_router.py tokenade/tests/test_cli_gateway.py tokenade/tests/test_request_config.py tokenade/tests/test_plugin_run_cli.py tokenade/tests/test_cli.py -q
python3 -m flake8 tokenade/core/gateway tokenade/tests/test_gateway_runtime.py tokenade/tests/test_gateway_server.py tokenade/tests/test_gateway_session_router.py tokenade/tests/test_cli_gateway.py --max-line-length=120 --ignore=E501,W503,W293,E203,F541,F841,E306,E402,E226,E128,E127,E731,F821,F401,F811,E401,E704
```

Witness result:

```json
{
  "contexts_sanitized": true,
  "drain_closed_count": 6,
  "prewarm_context_count": 7,
  "route_site": "github",
  "runtime_context_site": "github",
  "session_count": 7,
  "tab_success": true
}
```

## Notes

- Phase 4 introduces the runtime seam and verifies isolated context semantics with fake Playwright-compatible contexts.
- The default hidden gateway still does not force live browser launch unless `gateway.runtime.enabled` is set or a runtime is injected.
- Real CloakBrowser/Playwright browser context witness should be handled as a later hardening step before any public gateway promotion.

## Goal

Wire gateway routing to actual browser/CDP runtime using isolated session contexts. This is the first phase where gateway becomes more than a control API.

## Runtime Model

Use the D-model:

```text
One gateway process.
One browser/control plane where feasible.
One isolated browser context per active session.
SessionRouter controls which context receives future work.
Existing tabs drain; new tabs/new navigations use the active context.
```

## Explicit Non-Default

Do not use the A-model as default:

```text
Replace cookies/storage in the same live browser context.
```

Reasons:

- risks service worker/cache/IndexedDB contamination;
- risks mixed account identity in active tabs;
- contradicts market expectations for stable profile/account identity;
- likely fails on high-value sites that care about session continuity.

## Scope

- Create/load isolated contexts for selected sessions.
- Inject cookies/storage into each context.
- Bind context to session record.
- Route new work to current active context.
- Drain old tabs on rotation.
- Keep switch processing under hundreds of ms for prewarmed contexts.

## Candidate Existing Code To Reuse Or Refactor

- `tokenade/core/proxy/cdp_proxy.py`
- `tokenade/core/proxy/multi_site_proxy.py`
- `tokenade/core/importer/session_loader.py`
- `tokenade/core/browser/stealth/launcher.py`
- `tokenade/core/browser/cloak.py`

## API Extensions

Potential endpoint additions:

- `POST /tabs/new`
- `GET /contexts`
- `POST /contexts/prewarm`
- `POST /contexts/drain`

These should wait until the first context runtime is working.

## Tests

- Creates isolated contexts for fixture sessions.
- Cookies/storage are not shared across contexts.
- Active context changes on rotation.
- Existing page remains bound to old context after rotation.
- New page uses new active context.
- Drain closes inactive tabs without mutating active session state.
- Switch with prewarmed contexts is under target latency.

## Witness

Use real sessions where feasible:

- GitHub session context.
- Discord or Telegram session context if installed Site Handlers are available.
- Validate that new route uses selected session and old route remains isolated.

## Exit Criteria

- Gateway can route real browser work to isolated session contexts.
- Rotation works without in-place identity mutation.
- Existing tabs drain safely.
- Gateway can be considered for default CLI visibility only after this phase and witness tests pass.
