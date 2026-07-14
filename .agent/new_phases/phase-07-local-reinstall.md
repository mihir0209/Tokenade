# Phase 7: Local Plugin Reinstall

## Goal

Prove that a clean user installation can discover and load the newly published
plugins.

## Scope

- Snapshot current `~/.tokenade` state if needed for diagnosis.
- Delete the old installed plugin directory only after Phase 6 succeeds.
- Recreate the normal installation directory.
- Install selected plugins through the supported registry command.
- Verify dependency installation, discovery, security, and loading.

## References

- `tokenade/core/integration/plugin_registry.py`
- `tokenade/core/integration/plugin_loader.py`
- `~/.tokenade/plugins/`
- `.agent/new_phases/phase-06-marketplace-release.md`

## Acceptance Criteria

- No stale plugin files remain in the clean installation.
- Selected API 1.3.0 plugins install from the registry.
- Loader reports the expected versions and capabilities.
- Installation is reproducible without repository-local paths.

## Dependencies

- Phase 6.
