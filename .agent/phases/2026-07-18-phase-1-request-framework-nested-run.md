# Phase 1: Request Framework And Nested Run

**Date:** 2026-07-18  
**Status:** Planned  
**Parent plan:** `.agent/plans/2026-07-18-gateway-request-framework.md`

## Goal

Create the nested `request.json` backbone and make `tokenade run --request request.json` execute ordered plugin operations from it.

## Scope

- Add a request/config loader module.
- Support nested request envelopes with explicit `operation`.
- Parse ordered `plugins[]` entries.
- Validate required plugin availability.
- Execute plugins with `roles.run` in order.
- Return machine-readable JSON output with one result per plugin operation.

## Request Shape

```json
{
  "version": "1",
  "operation": "run",
  "plugins": [
    {
      "name": "generic-handler",
      "required": true,
      "roles": {
        "run": {
          "method": "process"
        }
      },
      "config": {
        "session_file": "/tmp/real-sessions/github.tokenade",
        "site": "github"
      }
    }
  ],
  "execution": {
    "stop_on_error": true
  }
}
```

## Core Rules

- `operation` is required.
- `plugins` must be an ordered array when present.
- Each plugin entry must have `name`.
- `roles` must be a dict if provided.
- `config` must be an object if provided, but contents are dynamic and pass-through.
- Required missing plugins fail before execution.
- Missing plugin suggestions:
  ```text
  tokenade plugin install <name>
  tokenade plugin install <name> --registry <registry-name-or-url>
  ```
- `run` operations execute only plugin entries with `roles.run`.
- Plugin method defaults to manifest default method if `roles.run.method` is absent.
- `execution.stop_on_error` defaults to `true`.

## Candidate Files

- `tokenade/core/request_config.py`
- `tokenade/core/integration/plugin_runner.py`
- `tokenade/cli/__init__.py`
- `tokenade/tests/test_request_config.py`
- `tokenade/tests/test_cli_run_request.py`

## Implementation Notes

- Reuse `PluginRunner` for actual plugin execution where possible.
- Extend `PluginRunner` to accept nested plugin config as request kwargs.
- Avoid over-validating plugin-specific config.
- Keep output JSON serializable and deterministic.
- Consider whether old `tokenade run <plugin> --input` should be removed or produce a targeted migration error.

## Expected CLI

```bash
tokenade run --request request.json
```

## Expected Output

```json
{
  "success": true,
  "operation": "run",
  "results": [
    {
      "success": true,
      "plugin": "generic-handler",
      "method": "process",
      "data": {},
      "error": null
    }
  ]
}
```

## Tests

- Loads valid nested request.
- Rejects missing `operation`.
- Rejects non-array `plugins`.
- Fails closed for missing required plugin with install suggestions.
- Allows missing optional plugin and records skipped/ignored status.
- Executes one plugin from nested request.
- Executes multiple plugins in order.
- Stops on first failure by default.
- Continues when `execution.stop_on_error=false`.
- Existing visible CLI tests continue to show `run` as public.

## Witness

Use installed marketplace `generic-handler`:

```bash
tokenade run --request /tmp/tokenade-run-generic-github.request.json
```

Expected: validates `/tmp/real-sessions/github.tokenade` successfully through `generic-handler.process`.

## Exit Criteria

- Nested `run --request` works with a real installed plugin.
- Plugin config pass-through is proven.
- Missing required plugin UX is clear.
- Tests and lint pass.
