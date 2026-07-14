# Phase 1: API 1.3.0 Contract

## Goal

Establish one canonical plugin API version and reusable validation types for
external plugin execution. This phase must not add the CLI runner yet.

## Scope

- Bump the canonical API version from `1.1.0` to `1.3.0`.
- Align `PluginBase.API_VERSION` with the canonical version.
- Define manifest execution metadata for optional external operations.
- Define request argument schema validation and type coercion helpers.
- Define structured runner error codes and JSON result envelope types.
- Preserve compatibility for plugins that omit the optional `run` section.

## Contract

The manifest uses a `run` object:

```json
{
  "run": {
    "enabled": true,
    "default_method": "process",
    "methods": {
      "process": {
        "arguments": {
          "session_file": {"type": "path", "required": true},
          "output_dir": {"type": "path", "required": false, "default": null}
        }
      }
    }
  }
}
```

Supported executable methods in the first contract are `process`, `run`, and
`refresh_session`. The runner will enforce the method allowlist in Phase 2.

Input is a flat JSON object. Argument names map directly to Python keyword
arguments. Unknown fields are invalid. The schema supports required fields,
defaults, and these types: `string`, `path`, `int`, `float`, `bool`, `list`,
`object`.

## References

- `tokenade/plugin/api.py`
- `tokenade/plugin/base.py`
- `tokenade/core/integration/plugin_loader.py`
- `tokenade/core/integration/plugin_security.py`
- `tokenade-plugins/plugins/google-flow-handler/plugin.json`
- `.agent/plans/google-oauth-automation-plugin.md`

## Acceptance Criteria

- There is exactly one canonical API version constant: `1.3.0`.
- API metadata and schema helpers are unit tested.
- A manifest without `run` remains valid as an internal plugin manifest.
- An enabled `run` manifest rejects malformed methods and argument schemas.
- Result and error objects serialize deterministically to JSON-compatible data.
- Existing plugin tests continue to pass.

## Dependencies

- None.

## Output

- API constants and dataclasses/helpers.
- Focused tests for API version, manifest schema, argument validation, and
  result/error serialization.
