# Tokenade Plugin System — Examples

This directory contains examples showing how to create and use Tokenade plugins.

## Directory Structure

```
examples/plugins/
├── README.md                    # This file
├── my_custom_refresh/           # Example 1: Custom session refresh plugin
│   ├── plugin.json              # Plugin manifest
│   └── plugin.py                # Plugin implementation
├── my_site_handler/             # Example 2: Custom site handler plugin
│   ├── plugin.json
│   └── plugin.py
├── my_export_format/            # Example 3: Custom export format plugin
│   ├── plugin.json
│   └── plugin.py
└── using_plugins.py             # Example 4: Programmatic plugin usage
```

## Quick Start

### 1. Install a plugin from the registry
```bash
tokenade plugin install oauth2
```

### 2. List installed plugins
```bash
tokenade plugin list
```

### 3. Use a plugin with a command
```bash
tokenade refresh-browser -s google.tokenade --plugin oauth2 \
    --client-id YOUR_ID --client-secret YOUR_SECRET --refresh-token YOUR_TOKEN
```

## Writing Your Own Plugin

See `my_custom_refresh/plugin.py` for a complete example.

### Plugin Types

| Type | Base Class | Purpose |
|------|-----------|---------|
| `session_refresh` | `SessionRefreshPlugin` | Refresh expired sessions |
| `handler` | `SiteHandlerPlugin` | Handle specific websites |
| `export_format` | `ExportFormatPlugin` | Custom export formats |
| `validator` | `SessionValidatorPlugin` | Custom validation rules |

### Minimal Plugin Structure

```
my-plugin/
├── plugin.json    # Required: metadata manifest
└── plugin.py      # Required: plugin code
```

### plugin.json

```json
{
    "name": "my-plugin",
    "version": "1.0.0",
    "description": "What my plugin does",
    "author": "Your Name",
    "type": "session_refresh",
    "entry_point": "plugin.py",
    "entry_class": "MyPlugin",
    "dependencies": []
}
```

### plugin.py

```python
from tokenade.plugin import SessionRefreshPlugin

class MyPlugin(SessionRefreshPlugin):
    name = "my-plugin"
    version = "1.0.0"
    description = "My custom refresh plugin"

    def can_refresh(self, session):
        return "example.com" in str(session.get("cookies", []))

    def refresh(self, session, credentials):
        # Your refresh logic here
        return session
```

## Programmatic Usage

```python
from tokenade.core.integration.plugin_loader import PluginLoader

loader = PluginLoader()
loader.load_all()

# Find a refresher for a session
refresher = loader.get_refresher_for_session(session)
if refresher:
    new_session = refresher.refresh(session, credentials)
```

## Built-in Plugins

### OAuth2 Plugin (`oauth2`)

Refreshes OAuth2 sessions using refresh tokens.

```bash
tokenade plugin install oauth2
tokenade refresh-browser -s google.tokenade --plugin oauth2 \
    --client-id ID --client-secret SECRET --refresh-token TOKEN
```

Supports: Google, GitHub, custom providers.
