# Web Dashboard for Session Monitoring

**Date:** 2026-06-05
**Status:** Planned
**Priority:** Low
**Dependencies:** Session Refresh Mechanism

## Problem

Managing multiple sessions across multiple accounts requires checking each one individually. No unified view of session health.

## Solution

FastAPI-based web dashboard for monitoring and managing all sessions.

## Implementation Plan

### Phase 1: Core API
```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Session(BaseModel):
    id: str
    site_name: str
    status: str  # active, expired, expiring_soon
    expires_in: int  # seconds
    health_score: float
    last_validated: datetime
    source_browser: str

@app.get("/api/sessions")
async def list_sessions() -> List[Session]:
    """List all managed sessions."""

@app.get("/api/sessions/{id}/health")
async def check_health(id: str) -> SessionHealth:
    """Check session health."""

@app.post("/api/sessions/{id}/refresh")
async def refresh_session(id: str) -> RefreshResult:
    """Refresh session from source."""

@app.delete("/api/sessions/{id}")
async def delete_session(id: str):
    """Delete session."""
```

### Phase 2: Dashboard UI
- React-based SPA
- Session list with health indicators
- Real-time health monitoring
- One-click refresh
- Export/import functionality

### Phase 3: Notifications
```python
# Email alerts
@app.post("/api/notifications/config")
async def configure_notifications(config: NotificationConfig):
    """Configure email/webhook alerts."""

# Webhook integration
# - Slack
# - Discord
# - Telegram
# - Custom webhook
```

### Phase 4: Analytics
- Session usage statistics
- Health trends over time
- Export/import history
- Device fingerprint comparison

## Files

### New Files
- `tokenade/dashboard/app.py` - FastAPI application
- `tokenade/dashboard/models.py` - Pydantic models
- `tokenade/dashboard/routes/` - API routes
- `tokenade/dashboard/static/` - Frontend assets
- `tokenade/dashboard/templates/` - HTML templates

### Modified Files
- `tokenade/cli.py` - Add `tokenade serve` command
- `setup.py` - Add dashboard dependencies

## Estimated Effort

10 days for full-featured dashboard
