# Site Configurations (plugin-owned)

**Sprint 0:** Site configs are **not** a directory in the Tokenade core repo.
They live **inside each site-handler plugin** as `site_config.json`.

## Layout

```
~/.tokenade/plugins/google-handler/
├── plugin.json
├── plugin.py
└── site_config.json    ← domains, critical cookies, URLs
```

The `SiteHandlerPlugin` base class loads `site_config.json` when the plugin
directory is bound (via `PluginLoader`). Core APIs resolve sites through plugins:

```python
from tokenade.core.importer.site_configs import get_site_config, list_sites

list_sites()                 # e.g. ['chatgpt', 'github', 'google', ...]
get_site_config("google")    # dict from google-handler/site_config.json
```

## site_config.json schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Site key (e.g. `google`, `github`) |
| `domains` | string[] | Yes | Cookie domains to export / match |
| `critical_cookies` | string[] | Yes | Names used for health / validation |
| `login_url` | string | No | Sign-in URL |
| `dashboard_url` | string | No | Logged-in landing URL |
| `validate_url` | string | No | Defaults to `dashboard_url` |
| `session_check_url` | string | No | Fast API session probe |
| `logged_in_selectors` | string[] | No | CSS: logged-in UI |
| `logged_out_selectors` | string[] | No | CSS: logged-out UI |
| `login_indicator_css` | string | No | Legacy single selector (maps to logged_out) |
| `wait_seconds` | int | No | Validation wait (default 5) |
| `critical_storage` | object | No | `{ "local": { origin: [keys] }, "session": {} }` |
| `preferred_plugin` | string | No | Plugin name (default: owning plugin) |

### Example

```json
{
  "name": "example-site",
  "domains": ["example.com", "www.example.com"],
  "critical_cookies": ["session_id", "auth_token"],
  "login_url": "https://example.com/login",
  "dashboard_url": "https://example.com/dashboard",
  "wait_seconds": 5,
  "preferred_plugin": "my-site-handler"
}
```

## Using with the CLI

```bash
# Domain list comes from the plugin's site_config.json
tokenade export --browser-name firefox --plugin google-handler -o gmail.tokenade

tokenade launch -s gmail.tokenade --plugin google-handler --browser brave \
  --profile-dir /tmp/tokenade-brave-clean --visible
```

Optional **ad-hoc** filter file (batch / one-off) still exists as CLI
`--site-config path/to.json` for multi-site batch export. That is a **file path
argument**, not a growing catalog in the core repository.

## Authoring a new site

1. Create a handler plugin under `~/.tokenade/plugins/<name>-handler/`.
2. Add `plugin.json` + `plugin.py` (subclass `SiteHandlerPlugin`).
3. Add **`site_config.json`** with domains and critical cookies.
4. Implement `extract_session` / `inject_session`; getters default from JSON.

See [PLUGIN_DEVELOPMENT.md](PLUGIN_DEVELOPMENT.md) and
`examples/plugins/my_site_handler/`.

## What was removed

| Removed | Replacement |
|---------|-------------|
| Repo-root `site_configs/*.json` | Per-plugin `site_config.json` |
| Built-in Python `SITE_CONFIGS` table | Plugin discovery |
| `~/.tokenade/site_configs/` catalog | Handlers only |

Do **not** add site JSON dumps back into the Tokenade monorepo.
