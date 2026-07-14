# Phase 5: Registry Repair

## Goal

Make marketplace registry metadata complete and synchronized with actual
plugin manifests.

## Scope

- Regenerate or update `plugins.json` from plugin manifests.
- Add missing `google-flow-handler` and `oauth-flow-handler` entries.
- Correct stale versions and API versions.
- Validate one-to-one coverage between plugin directories and registry entries.
- Add a repeatable registry validation/generation tool or test.

## References

- `../tokenade-plugins/plugins.json`
- `../tokenade-plugins/marketplace.json`
- `../tokenade-plugins/plugins/*/plugin.json`
- `tokenade/core/integration/plugin_registry.py`

## Acceptance Criteria

- Every plugin directory appears exactly once in `plugins.json`.
- Registry fields match the source manifest.
- Generation/validation reports drift clearly.
- Marketplace installation can find every published plugin.

## Dependencies

- Phase 4.
