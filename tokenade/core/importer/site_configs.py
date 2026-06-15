"""
Site Configurations - Pre-built configs for popular sites.

Each config includes:
- domains: Cookie domains to match
- critical_cookies: Cookies that must be present for session validity
- validate_url: URL to navigate to for validation
- login_indicator_css: CSS selector for logged-OUT indicator (presence = logged out)
- wait_seconds: Time to wait for page load during validation
"""

SITE_CONFIGS = {
    "github": {
        "name": "GitHub",
        "domains": [
            "github.com",
            ".github.com",
        ],
        "critical_cookies": [
            "user_session",
            "__Host-user_session_same_site",
            "__Host-device_id",
            "has_recent_activity",
            "logged_in",
            "_gh_sess",
        ],
        "validate_url": "https://github.com",
        "login_indicator_css": "a[href='/login']",
        "wait_seconds": 5,
    },
    "discord": {
        "name": "Discord",
        "domains": [
            "discord.com",
            "discordapp.com",
            ".discord.com",
        ],
        "critical_cookies": [
            "__dcfduid",
            "__sdcfduid",
            "authorization",
            "discord_session",
        ],
        "validate_url": "https://discord.com/channels/@me",
        "login_indicator_css": "a[href='/login']",
        "wait_seconds": 8,
    },
    "reddit": {
        "name": "Reddit",
        "domains": [
            "reddit.com",
            "www.reddit.com",
            ".reddit.com",
            "old.reddit.com",
        ],
        "critical_cookies": [
            "reddit_session",
            "token",
            "session",
            "_options",
            "recent_srs",
        ],
        "validate_url": "https://www.reddit.com/notifications",
        "login_indicator_css": "a[href='/login']",
        "wait_seconds": 5,
    },
    "google": {
        "name": "Google",
        "domains": [
            "google.com",
            "accounts.google.com",
            "mail.google.com",
            "labs.google.com",
            "myaccount.google.com",
            ".google.com",
        ],
        "critical_cookies": [
            "SID", "SSID", "APISID", "SAPISID", "HSID",
            "__Secure-1PSID", "__Secure-3PSID",
            "__Secure-1PAPISID", "__Secure-3PAPISID",
            "OSID", "__Secure-OSID",
            "__Host-GAPS", "COMPASS",
        ],
        "validate_url": "https://myaccount.google.com",
        "login_indicator_css": "a[href*='accounts.google.com/ServiceLogin']",
        "wait_seconds": 5,
    },
    "openai": {
        "name": "OpenAI",
        "domains": [
            "openai.com",
            ".openai.com",
            "chatgpt.com",
            ".chatgpt.com",
        ],
        "critical_cookies": [
            "__Secure-next-auth.session-token.0",
            "__Secure-next-auth.session-token.1",
            "__Secure-next-auth.session-token.2",
            "__Secure-oai-is",
            "oai-did",
            "oai-client-auth-info",
            "cf_clearance",
        ],
        "validate_url": "https://chatgpt.com",
        "login_indicator_css": "a[href='/auth/login']",
        "wait_seconds": 8,
    },
}


def get_site_config(site_name: str) -> dict:
    """Get config for a specific site."""
    return SITE_CONFIGS.get(site_name.lower(), {})


def list_sites() -> list:
    """List all available site configs."""
    return list(SITE_CONFIGS.keys())
