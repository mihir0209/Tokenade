# Phase 4: Marketplace Plugin Migration

## Goal

Bring every marketplace plugin to API 1.3.0 compatibility and validate each
plugin against its declared type and manifest.

## Scope

- Audit all 25 plugin directories.
- Add `API_VERSION = "1.3.0"` to every entry class.
- Set every manifest `api_version` to `1.3.0`.
- Normalize primary operation results to `PluginResult`.
- Correct misleading plugin types and isolate no-op utility handlers.
- Add `run` metadata only to plugins with a meaningful external operation.
- Add plugin-specific contract tests and run the plugin test tools.

## References

- `../tokenade-plugins/plugins/*/plugin.json`
- `../tokenade-plugins/plugins/*/plugin.py`
- `tokenade/plugin/base.py`
- `tokenade/plugin/api.py`
- `tokenade/core/integration/plugin_loader.py`
- `tokenade/core/integration/plugin_verifier.py`
- `tokenade/core/integration/plugin_security.py`

## Acceptance Criteria

- All marketplace plugins declare API 1.3.0.
- Every manifest entry class and type matches the implementation.
- Every plugin passes discovery, security, loading, and contract checks.
- External execution is explicit and schema-backed.
- No plugin silently claims a contract it does not implement.

## Dependencies

- Phases 1-3.
