"""
Enhanced webhook integrations.

Supports Slack, Discord, Microsoft Teams, Telegram, and custom webhooks.
"""
import json
import logging
import hashlib
import hmac
from typing import Dict, Optional, Any, List
from dataclasses import dataclass
from urllib.request import Request, urlopen
from urllib.error import URLError
import ssl

logger = logging.getLogger(__name__)


@dataclass
class WebhookConfig:
    """Webhook configuration."""
    url: str
    type: str = "custom"
    secret: Optional[str] = None
    channel: Optional[str] = None
    bot_token: Optional[str] = None


class WebhookIntegration:
    """Send notifications to various platforms."""
    
    def __init__(self, config: WebhookConfig):
        self.config = config
    
    def send_session_event(self, event_type: str, session_data: Dict) -> bool:
        """Send a session event notification.
        
        Args:
            event_type: 'export', 'share', 'refresh', 'expired'
            session_data: Session metadata
            
        Returns:
            Success boolean
        """
        payload = self._build_payload(event_type, session_data)
        
        if self.config.type == "slack":
            formatted = self._format_slack(payload)
            return self._http_post(self.config.url, formatted)
        elif self.config.type == "discord":
            formatted = self._format_discord(payload)
            return self._http_post(self.config.url, formatted)
        elif self.config.type == "teams":
            formatted = self._format_teams(payload)
            return self._http_post(self.config.url, formatted)
        elif self.config.type == "telegram":
            return self._send_telegram(payload)
        else:
            return self._http_post(self.config.url, payload)
    
    def _build_payload(self, event_type: str, session_data: Dict) -> Dict:
        """Build notification payload."""
        site = session_data.get("site_name", "unknown")
        cookies = session_data.get("cookie_count", 0)
        
        messages = {
            "export": f"Session exported for {site} ({cookies} cookies)",
            "share": f"Session shared for {site}",
            "refresh": f"Session refreshed for {site}",
            "expired": f"Session expired for {site}",
        }
        
        return {
            "event_type": event_type,
            "message": messages.get(event_type, f"Session event: {event_type}"),
            "site_name": site,
            "cookie_count": cookies,
            "timestamp": session_data.get("created_at", ""),
        }
    
    def _format_slack(self, payload: Dict) -> Dict:
        """Format payload for Slack incoming webhook."""
        return {
            "text": payload["message"],
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{payload['event_type'].title()}*\n{payload['message']}"
                    }
                }
            ]
        }
    
    def _format_discord(self, payload: Dict) -> Dict:
        """Format payload for Discord webhook."""
        return {
            "embeds": [
                {
                    "title": f"Tokenade: {payload['event_type'].title()}",
                    "description": payload["message"],
                    "color": 0x00ff00 if payload["event_type"] != "expired" else 0xff0000,
                    "fields": [
                        {"name": "Site", "value": payload["site_name"], "inline": True},
                        {"name": "Cookies", "value": str(payload["cookie_count"]), "inline": True},
                    ]
                }
            ]
        }
    
    def _format_teams(self, payload: Dict) -> Dict:
        """Format payload for Microsoft Teams webhook."""
        return {
            "@type": "MessageCard",
            "themeColor": "00FF00" if payload["event_type"] != "expired" else "FF0000",
            "title": f"Tokenade: {payload['event_type'].title()}",
            "text": payload["message"],
            "sections": [
                {
                    "facts": [
                        {"name": "Site", "value": payload["site_name"]},
                        {"name": "Cookies", "value": str(payload["cookie_count"])},
                    ]
                }
            ]
        }
    
    def _send_telegram(self, payload: Dict) -> bool:
        """Send to Telegram via Bot API."""
        if not self.config.bot_token:
            logger.error("Telegram bot token required")
            return False
        
        text = f"*Tokenade: {payload['event_type'].title()}*\n{payload['message']}\nSite: {payload['site_name']}"
        
        url = f"https://api.telegram.org/bot{self.config.bot_token}/sendMessage"
        telegram_payload = {
            "chat_id": self.config.channel,
            "text": text,
            "parse_mode": "Markdown",
        }
        
        return self._http_post(url, telegram_payload)
    
    def _http_post(self, url: str, payload: Dict) -> bool:
        """Send HTTP POST request."""
        try:
            data = json.dumps(payload).encode("utf-8")
            
            req = Request(
                url,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Tokenade/3.3",
                },
                method="POST"
            )
            
            if self.config.secret:
                signature = hmac.HMAC(
                    self.config.secret.encode(),
                    data,
                    hashlib.sha256
                ).hexdigest()
                req.add_header("X-Tokenade-Signature", signature)
            
            ctx = ssl.create_default_context()
            
            response = urlopen(req, context=ctx, timeout=10)
            return response.status < 400
            
        except URLError as e:
            logger.error(f"Webhook request failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return False


class WebhookManager:
    """Manage multiple webhook configurations."""
    
    def __init__(self):
        self._webhooks: Dict[str, WebhookConfig] = {}
    
    def add(self, name: str, config: WebhookConfig):
        """Add a webhook configuration."""
        self._webhooks[name] = config
    
    def remove(self, name: str) -> bool:
        """Remove a webhook configuration."""
        return self._webhooks.pop(name, None) is not None
    
    def send(self, name: str, event_type: str, session_data: Dict) -> bool:
        """Send event to a specific webhook."""
        config = self._webhooks.get(name)
        if not config:
            logger.error(f"Webhook not found: {name}")
            return False
        
        integration = WebhookIntegration(config)
        return integration.send_session_event(event_type, session_data)
    
    def broadcast(self, event_type: str, session_data: Dict) -> Dict[str, bool]:
        """Send event to all configured webhooks."""
        results = {}
        for name, config in self._webhooks.items():
            integration = WebhookIntegration(config)
            results[name] = integration.send_session_event(event_type, session_data)
        return results
    
    def list_webhooks(self) -> List[Dict]:
        """List all configured webhooks."""
        return [
            {"name": name, "type": config.type, "url": config.url[:50] + "..."}
            for name, config in self._webhooks.items()
        ]
