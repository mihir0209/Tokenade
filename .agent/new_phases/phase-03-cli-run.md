# Phase 3: Generalized CLI Run

## Goal

Expose the runner through a generalized terminal command without plugin-
specific commands.

## Interface

```text
tokenade run <plugin-name> [method] --input request.json
```

The command owns only `--input`; plugin fields remain in the JSON request.
The method positional argument is optional and defaults from the manifest.

## Scope

- Add a two-stage argparse parser.
- Emit the result envelope as JSON on stdout.
- Send logs and diagnostics to stderr.
- Return exit codes `0`, `1`, or `2` according to the global contract.
- Add CLI tests for defaults, method selection, malformed input, and output.

## References

- `tokenade/cli/__init__.py`
- `.agent/new_phases/phase-02-plugin-runner.md`

## Acceptance Criteria

- No `oauth-automate` or other plugin-specific command exists.
- Existing CLI commands are unaffected.
- Shell callers can safely parse stdout as JSON.
- Plugin-specific arguments are never added as runner-owned flags.

## Dependencies

- Phases 1 and 2.
