# Phase 2: Plugin Runner

## Goal

Implement the lifecycle-aware core execution engine for one installed plugin.

## Scope

- Add `PluginRunner` under `tokenade/core/integration/`.
- Discover plugins from `~/.tokenade/plugins/` using the existing loader.
- Apply security validation and the normal load/configure lifecycle.
- Require `run.enabled` for external execution.
- Select the manifest default method or an explicitly requested method.
- Enforce the `process`, `run`, and `refresh_session` allowlist.
- Load flat JSON input, validate it, apply defaults, and reject unknown fields.
- Invoke the method with keyword arguments.
- Normalize `PluginResult`, dictionaries, and invocation failures into a
  stable result envelope.
- Always unload/clean up the plugin after invocation.

## References

- `tokenade/core/integration/plugin_loader.py`
- `tokenade/plugin/api.py`
- `.agent/new_phases/phase-01-api-contract.md`

## Acceptance Criteria

- Internal-only plugins cannot be run.
- Invalid manifests and inputs produce structured runner errors.
- Plugin failures are distinguishable from runner failures.
- Lifecycle cleanup happens on success and failure.
- No CLI code is required to test the runner.

## Dependencies

- Phase 1.
