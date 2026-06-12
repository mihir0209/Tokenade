# Direct Profile Injection CLI Command

**Date:** 2026-06-05
**Status:** Planned
**Priority:** High
**Blocked by:** Nothing

## Problem

Currently, injecting cookies into a real browser profile requires manual SQLite manipulation (as we did for Brave testing). This should be a proper CLI command with error handling, backup, and safety checks.

## Solution

Add `tokenade inject-profile` command that directly modifies the target browser's cookie database.

## Implementation Plan

### Phase 1: ProfileManager (Days 1-2)
```python
class ProfileManager:
    """Manages browser profile cookie injection."""
    
    def inject_cookies(self, profile_path, cookies, backup=True):
        """Inject cookies into browser profile."""
        # 1. Create backup
        # 2. Copy database to temp
        # 3. Insert cookies with correct schema
        # 4. Copy back
        # 5. Verify injection
    
    def backup_profile(self, profile_path):
        """Create timestamped backup."""
    
    def restore_profile(self, backup_path):
        """Restore from backup."""
```

### Phase 2: Browser Profile Discovery (Day 3)
- Extend `browser_discovery.py` to find active profile paths
- Support Chrome, Firefox, Brave, Edge, Opera, Vivaldi
- Auto-detect profile from running browser instance

### Phase 3: CLI Integration (Day 4)
```bash
# Inject into running browser profile
tokenade inject-profile --browser brave --session chatgpt.tokenade --site chatgpt

# With custom profile path
tokenade inject-profile --profile /path/to/cookies.sqlite --session chatgpt.tokenade

# With backup and verification
tokenade inject-profile --browser chrome --session chatgpt.tokenade --verify
```

### Phase 4: Safety Features (Day 5)
1. Auto-backup before modification
2. Verify injection succeeded
3. Warn if browser is running
4. Support dry-run mode
5. Conflict detection (existing cookies)

## Files

### New Files
- `tokenade/core/injector/profile_manager.py` - Profile management
- `tokenade/core/injector/cookie_injector.py` - Database manipulation
- `tokenade/tests/test_profile_manager.py` - Tests

### Modified Files
- `tokenade/cli.py` - Add inject-profile command
- `tokenade/core/importer/browser_discovery.py` - Active profile detection

## Success Criteria

- [ ] Works with Chrome, Brave, Edge, Opera, Vivaldi
- [ ] Creates backup before modification
- [ ] Verifies injection succeeded
- [ ] Handles browser lock files gracefully
- [ ] Supports dry-run mode
- [ ] All tests pass

## Estimated Effort

5 days for production-ready profile injection
