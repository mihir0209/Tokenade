"""Example: Notification Plugin

Sends webhooks/emails when sessions expire or plugins fail.

Install:
    cp -r my-notifier ~/.tokenade/plugins/my-notifier
    tokenade plugin configure my-notifier --set webhook_url=https://hooks.example.com/x
"""

from tokenade.plugin.base import NotificationPlugin


class MyNotificationPlugin(NotificationPlugin):
    """Example notification plugin — sends webhooks on events."""

    name = "my-notifier"
    version = "1.0.0"
    description = "Example notification plugin"

    def notify_session_expired(self, session_id: str, session_name: str) -> None:
        """Called when a session has expired."""
        payload = {
            "event": "session_expired",
            "session_id": session_id,
            "session_name": session_name,
        }
        self._send_webhook(payload)

    def notify_plugin_failed(self, plugin_name: str, error: str) -> None:
        """Called when a plugin has failed."""
        payload = {
            "event": "plugin_failed",
            "plugin": plugin_name,
            "error": error,
        }
        self._send_webhook(payload)

    def notify_refresh_complete(self, session_id: str, cookies_added: int) -> None:
        """Called after a successful refresh."""
        payload = {
            "event": "refresh_complete",
            "session_id": session_id,
            "cookies_added": cookies_added,
        }
        self._send_webhook(payload)

    def _send_webhook(self, payload: dict) -> None:
        """Send a webhook notification (best-effort, no exceptions)."""
        try:
            import requests
            url = self.config.get("webhook_url", "")
            if url:
                requests.post(url, json=payload, timeout=5)
        except Exception:
            pass
