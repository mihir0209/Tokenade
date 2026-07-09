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

## P7 follow-up (2026-07-09)

### Network / slow markers
- `TestTLSMatcherIntegration` → `@pytest.mark.network` (class)
- `test_proxy.py::test_chrome_tls_matching`, `test_firefox_fallback_to_chrome` → network
- `test_playwright_e2e.py` → `pytestmark = [pytest.mark.slow]`

### Proven near-duplicates removed (method-level only)
From `test_advanced_validator_coverage.py` (renamed `test_advanced_validator_edge_cases.py`):
- `TestValidationResult.test_defaults` / `test_with_details` (duplicate of base)
- `TestValidationRule.test_defaults` (duplicate of base)
- `TestLoadAndCreateRules.test_load_defaults` (duplicate of base)

Kept: all unique edge/API paths in the renamed file; `TestValidationRule.test_custom_values`.

### Large coverage files re-checked (not deleted)
| File | Sibling | Method-name overlap | Decision |
|------|---------|--------------------:|----------|
| advanced_validator_coverage | yes | 3 near-identical | trimmed dups, renamed |
| cdp_routing_coverage | none | — | KEEP (sole suite) |
| engine_coverage | none | — | KEEP |
| browser_manager_coverage | none | — | KEEP |
| forward_proxy_coverage | yes | 1 name, different body | KEEP both |
| session_packager_coverage | yes | 1 name, different body | KEEP both |
| session_loader_coverage | yes | 0 | KEEP |

### Body-hash pass on name overlaps (P7)

Same `test_*` name ≠ same test. Normalized-source SHA of overlapping methods:

| Pair | Name overlap | Identical body | Decision |
|------|-------------:|---------------:|----------|
| profile_manager_coverage vs profile_manager | 6 | **0** | KEEP both |
| batch_operations_coverage vs batch_operations | 5 | **0** | KEEP both |
| session_monitor_coverage vs session_monitor_enhanced | 5 | **0** | KEEP both |
| session_sync_coverage vs session_sync | 4 | **0** | KEEP both |
| fingerprint_collectors_coverage vs base | 3 | **0** | KEEP both |
| local_storage_extractor_coverage vs base | 2 | **0** | KEEP both |
| tls_matcher_coverage vs base | 2 | **0** | KEEP both |

**Conclusion:** No bulk/method delete justified beyond advanced_validator near-dups already removed. Further cleanup needs mutmut survivors or line-by-line proof, not name matching.

### Mutmut
- Paths: `resolve.py`, `errors.py`, `encryptor.py`, `site_configs.py`
- Runner excludes `-m 'not network'`; `backup = false` (avoid dirtying tree)
- `make test-mut` / `make test-mut-ci`
- After mutmut runs: restore any accidental source edits; `.mutmut-cache` / `mutants/` gitignored

## Mutmut baseline (2026-07-09, mutmut 2.5.1)

### Pass 1 (partial, pre-killers)
| Metric | Value |
|--------|------:|
| Scope | resolve + errors + encryptor + site_configs |
| Checked | ~23 / 433 |
| 🎉 Killed | 10 |
| 🙁 Survived | 13 |

### Pass 2 (P8 killers — complete high-value slice)

| Metric | Value |
|--------|------:|
| Scope | `resolve.py` + `errors.py` + `encryptor.py` |
| Mutants | **127** |
| 🎉 Killed | **127** |
| 🙁 Survived | **0** |
| Kill rate | **100%** |

**What killed the first survivors:**
- Alias/default mutations that still returned `GoogleHandler` via fallback → registry isolation + unique handler classes
- `TokenadeError` attribute nulling → `test_errors.py` exact attribute asserts
- Exact `MAGIC` / constants / error strings (`XX...XX` wrappers) → exact equality asserts
- `hasattr(self, 'config')` → encrypt/decrypt with non-default `EncryptionConfig.iterations`
- File umask `0o177`, log messages, `decrypt_session` path defaults → permission + path + caplog tests

**Not in 100% gate:** `site_configs.py` static tables (hundreds of string mutants; keep behavioral tests only).

**Config notes:**
- Pin `mutmut>=2.4.0,<3` — mutmut 3 expects top-level `tests/`
- `backup = false` — never leave source dirty
- `make test-mut` / `make test-mut-ci`
- Killers live in `test_mutmut_killers.py`, `test_errors.py`, strengthened encryptor/resolve/site_configs
