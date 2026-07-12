# Plugin User Guide

This guide covers installing, managing, and using plugins in Tokenade.

## Installing Plugins

### From the registry (TUI)

```bash
tokenade tui
```

Navigate to the **Marketplace** tab, find a plugin, and click **Install**.

### From the CLI

```bash
# List available plugins from the registry
tokenade plugin list --available

# Install a specific plugin
tokenade plugin install google-handler

# Verify installation
tokenade plugin list
```

### Manual installation

```bash
# Copy plugin directory to the plugins folder
cp -r my-plugin ~/.tokenade/plugins/my-plugin

# List to verify
tokenade plugin list
```

## Managing Plugins

### List installed plugins

```bash
# List with lifecycle state and health
tokenade plugin list

# Show detailed info for a plugin
tokenade plugin info google-handler

# Show available plugins from the registry
tokenade plugin list --available
```

### Enable / Disable plugins

```bash
# Disable a plugin (keeps it installed but inactive)
tokenade plugin disable google-handler

# Re-enable
tokenade plugin enable google-handler
```

### Update plugins

```bash
# Update all plugins
tokenade plugin update

# Update a specific plugin
tokenade plugin update google-handler

# Check for outdated plugins
tokenade plugin outdated
```

### Uninstall plugins

```bash
tokenade plugin uninstall google-handler
```

### Reload a plugin

```bash
# Reload without losing configuration
tokenade plugin reload google-handler
```

## Configuring Plugins

```bash
# Show current config
tokenade plugin configure google-handler --show

# Set config values
tokenade plugin configure google-handler --set timeout=60 retries=3

# Validate config against schema
tokenade plugin configure google-handler --validate

# Reset to defaults
tokenade plugin configure google-handler --reset
```

### Config precedence

1. Schema defaults (lowest)
2. Global config (`~/.tokenade/config.json`)
3. Plugin-specific user config (`~/.tokenade/plugins/<name>/config.json`) (highest)

## Using Plugins with CLI

### Auto-discovery (default)

By default, plugins run automatically when available:

```bash
# Auto-discovers google-handler for google.com cookies
tokenade export --browser-name firefox --domains "google.com" -o gmail.tokenade

# Auto-discovers oauth2 refresher for refresh
tokenade refresh-browser -s gmail.tokenade
```

### Force a specific plugin

```bash
# Force a specific handler
tokenade export --browser-name firefox --plugin google-handler -o gmail.tokenade

# Force a specific refresher
tokenade refresh-browser -s gmail.tokenade --plugin oauth2
```

### Exclude plugins

```bash
# Skip all plugins, use default behavior
tokenade launch --no-plugin
tokenade refresh-browser -s gmail.tokenade --no-plugin
tokenade accounts refresh --no-plugin
```

### Plugin arguments

```bash
# Pass credentials to a plugin
tokenade refresh-browser -s gmail.tokenade --plugin oauth2 \
    --plugin-arg client_id XXX \
    --plugin-arg client_secret YYY
```

## Using Plugins with TUI

Launch the interactive TUI:

```bash
tokenade tui
```

Tabs:
- **Marketplace** — Browse and install plugins from the registry
- **Installed** — Manage installed plugins (enable/disable/reload/configure)
- **Registries** — Add/remove/enable/disable plugin registries
- **Sessions** — Manage sessions
- **Settings** — Global configuration

## Registry Management

### Add a custom registry

```bash
# Via TUI: Settings tab → Add Custom Registry
# Via CLI:
tokenade config set registry-url https://github.com/myorg/plugins
```

### Multiple registries

Tokenade supports multiple registries with priority ordering. When the same
plugin exists in multiple registries, the highest-priority registry wins.

```bash
# List configured registries (TUI → Registries tab)
# Set priority via TUI (Up/Down buttons)
```

## Troubleshooting

### Plugin not found

```bash
# Verify installation
tokenade plugin list

# Check plugin directory
ls ~/.tokenade/plugins/

# Verify manifest
cat ~/.tokenade/plugins/<name>/plugin.json
```

### Plugin failed to load

```bash
# Check detailed error
tokenade plugin info <name>

# Check logs
tokenade logs --search "<name>"

# Test plugin integrity
tokenade plugin test <name>
```

### Plugin health shows unhealthy

```bash
# Check shared context health
tokenade health -s ~/.tokenade/sessions/*.tokenade

# Check plugin-specific health via TUI (Installed tab)
```

### Config not applied

```bash
# Verify config was saved
tokenade plugin configure <name> --show

# Check config file
cat ~/.tokenade/plugins/<name>/config.json

# Validate against schema
tokenade plugin configure <name> --validate
```

### Dependency missing

```bash
# Check dependencies
tokenade plugin deps <name>

# Check all dependencies
tokenade plugin check-deps

# Install missing dependencies
tokenade plugin install <missing-dep>
```

### Roll back a plugin

```bash
# Reload the previous version (if available)
tokenade plugin update <name>

# Or manually restore from backup
cp ~/.tokenade/plugins/<name>.bak ~/.tokenade/plugins/<name>
tokenade plugin reload <name>
```
