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
    "twitter": {
        "name": "Twitter/X",
        "domains": [
            "x.com",
            "twitter.com",
            ".x.com",
            ".twitter.com",
            "api.x.com",
            "api.twitter.com",
        ],
        "critical_cookies": [
            "auth_token",
            "ct0",
            "twid",
            "__cf_bm",
        ],
        "validate_url": "https://x.com/home",
        "login_indicator_css": "a[href='/login']",
        "wait_seconds": 5,
    },
    "linkedin": {
        "name": "LinkedIn",
        "domains": [
            "linkedin.com",
            "www.linkedin.com",
            ".linkedin.com",
            "linkedin.com",
            "edge.linkedin.com",
        ],
        "critical_cookies": [
            "li_at",
            "JSESSIONID",
            "UserMatchHistory",
            "AnalyticsSyncHistory",
            "li_srsr",
            "li_fat_id",
        ],
        "validate_url": "https://www.linkedin.com/feed/",
        "login_indicator_css": "a[href*='linkedin.com/login']",
        "wait_seconds": 5,
    },
    "netflix": {
        "name": "Netflix",
        "domains": [
            "netflix.com",
            ".netflix.com",
            "www.netflix.com",
            ".netflix.com",
        ],
        "critical_cookies": [
            "SecureNetflixId",
            "NetflixId",
            "netflix-session",
            "nflxSession",
        ],
        "validate_url": "https://www.netflix.com/browse",
        "login_indicator_css": "a[href*='/Login']",
        "wait_seconds": 8,
    },
    "youtube": {
        "name": "YouTube",
        "domains": [
            "youtube.com",
            ".youtube.com",
            "www.youtube.com",
            "accounts.google.com",
        ],
        "critical_cookies": [
            "SID", "SSID", "HSID",
            "__Secure-1PSID", "__Secure-3PSID",
            "LOGIN_INFO",
            "VISITOR_INFO1_LIVE",
            "YSC",
            "PREF",
        ],
        "validate_url": "https://www.youtube.com",
        "login_indicator_css": "a[href*='accounts.google.com/ServiceLogin']",
        "wait_seconds": 5,
    },
    "amazon": {
        "name": "Amazon",
        "domains": [
            "amazon.com",
            ".amazon.com",
            "www.amazon.com",
            "smile.amazon.com",
        ],
        "critical_cookies": [
            "session-id",
            "session-id-time",
            "i18n-prefs",
            "lc-main",
            "x-main",
            "at-main",
            "ubid-main",
            "sess-at-main",
        ],
        "validate_url": "https://www.amazon.com/gp/your-account/order-history",
        "login_indicator_css": "a[href*='signin']",
        "wait_seconds": 5,
    },
    "spotify": {
        "name": "Spotify",
        "domains": [
            "spotify.com",
            ".spotify.com",
            "open.spotify.com",
            "accounts.spotify.com",
        ],
        "critical_cookies": [
            "sp_dc",
            "sp_key",
            "sp_t",
            "sp_landing",
            "__Secure-3P3PSID",
        ],
        "validate_url": "https://open.spotify.com",
        "login_indicator_css": "a[href*='accounts.spotify.com/login']",
        "wait_seconds": 5,
    },
    "microsoft": {
        "name": "Microsoft",
        "domains": [
            "microsoft.com",
            ".microsoft.com",
            "login.microsoftonline.com",
            "outlook.live.com",
            "onedrive.live.com",
        ],
        "critical_cookies": [
            "ESTSAUTH",
            "ESTSAUTHPERSISTENT",
            "SignIn5Info",
            "ai_session",
            "ANON",
            "MUID",
        ],
        "validate_url": "https://outlook.live.com/mail/",
        "login_indicator_css": "a[href*='login.microsoftonline.com']",
        "wait_seconds": 5,
    },
    "generic_oauth2": {
        "name": "Generic OAuth2",
        "domains": [],  # User must specify via --domains
        "critical_cookies": [
            "session",
            "session_id",
            "access_token",
            "refresh_token",
            "token",
            "auth",
            "jwt",
        ],
        "validate_url": "",
        "login_indicator_css": "a[href*='login'], a[href*='signin'], button[data-action='login']",
        "wait_seconds": 5,
    },
}


def get_site_config(site_name: str) -> dict:
    """Get config for a specific site."""
    return SITE_CONFIGS.get(site_name.lower(), {})


def list_sites() -> list:
    """List all available site configs."""
    return list(SITE_CONFIGS.keys())
