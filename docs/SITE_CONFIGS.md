# Site Configurations

Tokenade includes preset site configurations for popular websites. These configs define:

- **Domains** — Which cookie domains belong to the site
- **Critical Cookies** — Cookies that must be present for session validity
- **Validation URL** — URL to navigate to when validating the session
- **Login Indicator CSS** — CSS selector for the "Sign In" button (presence = logged out)
- **Wait Seconds** — How long to wait for page load during validation

## Built-in Configs

| Site | Domains | Critical Cookies | Validate URL |
|------|---------|-----------------|--------------|
| **GitHub** | `github.com`, `.github.com` | `user_session`, `_gh_sess`, `logged_in` | `https://github.com` |
| **Discord** | `discord.com`, `discordapp.com` | `authorization`, `discord_session` | `https://discord.com/channels/@me` |
| **Reddit** | `reddit.com`, `www.reddit.com` | `reddit_session`, `token` | `https://www.reddit.com/notifications` |
| **Google** | `google.com`, `accounts.google.com` | `SID`, `SSID`, `SAPISID`, `HSID` + 8 more | `https://myaccount.google.com` |
| **OpenAI** | `openai.com`, `chatgpt.com` | `session-token`, `oai-did` | `https://chatgpt.com` |

## Using Site Configs

Site configs are automatically applied when exporting or loading sessions:

```bash
# Export — auto-detects site from cookies
tokenade export --browser-name brave -o session.tokenade

# Load — uses preset config for validation
tokenade load -s session.tokenade
```

## Creating Custom Site Configs

Create a JSON file with the following structure:

```json
{
  "name": "My Site",
  "domains": ["mysite.com", ".mysite.com"],
  "critical_cookies": ["session_id", "auth_token"],
  "validate_url": "https://mysite.com/dashboard",
  "login_indicator_css": "a[href='/login']",
  "wait_seconds": 5
}
```

### Using Custom Configs

```bash
# Export with custom site config
tokenade export --browser-name chrome --site-config mysite.json

# Or pass it to the packager in Python
from tokenade.core.importer.session_packager import SessionPackager
packager = SessionPackager()
```

## Config Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Display name for the site |
| `domains` | list | Yes | Cookie domains to match |
| `critical_cookies` | list | Yes | Cookies required for valid session |
| `validate_url` | string | No | URL to navigate to for validation |
| `login_indicator_css` | string | No | CSS selector for logged-out indicator |
| `wait_seconds` | int | No | Page load wait time (default: 10) |

## Login Indicator CSS

The `login_indicator_css` field should select an element that is **only visible when logged OUT**. When the validator finds this element, it marks the session as invalid.

Examples:
- GitHub: `a[href='/login']` — the Sign In link
- Google: `a[href*='accounts.google.com/ServiceLogin']` — the Sign In link
- Discord: `a[href='/login']` — the Login button
- Reddit: `a[href='/login']` — the Log In link

## Python API

```python
from tokenade.core.importer.site_configs import get_site_config, list_sites

# List available sites
print(list_sites())  # ['github', 'discord', 'reddit', 'google', 'openai']

# Get a specific config
config = get_site_config("github")
print(config["domains"])  # ['github.com', '.github.com']
```
