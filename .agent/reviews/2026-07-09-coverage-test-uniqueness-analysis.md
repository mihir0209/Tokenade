# Coverage Test Uniqueness Analysis

**Date:** 2026-07-09  
**Policy:** No bulk deletes. Delete only when uniqueness analysis proves redundancy. Prefer mutation testing over line-coverage theater.

## Method

For each `*_coverage*.py` file:

1. Extract test function/class names via AST
2. Compare numbered siblings (`coverage` vs `coverage2` / `coverage4`)
3. Check for non-coverage counterparts (`test_<module>.py`)
4. Classify: **KEEP**, **RENAME** (unique but poorly named), **DELETE** (redundant or zero behavioral value)

## Numbered siblings — NOT duplicates

| Group | Files | Result |
|-------|-------|--------|
| cdp_injection | `coverage.py` (56) + `coverage4.py` (11) | **0 method-name overlap** — coverage4 is edge/raw-CDP paths. **KEEP both**, rename coverage4. |
| local_storage_extractor | `coverage.py` (23) + `coverage2.py` (21) | **Nearly disjoint** (plyvel mock paths unique to coverage2). **KEEP both**, rename coverage2. |
| profile_manager | `coverage.py` (22) + `coverage2.py` (14) | **Disjoint** (error-string paths unique to coverage2). **KEEP both**, rename coverage2. |
| session_sharer | `coverage2.py` only (12) | QR/version edge paths. **KEEP**, rename. |

**Conclusion:** Numbered “coverage N” files are **sequential edge-path dumps**, not re-runs of the same tests. Bulk-deleting them would **delete unique mutants**.

## Tiny / theater files

| File | Tests | Decision |
|------|------:|----------|
| `test_cli_main_coverage.py` | 2 | `hasattr(main)` + `callable(main)` — **no behavioral assertion**. **DELETE** (covered by hundreds of CLI command tests). |
| `test_site_configs_coverage.py` | 3 | Weak smoke; JSON overlay not tested. **REPLACE** with real `test_site_configs.py` (list + unknown + overlay). |
| `test_credentials_coverage.py` | 4 | Keyring exception paths — **unique**. **RENAME** → `test_credentials_keyring_errors.py`. |
| `test_coverage_boost.py` | 80 | Bad name; contains **only** FormatImporter suite (no dedicated non-coverage file). **RENAME** → `test_format_importer_and_helpers.py`. |

## Large single coverage files

Files like `test_cdp_routing_coverage.py`, `test_engine_coverage.py`, etc. target modules that often **lack** a parallel non-coverage suite. They stay until a dedicated behavioral suite exists and mutation score shows redundancy.

## Mutation testing direction

Line coverage incentivizes empty asserts and path spam. Mutation testing (mutmut) measures whether tests kill intentional code bugs.

- Dev optional: `mutmut`
- Config: `mutmut` section / `setup.cfg` or `pyproject.toml`
- Scope first: `tokenade/core/crypto`, `tokenade/core/proxy/cdp_injection.py`, `tokenade/handlers/resolve.py` (small, high value)
- Do **not** require 100% kill rate on first pass; track baseline and improve

## Actions taken this batch

1. DELETE `test_cli_main_coverage.py` (trivial)
2. REPLACE `test_site_configs_coverage.py` with mutation-oriented `test_site_configs.py`
3. RENAME credentials / coverage_boost / numbered edge files to honest names
4. Add mutmut config + Makefile target + short docs note
5. Full suite must pass

## Explicit non-actions

- No bulk delete of the 50+ coverage files
- No deletion of coverage2/4 edge suites without per-test diff
