"""Alerting system for critical events"""
import os
import json
from typing import Optional
import structlog
import httpx

logger = structlog.get_logger(__name__)


class AlertManager:
    """Manages alerts for critical system events"""
    
    def __init__(self):
        self.telegram_bot_token = os.getenv("TG_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TG_CHAT_ID")
        self.slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        self.enabled = bool(self.telegram_bot_token or self.slack_webhook_url)
    
    def send_telegram(self, message: str) -> bool:
        """Send alert via Telegram"""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            response = httpx.post(
                url,
                json={"chat_id": self.telegram_chat_id, "text": message},
                timeout=5.0
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"Telegram alert failed: {e}")
            return False
    
    def send_slack(self, message: str) -> bool:
        """Send alert via Slack"""
        if not self.slack_webhook_url:
            return False
        
        try:
            response = httpx.post(
                self.slack_webhook_url,
                json={"text": message},
                timeout=5.0
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"Slack alert failed: {e}")
            return False
    
    def alert_kill_switch(self, reason: str, details: Optional[dict] = None) -> None:
        """Alert on kill switch activation"""
        if not self.enabled:
            return
        
        message = f"🚨 KILL SWITCH ACTIVATED\n\nReason: {reason}"
        if details:
            message += f"\nDetails: {json.dumps(details, indent=2)}"
        
        # Try both channels
        self.send_telegram(message)
        self.send_slack(message)
        
        logger.critical("Kill switch alert sent", reason=reason)


# Global instance
alert_manager = AlertManager()

