# Next Phase: Comprehensive Test Coverage

**Date:** 2026-06-01
**Status:** In Progress
**Priority:** Critical (Blocking other features)
**Owner:** Tokenade Team

## Overview

The current test suite covers crypto and fingerprint modules (2/6 core modules).
This plan brings coverage to >80% across all components before adding new
features. Testing is the foundation - without it, adding handlers or APIs is
technical debt.

## Current State

| Module | Test File | Coverage | Status |
|--------|-----------|----------|--------|
| core.crypto | test_crypto.py | ~90% | ✅ Done |
| core.fingerprint | test_fingerprint.py | ~85% | ✅ Done |
| core.browser | None | 0% | ❌ Missing |
| core.runtime | None | 0% | ❌ Missing |
| core.security | None | 0% | ❌ Missing |
| handlers.base | None | 0% | ❌ Missing |
| handlers.google | None | 0% | ❌ Missing |
| handlers.github | None | 0% | ❌ Missing |
| cli | None | 0% | ❌ Missing |

## Execution Order

### Phase 1: Core Infrastructure Tests (Day 1)
1. **test_browser.py** - Mock Playwright, test BrowserManager lifecycle
2. **test_security.py** - Mock keyring, test CredentialManager, SecureSessionStorage

### Phase 2: Handler Tests (Day 2)
3. **test_handlers.py** - Mock page interactions, test GoogleHandler, GitHubHandler
4. **test_base_handler.py** - Test HandlerRegistry, abstract base class compliance

### Phase 3: Runtime & Integration (Day 3)
5. **test_runtime.py** - Mock HTTP responses, test RuntimeEngine, SessionValidator
6. **test_integration.py** - End-to-end: extract → save → load → inject workflow

### Phase 4: CLI & Performance (Day 4)
7. **test_cli.py** - Mock argparse, test command dispatch
8. **benchmarks/** - Performance tests for browser launch, cookie extraction

## Implementation Details

### Mock Strategy
```python
# Browser mock pattern
@pytest.fixture
def mock_browser():
    browser = MagicMock()
    browser.page = MagicMock()
    browser.page.evaluate.return_value = {"projects": []}
    browser.page.query_selector.return_value = True
    return browser

# HTTP mock pattern  
@responses.activate
def test_runtime_engine():
    responses.add(responses.GET, "https://api.github.com/user", json={"login": "test"})
    engine = RuntimeEngine(config)
    result = engine.get("https://api.github.com/user")
    assert result.status_code == 200
```

### Coverage Targets
- Unit tests: >80% line coverage
- Integration tests: All happy paths + 3 error paths per feature
- Benchmarks: Documented baselines for regression detection

## Success Criteria

- [ ] `pytest` runs all tests in <30 seconds
- [ ] Coverage report shows >80% overall
- [ ] All handlers have mocked integration tests
- [ ] CI pipeline configured (GitHub Actions workflow)
- [ ] No test failures on clean checkout

## Benefits

- **Safety Net:** Refactor handlers, add features, fix bugs with confidence
- **Documentation:** Tests show exactly how each component works
- **CI/CD Ready:** Automated testing enables continuous deployment
- **Onboarding:** New contributors understand codebase via tests
- **Regression Prevention:** Catch breaking changes immediately

## Risks

- **Mock complexity:** Playwright mocks may be verbose → Mitigation: Create reusable fixtures
- **Test flakiness:** HTTP mocks may fail intermittently → Mitigation: Use responses library, not real HTTP
- **Time investment:** 4 days of testing delays features → Mitigation: Parallel work on handlers possible after Day 2

## Dependencies

- pytest >= 7.0.0
- pytest-asyncio >= 0.21.0
- pytest-cov (for coverage reports)
- responses (for HTTP mocking)
- freezegun (for time-based tests)

## Notes

- Start with Phase 1 immediately
- Phase 2 can begin after test_browser.py is complete
- Integration tests should use temp directories, not real browser_data/
- All tests must pass in Docker container (`docker-compose run tokenade-dev pytest`)
