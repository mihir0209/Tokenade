"""
Example: Webhook Notification Plugin

This plugin sends webhook notifications when sessions are refreshed.
Useful for monitoring, alerting, and integration with Slack/Discord/etc.

To use this plugin:
1. Copy the my_webhook_notify/ directory to ~/.tokenade/plugins/
2. Run: tokenade plugin list
3. Set up your webhook URL in the plugin config

Plugin lifecycle:
1. Session refresh is triggered
2. This plugin's can_refresh() returns True for all sessions
3. refresh() sends a webhook notification, then passes through
"""

import json
import logging
import time
import urllib.request

from tokenade.plugin import SessionRefreshPlugin

logger = logging.getLogger(__name__)


class WebhookNotifyPlugin(SessionRefreshPlugin):
    """Send webhook notifications on session refresh events.

    This example shows:
    - How to create a pass-through plugin (refreshes + notifies)
    - How to send HTTP webhooks
    - How to handle plugin configuration
    """

    name = "my-webhook-notify"
    version = "1.0.0"
    description = "Example: Send webhook notifications on session refresh"
    author = "Tokenade Examples"

    # Default webhook URL (override via credentials)
    DEFAULT_WEBHOOK_URL = "https://hooks.example.com/tokenade"

    def can_refresh(self, session: dict) -> bool:
        """This plugin handles ALL sessions — it's a pass-through notifier."""
        return True

    def refresh(self, session, credentials):
        """Send webhook notification, then return session unchanged.

        This plugin doesn't actually refresh tokens — it just notifies.
        The actual refresh is done by another plugin (like oauth2).
        """
        webhook_url = credentials.get("webhook_url", self.DEFAULT_WEBHOOK_URL)
        site_name = session.get("site_name", "unknown")
        cookie_count = len(session.get("cookies", []))

        payload = {
            "event": "session_refresh",
            "site": site_name,
            "cookie_count": cookie_count,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "plugin": self.name,
        }

        try:
            self._send_webhook(webhook_url, payload)
            logger.info(f"Webhook sent for {site_name} refresh")
        except Exception as e:
            logger.warning(f"Webhook failed: {e}")

        # Return session unchanged (pass-through)
        return session

    def get_credentials_args(self):
        return [
            {
                "name": "--webhook-url",
                "help": "Webhook URL for notifications",
                "required": False,
                "type": str,
            },
        ]

    def _send_webhook(self, url: str, payload: dict):
        """Send a POST request to the webhook URL."""
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
