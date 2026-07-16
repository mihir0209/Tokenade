# Tokenade User Guide

Tokenade extracts, transfers, and injects browser sessions across machines and browsers.

## Installation

```bash
pip install tokenade
```

Or from source:

```bash
git clone https://github.com/mihir0209/tokenade
cd tokenade
pip install -e .
```

## Quick Start

### Export a session from Firefox

```bash
# Export Google session
tokenade export --browser-name firefox \
  --domains google.com,accounts.google.com \
  -o google.tokenade

# Export with plugin (recommended for hard sites)
tokenade export --browser-name firefox \
  --plugin discord-handler \
  -o discord.tokenade
```

### Transfer to another machine

```bash
# Copy the .tokenade file
scp google.tokenade user@newmachine:~/

# On new machine, load into browser
tokenade load --file google.tokenade
```

### Validate a session

```bash
# Validate all sessions in a directory
tokenade validate -d ~/sessions/

# Get recommendation for a URL
tokenade recommend --url https://github.com
```

## Core Commands

### Export

Export sessions from your browser:

```bash
# Basic export (cookies only)
tokenade export --browser-name firefox --domains example.com -o session.tokenade

# With localStorage (for hard sites)
tokenade export --browser-name firefox --plugin discord-handler -o discord.tokenade

# List available handlers
tokenade export --list-handlers

# List browser profiles
tokenade export --list-profiles
```

### Load / Inject

Load sessions into a browser:

```bash
# Load into CloakBrowser (default, headless)
tokenade load --file session.tokenade

# Show browser window
tokenade load --file session.tokenade --visible

# Load with validation
tokenade load --file session.tokenade --validate

# Load with specific stealth level
tokenade load --file session.tokenade --stealth-level maximum
```

### Plugin Management

Manage site handler plugins:

```bash
# List installed plugins
tokenade plugin list

# Install a plugin
tokenade plugin install discord-handler

# Test a plugin
tokenade plugin test discord-handler

# Search marketplace
tokenade plugin search telegram
```

### Session Validation

Validate session health:

```bash
# Validate all sessions
tokenade validate -d ~/sessions/

# Get session info
tokenade health session.tokenade

# Check expiry
tokenade session-expiry-alert session.tokenade
```

### Encryption

Encrypt sensitive sessions:

```bash
# Encrypt a session
tokenade encrypt session.tokenade --password "my-secret"

# Decrypt
tokenade decrypt session.tokenade.enc --password "my-secret"
```

### Session Sharing

Share sessions via encrypted URLs:

```bash
# Create share link
tokenade share session.tokenade

# Load from share link
tokenade load <share-url>
```

## Supported Sites

### Cookie-Simple Sites (via generic-handler)

- ChatGPT / OpenAI
- GitHub
- Google (basic export)
- Reddit

### Hard Sites (dedicated handlers)

- **Discord** (`discord-handler`): Uses localStorage token
- **Telegram** (`telegram-handler`): Uses localStorage auth keys

### OAuth Sites

- Google OAuth (`google-flow-handler`)
- Generic OAuth2 (`oauth-flow-handler`)

## Browser Automation

Tokenade defaults to CloakBrowser for automation:

```bash
# CloakBrowser (default, stealth) - headless
tokenade load --file session.tokenade

# CloakBrowser (visible window)
tokenade load --file session.tokenade --visible

# Launch CloakBrowser directly
tokenade launch --visible
```

## Plugin System

Plugins extend Tokenade's functionality:

### Plugin Types

- **handler**: Site-specific extraction/injection
- **session_refresh**: Token refresh logic
- **notification**: Expiry alerts, webhooks
- **proxy**: Proxy rotation, health checks
- **export_format**: Custom export formats

### Writing a Plugin

```python
from tokenade.plugin import SiteHandlerPlugin, PluginResult

class MySiteHandler(SiteHandlerPlugin):
    name = "my-site-handler"
    version = "1.0.0"
    
    def can_handle(self, url: str) -> bool:
        return "my-site.com" in url
    
    def validate(self, session: dict) -> PluginResult:
        # Validate session
        return PluginResult(success=True, data={"valid": True})
```

## Configuration

Configuration file: `~/.tokenade/config.yaml`

```yaml
automation_browser: cloak
default_browser: firefox
plugin_dir: ~/.tokenade/plugins
```

## Troubleshooting

### Browser is running

```bash
# Close browser before export
# Or use CDP mode
tokenade export --cdp-port 9222
```

### Plugin not found

```bash
# Install from marketplace
tokenade plugin install <plugin-name>

# Or copy to plugins directory
cp -r plugin/ ~/.tokenade/plugins/
```

### Session expired

```bash
# Refresh session
tokenade refresh session.tokenade

# Check expiry
tokenade health session.tokenade
```

## Advanced Usage

### Batch Operations

```bash
# Export multiple sites
tokenade batch-export --sites google,github,chatgpt

# Load multiple sessions
tokenade batch-load ~/sessions/
```

### Proxy Rotation

```bash
# Start proxy with rotation
tokenade proxy --port 8080 --rotate

# Use proxy during refresh
tokenade refresh session.tokenade --proxy http://proxy:8080
```

### CI/CD Integration

```bash
# Health report for CI
tokenade health-report -d ~/sessions/ --json

# Validate in CI pipeline
tokenade validate -d ~/sessions/ --fail-on-invalid
```

## API Usage

```python
from tokenade import PluginLoader, recommend

# Load a plugin
loader = PluginLoader()
plugin = loader.load_by_name("discord-handler")

# Get recommendation
rec = recommend(url="https://discord.com")
print(f"Use plugin: {rec.plugin}")
```

## License

MIT License
