# Phase 4: Gateway Runtime With Isolated Contexts

**Date:** 2026-07-18  
**Status:** Planned  
**Parent plan:** `.agent/plans/2026-07-18-gateway-request-framework.md`

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
