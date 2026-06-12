# Web Dashboard and REST API Server

**Date:** 2026-06-01
**Status:** Planned
**Priority:** Medium

## Overview

Currently Tokenade is CLI-only. This plan adds a web dashboard and REST API
for remote management, monitoring, and integration with other tools.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Web UI    │────▶│  REST API    │────▶│  Tokenade   │
│  (React)    │     │  (FastAPI)   │     │   Core      │
└─────────────┘     └──────────────┘     └─────────────┘
                           │
                    ┌──────┴──────┐
                    │  Database   │
                    │  (SQLite)   │
                    └─────────────┘
```

## Features

### REST API Endpoints
- `POST /accounts` - Add account
- `GET /accounts` - List accounts
- `POST /extract` - Extract session
- `POST /transfer` - Transfer session
- `GET /sessions` - List sessions
- `POST /test` - Run portability test
- `GET /fingerprints` - List fingerprints
- `POST /fingerprints/collect` - Collect fingerprint

### Web Dashboard
- Account management UI
- Session browser with cookie inspection
- Real-time portability test results
- Fingerprint comparison visualizer
- Session timeline (when extracted, transferred, expired)

## Implementation

```python
# FastAPI example
from fastapi import FastAPI
from tokenade import CredentialManager, BrowserFactory

app = FastAPI()

@app.post("/extract")
async def extract_session(account_id: int):
    manager = CredentialManager()
    account = manager.get_account(account_id)
    # ... extraction logic
    return {"status": "success", "session": session_data}
```

## Benefits

- **Remote Management:** Manage sessions from anywhere
- **Integration:** Other tools can call the API
- **Visualization:** See session health at a glance
- **Collaboration:** Multiple users can share session pool
- **Automation:** Schedule extractions and tests

## Success Criteria

- [ ] REST API with OpenAPI documentation
- [ ] Web dashboard with all CRUD operations
- [ ] Authentication and authorization
- [ ] Session health monitoring with alerts
- [ ] Docker deployment ready

## Estimated Effort

2-3 weeks for full web stack
