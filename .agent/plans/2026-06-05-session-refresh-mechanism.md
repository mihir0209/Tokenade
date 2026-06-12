# Session Refresh Mechanism

**Date:** 2026-06-05
**Status:** Planned
**Priority:** Medium

## Problem

Sessions expire. Currently, users must manually re-export from the source browser when cookies expire. This breaks automation workflows.

## Solution

Automatic session refresh by re-fetching cookies from source browser or using refresh tokens.

## Implementation Plan

### Phase 1: Expiry Detection
```python
class SessionHealthChecker:
    def check_session(self, session_file: str) -> SessionHealth:
        """Check if session is still valid."""
        return SessionHealth(
            expired=False,
            expires_in=3600,  # seconds
            health_score=0.85,
            recommendations=["refresh_needed"]
        )
```

### Phase 2: Auto-Refresh from Source
```bash
# Check session health
tokenade health chatgpt.tokenade

# Refresh from source browser
tokenade refresh chatgpt.tokenade --source-browser firefox

# Auto-refresh when expired
tokenade load chatgpt.tokenade --auto-refresh --source-browser firefox
```

### Phase 3: Refresh Token Support
```json
{
  "site_name": "chatgpt",
  "refresh_tokens": {
    "cookie": "__Secure-next-auth.session-token",
    "refresh_url": "https://chatgpt.com/api/auth/refresh",
    "method": "POST"
  }
}
```

### Phase 4: Scheduled Refresh
```bash
# Add to cron
tokenade schedule add chatgpt --refresh-interval 24h --source-browser firefox

# View schedule
tokenade schedule list

# Manual trigger
tokenade schedule run chatgpt
```

## Files

### New Files
- `tokenade/core/refresh/health_checker.py` - Session health checks
- `tokenade/core/refresh/refresher.py` - Auto-refresh logic
- `tokenade/core/refresh/scheduler.py` - Cron scheduling
- `tokenade/tests/test_refresh.py` - Tests

### Modified Files
- `tokenade/core/importer/session_loader.py` - Add --auto-refresh
- `tokenade/cli.py` - Add refresh, health, schedule commands

## Estimated Effort

5 days
