# Phase 6: Command Promotion And Proxy Reassignment

**Date:** 2026-07-18  
**Status:** Complete  
**Parent plan:** `.agent/plans/2026-07-18-gateway-request-framework.md`

## Progress

- 2026-07-18: Started implementation.
- 2026-07-18: Gateway remains hidden because Phase 4 has a real-session/fake-context witness but not a live CloakBrowser/Playwright context witness.
- 2026-07-18: Proxy will be reassigned to upstream proxy-provider tooling with visible `proxy resolve --request`; old local/CDP proxy behavior will move under hidden `proxy legacy`.
- 2026-07-18: Made `proxy` visible as upstream provider tooling and kept `gateway` hidden.
- 2026-07-18: Added `tokenade proxy resolve --request request.json` with redacted output by default and optional `--show-secrets`.
- 2026-07-18: Moved old overloaded local/CDP proxy behavior behind hidden `tokenade proxy legacy` instead of top-level `proxy` semantics.
- 2026-07-18: Updated completion scripts and parser-surface tests to match the public command surface.
- 2026-07-18: Verified broader CLI/gateway/proxy regression slice and witnessed help surface plus redacted `proxy resolve` output.
- 2026-07-18: Promoted `gateway` after a live CloakBrowser hidden-gateway HTTP witness passed against `/tmp/real-sessions/github.tokenade`.

## Verification

```bash
python3 -m pytest tokenade/tests/test_proxy_provider_resolver.py tokenade/tests/test_cli.py tokenade/tests/test_cli_refactor.py -q
python3 -m pytest tokenade/tests/test_proxy_provider_resolver.py tokenade/tests/test_source_network_context.py tokenade/tests/test_cli_gateway.py tokenade/tests/test_gateway_server.py tokenade/tests/test_gateway_runtime.py tokenade/tests/test_gateway_session_router.py tokenade/tests/test_request_config.py tokenade/tests/test_plugin_run_cli.py tokenade/tests/test_cli.py tokenade/tests/test_cli_refactor.py -q
python3 -m flake8 tokenade/cli/proxy.py tokenade/cli/__init__.py tokenade/cli/completions.py tokenade/tests/test_proxy_provider_resolver.py tokenade/tests/test_cli.py tokenade/tests/test_cli_refactor.py --max-line-length=120 --ignore=E501,W503,W293,E203,F541,F841,E306,E402,E226,E128,E127,E731,F821,F401,F811,E401,E704
```

Witness results:

```text
HELP_SURFACE {"gateway_hidden": true, "old_proxy_text_hidden": true, "proxy_visible": true}
PROXY_RESOLVE {"operation": "proxy.resolve", "password": "***", "provider": "fake-provider", "secret_exposed": false, "success": true}
```

## Promotion Decision

- `proxy` is public because it now means upstream proxy-provider tooling and has provider resolver tests plus a redaction witness.
- `gateway` is public because live CloakBrowser hidden-gateway HTTP runtime witness now passes against a real session.

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
