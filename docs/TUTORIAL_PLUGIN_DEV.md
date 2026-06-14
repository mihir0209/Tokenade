# Building Plugins for Tokenade

## Plugin Architecture

Plugins are Python modules stored in `~/.tokenade/plugins/`. Each plugin has:
- `plugin.json` — Manifest with metadata
- Entry point Python file with the plugin class

## Plugin Types

### 1. Site Handler

Custom cookie extraction and auth detection for specific sites.

### 2. Export Format

Custom output formats for session export.

### 3. Validator

Custom health check rules for sessions.

## Creating a Site Handler Plugin

### Step 1: Create the directory

```bash
mkdir -p ~/.tokenade/plugins/my-site-handler
```

### Step 2: Create plugin.json

```json
{
  "name": "my-site-handler",
  "version": "1.0.0",
  "description": "Custom handler for my-site.com",
  "author": "Your Name",
  "type": "handler",
  "site_name": "my-site.com",
  "entry_point": "handler.py",
  "entry_class": "MySiteHandler"
}
```

### Step 3: Create handler.py

```python
class MySiteHandler:
    """Custom handler for my-site.com."""

    def check_auth(self, cookies: list) -> bool:
        """Check if user is authenticated."""
        cookie_names = {c["name"] for c in cookies}
        # Return True if auth cookies are present
        return "session_id" in cookie_names and "user_token" in cookie_names

    def extract_tokens(self, cookies: list) -> list:
        """Extract auth tokens from cookies."""
        auth_cookies = ["session_id", "user_token", "csrf_token"]
        return [c for c in cookies if c["name"] in auth_cookies]

    def get_auth_status(self, cookies: list) -> str:
        """Get authentication status."""
        if self.check_auth(cookies):
            return "logged_in"
        return "logged_out"

    def get_critical_cookies(self) -> list:
        """List cookies required for authentication."""
        return ["session_id", "user_token"]
```

### Step 4: Test the plugin

```bash
# List installed plugins
tokenade plugin list

# Get plugin info
tokenade plugin info my-site-handler
```

## Creating an Export Format Plugin

### Step 1: Create the directory

```bash
mkdir -p ~/.tokenade/plugins/my-exporter
```

### Step 2: Create plugin.json

```json
{
  "name": "my-exporter",
  "version": "1.0.0",
  "description": "Custom export format",
  "author": "Your Name",
  "type": "export_format",
  "format_name": "my-format",
  "entry_point": "exporter.py",
  "entry_class": "MyExporter"
}
```

### Step 3: Create exporter.py

```python
class MyExporter:
    """Custom export format."""

    def export(self, session: dict) -> str:
        """Export session to custom format."""
        cookies = session.get("cookies", [])
        # Your custom format logic here
        lines = []
        for cookie in cookies:
            lines.append(f"{cookie['name']}={cookie['value']}")
        return "\n".join(lines)

    def get_content_type(self) -> str:
        """Return MIME type for this format."""
        return "text/plain"

    def get_file_extension(self) -> str:
        """Return file extension for this format."""
        return ".txt"
```

## Creating a Validator Plugin

### Step 1: Create the directory

```bash
mkdir -p ~/.tokenade/plugins/my-validator
```

### Step 2: Create plugin.json

```json
{
  "name": "my-validator",
  "version": "1.0.0",
  "description": "Custom validation rules",
  "author": "Your Name",
  "type": "validator",
  "rule_name": "check-secure-cookies",
  "entry_point": "validator.py",
  "entry_class": "SecureCookieValidator"
}
```

### Step 3: Create validator.py

```python
class SecureCookieValidator:
    """Validate that all cookies have Secure flag."""

    def validate(self, session: dict) -> dict:
        """Validate session and return results."""
        cookies = session.get("cookies", [])
        issues = []
        recommendations = []

        for cookie in cookies:
            if not cookie.get("secure"):
                issues.append(f"Cookie '{cookie['name']}' missing Secure flag")
            if not cookie.get("httpOnly"):
                recommendations.append(f"Cookie '{cookie['name']}' could benefit from HttpOnly")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "recommendations": recommendations,
            "score": max(0, 100 - len(issues) * 10),
        }
```

## Plugin Management

```bash
# List installed plugins
tokenade plugin list

# List available plugins from registry
tokenade plugin list --available

# Install from registry
tokenade plugin install example-plugin

# Uninstall
tokenade plugin uninstall example-plugin

# Show details
tokenade plugin info my-site-handler
```

## Publishing Plugins

1. Create a GitHub repo with your plugin
2. Add a `plugin.json` manifest
3. Submit to the Tokenade plugin registry (PR to the plugins repo)
4. Users can then install with `tokenade plugin install your-plugin`

## Best Practices

- Keep plugins focused — one site or one format per plugin
- Handle missing cookies gracefully
- Add error handling for edge cases
- Write tests for your plugin
- Document your plugin's purpose and usage
