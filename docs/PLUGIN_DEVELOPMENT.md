# Plugin Development Guide

## Overview

Tokenade plugins extend the tool's capabilities. Plugins can:
- Refresh sessions (OAuth2, API tokens)
- Handle site-specific extraction/injection
- Add custom export formats
- Validate session health
- Provide stealth patches
- Solve CAPTCHAs

## Plugin Structure

```
my-plugin/
├── plugin.json     # Plugin manifest (required)
├── plugin.py       # Plugin code (required)
└── README.md       # Documentation (optional)
```

## Plugin Manifest (plugin.json)

```json
{
    "name": "my-plugin",
    "version": "1.0.0",
    "description": "What this plugin does",
    "author": "Your Name",
    "category": "authentication",
    "tags": ["oauth", "google", "refresh"],
    "type": "session_refresh",
    "entry_point": "plugin.py",
    "entry_class": "MyPlugin",
    "dependencies": [],
    "min_version": "6.0.0",
    "verified": false,
    "icon": "🔐"
}
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique plugin name (lowercase, hyphens) |
| `version` | string | Semver version |
| `description` | string | Brief description |
| `author` | string | Author name |
| `type` | string | Plugin type (see below) |
| `entry_point` | string | Python file with plugin class |
| `entry_class` | string | Class name to instantiate |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `category` | string | Category for marketplace |
| `tags` | array | Searchable tags |
| `dependencies` | array | Python package dependencies |
| `min_version` | string | Minimum tokenade version |
| `verified` | boolean | **Only true after contract tests + human review** (default false) |
| `api_version` | string | Plugin API version (e.g. `1.0.0`) |
| `icon` | string | Emoji icon for marketplace |

### Forbidden vanity fields

Do **not** add hand-edited `downloads` or `rating` to manifests. Those fields are omitted until real telemetry exists. Inventing them is a honesty-policy violation.

### Plugin Types

| Type | Base Class | Purpose |
|------|------------|---------|
| `session_refresh` | `SessionRefreshPlugin` | Refresh sessions (OAuth2, API tokens) |
| `handler` | `SiteHandlerPlugin` | Site-specific extraction/injection |
| `export_format` | `ExportFormatPlugin` | Custom export formats |
| `validator` | `SessionValidatorPlugin` | Session health validation |
| `stealth` | `StealthPlugin` | Browser stealth patches |
| `proxy` | `ProxyProviderPlugin` / `ProxyPlugin` | Proxy providers |
| `notification` | `NotificationPlugin` | Webhooks / alerts |
| `captcha` | `CaptchaPlugin` | CAPTCHA solving |

### Crypto rule

Session encryption must use `tokenade.core.crypto.encryptor.TokenadeEncryptor` (AES-256-GCM, PBKDF2 600k). Plugins must not ship weaker parallel crypto.

## Writing a Plugin

### Example: Session Refresh Plugin

```python
"""
My OAuth2 Plugin for Tokenade.

Refreshes sessions using OAuth2 refresh token flow.
"""

import logging
import time
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class MyOAuth2Plugin:
    """OAuth2 session refresh plugin."""

    name = "my-oauth2"
    version = "1.0.0"
    description = "OAuth2 refresh for my service"
    author = "My Name"
    dependencies = []

    def can_refresh(self, session: dict) -> bool:
        """Check if this plugin can refresh the given session."""
        cookies = session.get("cookies", [])
        domains = {c.get("domain", "") for c in cookies}
        return any("myservice.com" in d for d in domains)

    def refresh(self, session: dict, credentials: dict) -> dict:
        """Refresh the session.

        Args:
            session: Current session data
            credentials: Plugin-specific credentials

        Returns:
            Updated session with fresh tokens
        """
        client_id = credentials.get("client_id", "")
        refresh_token = credentials.get("refresh_token", "")

        if not client_id:
            raise ValueError("Missing client_id")
        if not refresh_token:
            raise ValueError("Missing refresh_token")

        # Exchange refresh token for new access token
        # ... your OAuth2 logic here ...

        # Update session metadata
        session["metadata"]["last_refreshed"] = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
        )

        return session

    def get_credentials_args(self) -> List[Dict[str, str]]:
        """Define CLI arguments needed for credentials."""
        return [
            {"name": "--client-id", "help": "OAuth2 client ID",
             "required": True, "type": str},
            {"name": "--refresh-token", "help": "OAuth2 refresh token",
             "required": True, "type": str},
        ]
```

### Example: Site Handler Plugin

```python
"""
My Site Handler for Tokenade.

Handles session extraction and injection for mysite.com.
"""

import logging
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)

MY_DOMAINS = ["mysite.com", ".mysite.com"]
CRITICAL_COOKIES = ["session_id", "auth_token", "user_prefs"]


class MySiteHandler:
    """My site handler plugin."""

    name = "mysite-handler"
    version = "1.0.0"
    description = "Site handler for mysite.com"
    author = "My Name"
    dependencies = []

    def can_handle(self, url: str) -> bool:
        """Check if this handler can handle the given URL."""
        return any(d.lstrip(".") in url for d in MY_DOMAINS)

    def extract_session(self, browser_context: Any, url: str) -> dict:
        """Extract session from browser context."""
        cookies = browser_context.cookies()
        my_cookies = [
            c for c in cookies
            if any(d.lstrip(".") in c.get("domain", "") for d in MY_DOMAINS)
        ]

        return {
            "version": "2.0",
            "site_name": "mysite",
            "auth_status": "logged_in",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "cookies": my_cookies,
            "local_storage": {},
            "metadata": {"handler": "mysite-handler"},
        }

    def inject_session(self, browser_context: Any, session: dict) -> bool:
        """Inject session into browser context."""
        cookies = session.get("cookies", [])
        try:
            browser_context.add_cookies(cookies)
            return True
        except Exception as e:
            logger.error(f"Injection failed: {e}")
            return False

    def validate(self, session: dict) -> Dict[str, Any]:
        """Validate a session."""
        cookies = session.get("cookies", [])
        cookie_names = {c.get("name", "") for c in cookies}
        missing = [c for c in CRITICAL_COOKIES if c not in cookie_names]

        score = ((len(CRITICAL_COOKIES) - len(missing)) / len(CRITICAL_COOKIES)) * 100

        return {
            "valid": score >= 50,
            "score": score,
            "issues": [f"Missing: {', '.join(missing)}"] if missing else [],
            "recommendations": ["Re-export session"] if missing else [],
        }
```

## Installing a Plugin

### From Registry
```bash
tokenade plugin install my-plugin
```

### From Local Directory
```bash
cp -r my-plugin ~/.tokenade/plugins/
tokenade plugin reload my-plugin
```

## Testing a Plugin

```bash
# Run plugin test suite
tokenade plugin test my-plugin

# Verify integrity
tokenade plugin verify my-plugin
```

## Publishing a Plugin

1. Create a GitHub repository with your plugin
2. Add a `plugin.json` manifest
3. Submit a PR to [mihir0209/tokenade-plugins](https://github.com/mihir0209/tokenade-plugins)

### Plugin Repository Structure

```
my-plugins-repo/
├── plugins.json          # Registry file (list of all plugins)
├── marketplace.json      # Marketplace metadata
└── plugins/
    ├── plugin-a/
    │   ├── plugin.json
    │   └── plugin.py
    └── plugin-b/
        ├── plugin.json
        └── plugin.py
```

## Best Practices

1. **Keep it simple** — One plugin, one purpose
2. **Handle errors gracefully** — Return False on failure, log errors
3. **Use type hints** — All public methods should have type hints
4. **Document your plugin** — README.md with usage examples
5. **Test your plugin** — Use `tokenade plugin test`
6. **Version carefully** — Use semver, bump for breaking changes
7. **Don't store secrets** — Credentials come from CLI args, not hardcoded
8. **Respect the API** — Don't modify internal state directly

## Examples

See the official plugins at [mihir0209/tokenade-plugins](https://github.com/mihir0209/tokenade-plugins):

- `oauth2` — OAuth2 refresh (Google, GitHub, Microsoft)
- `google-handler` — Google site handler
- `github-handler` — GitHub site handler
- `discord-handler` — Discord site handler
- `session-health` — Session health validation
- `webhook-notify` — Webhook notifications
