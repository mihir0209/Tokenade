# Plugin API Reference

This document describes the Tokenade plugin API (v1.1.0). All plugins must
inherit from one of the base classes listed below and implement the required
methods.

## API Version

Current API version: **1.1.0**

Plugins declare their target API version in `plugin.json`:

```json
{
    "api_version": "1.1.0"
}
```

The plugin loader accepts API versions 1.0.0–1.1.0 with a warning for mismatches.

## Base Classes

All base classes are importable from `tokenade.plugin`:

```python
from tokenade.plugin import (
    SiteHandlerPlugin,
    SessionRefreshPlugin,
    ProxyProviderPlugin,
    CaptchaPlugin,
    NotificationPlugin,
    PluginResult,
    PluginMetadata,
)
```

### SiteHandlerPlugin

Overrides site-specific cookie extraction/injection behavior.

```python
from tokenade.plugin import SiteHandlerPlugin, PluginResult

class MyHandler(SiteHandlerPlugin):
    name = "my-handler"
    version = "1.0.0"
    description = "My custom site handler"

    def can_handle(self, url: str) -> bool:
        """Return True if this handler should process the URL."""
        return "example.com" in url

    def extract_session(self, page) -> PluginResult:
        """Extract session data from a Playwright page.

        Returns PluginResult with cookies, local_storage, session_storage.
        """
        cookies = page.context.cookies()
        return PluginResult(cookies=cookies)

    def inject_session(self, page, session: dict) -> None:
        """Inject session data into a Playwright page."""
        for cookie in session.get("cookies", []):
            page.context.add_cookies([cookie])
```

**Required methods:** `can_handle`, `extract_session`, `inject_session`

**Optional methods:** `get_dashboard_url`, `get_critical_cookies`,
`get_site_config`, `on_load`, `on_unload`, `on_configure`

### SessionRefreshPlugin

Refreshes expired sessions using OAuth tokens or browser-based refresh.

```python
from tokenade.plugin import SessionRefreshPlugin

class MyRefresher(SessionRefreshPlugin):
    name = "my-refresh"
    version = "1.0.0"
    description = "My session refresher"

    def can_refresh(self, session: dict) -> bool:
        """Return True if this plugin can refresh the session."""
        return bool(session.get("refresh_token"))

    def refresh(self, session: dict, credentials: dict | None = None) -> dict:
        """Refresh and return the updated session."""
        # Use refresh token to get new access token
        session["refreshed_by"] = self.name
        return session

    def get_credentials_args(self) -> list:
        """Return list of required credential arguments."""
        return [
            {"name": "--client-id", "required": True},
            {"name": "--client-secret", "required": True},
        ]
```

**Required methods:** `can_refresh`, `refresh`

**Optional methods:** `get_credentials_args`, `on_load`, `on_unload`,
`on_configure`

### ProxyProviderPlugin

Provides proxy servers for session operations.

```python
from tokenade.plugin import ProxyProviderPlugin

class MyProxy(ProxyProviderPlugin):
    name = "my-proxy"
    version = "1.0.0"
    description = "My proxy provider"

    def get_proxy(self, session_id: str) -> dict | None:
        """Return proxy configuration for a session."""
        return {
            "server_url": "socks5://user:pass@host:port",
            "sticky": True,
            "session_id": session_id,
        }

    def release_proxy(self, session_id: str) -> None:
        """Release a sticky proxy allocation."""
        pass
```

**Required methods:** `get_proxy`

**Optional methods:** `release_proxy`, `on_load`, `on_unload`, `on_configure`

### CaptchaPlugin

Solves CAPTCHAs during session operations.

```python
from tokenade.plugin import CaptchaPlugin

class MySolver(CaptchaPlugin):
    name = "my-solver"
    version = "1.0.0"
    description = "My CAPTCHA solver"

    def solve_image_captcha(self, image_data: bytes) -> str:
        """Solve an image CAPTCHA. Return the solution text."""
        return "SOLVED"

    def solve_recaptcha(self, site_key: str, page_url: str) -> str:
        """Solve reCAPTCHA. Return the token."""
        return "TOKEN"

    def solve_hcaptcha(self, site_key: str, page_url: str) -> str:
        """Solve hCaptcha. Return the token."""
        return "TOKEN"
```

**Required methods:** `solve_image_captcha`, `solve_recaptcha`, `solve_hcaptcha`

**Optional methods:** `on_load`, `on_unload`, `on_configure`

### NotificationPlugin

Sends notifications for plugin/session events.

```python
from tokenade.plugin import NotificationPlugin

class MyNotifier(NotificationPlugin):
    name = "my-notifier"
    version = "1.0.0"
    description = "My notification plugin"

    def notify_session_expired(self, session_id: str, session_name: str) -> None:
        """Called when a session expires."""
        self._send_webhook({"event": "expired", "session": session_name})

    def notify_plugin_failed(self, plugin_name: str, error: str) -> None:
        """Called when a plugin fails."""
        self._send_webhook({"event": "failed", "plugin": plugin_name})

    def notify_refresh_complete(self, session_id: str, cookies_added: int) -> None:
        """Called after a successful refresh."""
        self._send_webhook({"event": "refresh", "cookies": cookies_added})
```

**Required methods:** `notify_session_expired`, `notify_plugin_failed`,
`notify_refresh_complete`

**Optional methods:** `on_load`, `on_unload`, `on_configure`

## Plugin Metadata Types

### PluginResult

```python
@dataclass
class PluginResult:
    """Result of a plugin operation."""
    success: bool = True
    cookies: List[dict] = field(default_factory=list)
    local_storage: Dict[str, str] = field(default_factory=dict)
    session_storage: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### PluginMetadata

```python
@dataclass
class PluginMetadata:
    """Plugin metadata from plugin.json."""
    name: str
    version: str
    api_version: str
    description: str
    author: str
    plugin_type: str
    entry_point: str
    entry_class: str
    dependencies: List[str] = field(default_factory=list)
    site_name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
```

## Event Bus API

Plugins can emit and listen to events:

```python
from tokenade.core.events.bus import EventBus
from tokenade.core.events.types import EventType

bus = EventBus()

# Emit an event
bus.emit(EventType.PLUGIN_LOADED, data={"plugin": "my-plugin"}, source="my-plugin")

# Listen to events
def on_plugin_loaded(data, source):
    print(f"Plugin {data['plugin']} loaded from {source}")

bus.on(EventType.PLUGIN_LOADED, on_plugin_loaded)
```

### EventType values

- `PLUGIN_LOADED` — Plugin loaded successfully
- `PLUGIN_UNLOADED` — Plugin unloaded
- `PLUGIN_CONFIGURED` — Plugin configuration changed
- `PLUGIN_FAILED` — Plugin failed to load
- `SESSION_REFRESHED` — Session refreshed
- `SESSION_EXPIRED` — Session expired
- `PROXY_ASSIGNED` — Proxy assigned to session
- `CAPTCHA_SOLVED` — CAPTCHA solved

## Shared Context API

Plugins access shared state via `SharedContext`:

```python
from tokenade.core.context import SharedContext

ctx = SharedContext()

# Sessions namespace
ctx.sessions.set("session-1", {"cookies": [...]})
session = ctx.sessions.get("session-1")

# Plugins namespace
ctx.plugins.set_health("my-plugin", True)
healthy = ctx.plugins.get_health("my-plugin")

# Config namespace
ctx.config.set_registry_url("https://registry.example.com")
url = ctx.config.get_registry_url()

# Runtime namespace
ctx.runtime.set_active_proxy("session-1", "socks5://...")
proxy = ctx.runtime.get_active_proxy("session-1")

# Tasks namespace
ctx.tasks.start("my-task", plugin="my-plugin")
ctx.tasks.complete("my-task")
```

## Error Handling

Plugin errors are caught and logged by the loader. Plugins should:

1. **Never raise unhandled exceptions** — catch and log internally
2. **Return gracefully degraded results** — empty dict/list on failure
3. **Use the event bus for cross-cutting concerns** — don't call other plugins directly

```python
class MyPlugin(SiteHandlerPlugin):
    def extract_session(self, page):
        try:
            cookies = page.context.cookies()
            return PluginResult(cookies=cookies)
        except Exception as e:
            logger.error(f"Cookie extraction failed: {e}")
            return PluginResult(success=False, error=str(e))
```

## Testing Plugins

Use `tokenade plugin test <name>` to run contract tests:

1. Manifest exists and is valid JSON
2. Manifest has required fields (name, version, type, entry_point, entry_class)
3. Entry point file exists
4. Entry class is importable
5. Plugin is instantiable
6. Plugin has required metadata (name, version, description)
7. Plugin has required methods for its type
8. Plugin type matches manifest declaration

```bash
# Test a single plugin
tokenade plugin test my-handler

# Test all plugins
tokenade plugin test

# Verbose output
tokenade plugin test --verbose
```

## Publishing Plugins

1. Create a git repository with your plugin code
2. Add a `plugin.json` manifest at the root
3. Test with `tokenade plugin test`
4. Submit to the registry via GitHub PR or `tokenade plugin submit`
