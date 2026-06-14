# Tokenade API Reference

## Python SDK

### TokenadeClient

```python
from tokenade.sdk import TokenadeClient

client = TokenadeClient()
```

#### Methods

##### `extract(browser, domains=None, output=None) -> ExtractionResult`

Extract cookies from a browser.

```python
result = client.extract(
    browser="firefox",
    domains=["github.com"],
    output="github.tokenade"
)
print(result.success)  # True
print(result.session_path)  # "github.tokenade"
```

##### `load(session_path) -> dict`

Load a session file.

```python
session = client.load("github.tokenade")
print(session["site_name"])  # "github"
print(len(session["cookies"]))  # 42
```

##### `health_check(session_path) -> dict`

Check session health score.

```python
health = client.health_check("github.tokenade")
print(health["score"])  # 85.0
print(health["issues"])  # ["Cookie 'sid' missing Secure flag"]
```

##### `share(session_path, password=None, expiry_hours=24) -> str`

Create a shareable link.

```python
link = client.share("github.tokenade", password="secret", expiry_hours=48)
print(link)  # "https://..."
```

##### `export_playwright(session_path) -> str`

Export as Playwright storageState.

```python
state_json = client.export_playwright("github.tokenade")
# Use with Playwright:
# context = browser.new_context(storage_state=state_json)
```

---

## REST API

Start the API server:

```bash
tokenade serve --port 9224
```

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/sessions` | List all sessions |
| GET | `/api/sessions/{id}` | Get session details |
| DELETE | `/api/sessions/{id}` | Delete session |
| GET | `/api/proxy/status` | Proxy status |
| POST | `/api/export` | Export session |
| POST | `/api/share` | Create share link |
| GET | `/api/monitor/status` | Monitoring status |
| GET | `/api/monitor/sessions/{id}` | Session monitoring details |
| GET | `/api/monitor/sessions/{id}/cookies` | Cookie expiry timeline |

### Authentication

All endpoints require either:
- `Authorization: Bearer <api_key>` header
- `X-API-Key: <api_key>` header

### Examples

```bash
# List sessions
curl -H "X-API-Key: my-key" http://localhost:9224/api/sessions

# Check session health
curl -H "X-API-Key: my-key" http://localhost:9224/api/monitor/status

# Export session
curl -X POST -H "Content-Type: application/json" -H "X-API-Key: my-key" \
  -d '{"browser": "chrome", "domains": ["github.com"]}' \
  http://localhost:9224/api/export
```

---

## CLI Reference

### Export

```bash
tokenade export --browser-name firefox --domains "github.com" -o github.tokenade
```

### Proxy

```bash
tokenade proxy -s github.tokenade --port 9222
```

### Health

```bash
tokenade health -s github.tokenade
```

### Plugin Management

```bash
tokenade plugin list                    # List installed plugins
tokenade plugin list --available        # Show registry plugins
tokenade plugin install <name>          # Install from registry
tokenade plugin uninstall <name>        # Remove plugin
tokenade plugin info <name>             # Show plugin details
```

### Sessions

```bash
tokenade sessions list -d ./sessions    # List sessions
tokenade sessions merge s1.tokenade s2.tokenade -o merged.tokenade
tokenade sessions rotate s1.tokenade s2.tokenade
tokenade sessions stats *.tokenade
```

### Security

```bash
tokenade encrypt -s session.tokenade -o encrypted.tokenade
tokenade decrypt -s encrypted.tokenade -o session.tokenade
tokenade rekey -s encrypted.tokenade
```

### Sharing

```bash
tokenade share -s session.tokenade --password x --expiry 48
tokenade unshare --list
```
