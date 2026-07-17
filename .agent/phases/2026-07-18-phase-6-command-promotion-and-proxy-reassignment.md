# Phase 6: Command Promotion And Proxy Reassignment

**Date:** 2026-07-18  
**Status:** Planned  
**Parent plan:** `.agent/plans/2026-07-18-gateway-request-framework.md`

## Goal

Promote only witnessed commands to the public CLI and reassign old overloaded proxy semantics cleanly.

## Command Vocabulary

```text
gateway = local multi-session/session-context control plane
proxy = upstream network proxy tooling
launch = open one session in a browser
run = execute request.json plugin operations
```

## Promotion Rule

A command becomes visible in top-level help only after:

- it works end-to-end;
- it has local tests;
- it has at least one real or realistic witness;
- docs/help text are honest about what the command does.

## Gateway Promotion Criteria

- `gateway --request request.json` starts successfully.
- Loads real `.tokenade` sessions.
- Validates required plugins.
- Exposes control API.
- Routes new browser work to isolated session contexts.
- Rotates active session context without in-place state mutation.
- Existing tabs drain.
- Witness tests pass with real sessions.

## Proxy Reassignment Criteria

The `proxy` command should become visible only when it means upstream network proxy tooling.

Expected future command ideas:

```bash
tokenade proxy resolve --request request.json
tokenade proxy health --request request.json
tokenade proxy test --request request.json
```

Outputs must redact secrets by default.

## Old Proxy Handling

The current overloaded local/CDP proxy behavior should not be exposed as `proxy` in the final public surface.

Options after gateway is real:

- migrate old local proxy behavior into `gateway`;
- delete obsolete flags;
- keep temporary hidden aliases only if useful for tests or transition.

There are no known external users, so breaking changes are acceptable.

## Tests

- `gateway` hidden before runtime is witnessed.
- `gateway` visible only after promotion slice.
- `proxy` visible only with upstream proxy semantics.
- Top-level help has no overloaded or misleading command descriptions.
- Completion scripts match visible commands.

## Exit Criteria

- Public CLI matches product vocabulary.
- `gateway` and `proxy` no longer conflict conceptually.
- Hidden legacy command paths are either removed or intentionally retained with tests.
