# Multi-Site Batch Export/Load

**Date:** 2026-06-05
**Status:** Planned
**Priority:** Medium

## Problem

Currently, users must export and load sites one at a time. For users with many accounts (social media, banking, work), this is tedious.

## Solution

Batch operations that handle multiple sites simultaneously.

## Implementation Plan

### Phase 1: Batch Export
```bash
# Export all supported sites
tokenade export --batch --browser firefox --all

# Export from config file
tokenade export --batch --browser firefox --sites sites.json
```

**sites.json:**
```json
[
  {"name": "chatgpt", "url": "chatgpt.com", "auth_cookies": ["__Secure-next-auth.session-token"]},
  {"name": "github", "url": "github.com", "auth_cookies": ["user_session"]},
  {"name": "twitter", "url": "twitter.com", "auth_cookies": ["auth_token"]}
]
```

### Phase 2: Batch Load
```bash
# Load all sites from directory
tokenade load --batch --dir ./sessions/ --target brave

# Load from manifest
tokenade load --batch --manifest sessions.json --target brave
```

### Phase 3: Progress & Reporting
```bash
# Export with progress
tokenade export --batch --browser firefox --all --progress

# Generate report
tokenade export --batch --browser firefox --all --report report.json
```

**report.json:**
```json
{
  "timestamp": "2026-06-05T12:00:00Z",
  "source_browser": "firefox",
  "sites_exported": 5,
  "cookies_total": 150,
  "sites": [
    {"name": "chatgpt", "status": "success", "cookies": 31},
    {"name": "github", "status": "success", "cookies": 45}
  ]
}
```

## Files

### New Files
- `tokenade/core/batch/exporter.py` - Batch export logic
- `tokenade/core/batch/loader.py` - Batch load logic
- `tokenade/core/batch/manifest.py` - Manifest management
- `tokenade/tests/test_batch.py` - Tests

### Modified Files
- `tokenade/cli.py` - Add --batch flag and batch commands

## Estimated Effort

3 days
