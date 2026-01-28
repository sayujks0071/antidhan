#!/usr/bin/env python3
"""
Clawdbot Alert Service
Centralized alert routing through Clawdbot channels (Telegram, WhatsApp, Slack, etc.)
"""
import os
import sys
import logging
from typing import List, Optional
from datetime import datetime
from pathlib import Path

# Add services to path
services_path = Path(__file__).parent
if str(services_path) not in sys.path:
    sys.path.insert(0, str(services_path))

try:
    from clawdbot_bridge_service import get_bridge_service
except ImportError:
    logging.warning("Clawdbot bridge service not available")
    get_bridge_service = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ClawdbotAlertService")

class ClawdbotAlertService:
    """Centralized alert service for routing trading alerts via Clawdbot"""
    
    def __init__(self):
        self.bridge = get_bridge_service() if get_bridge_service else None
        self.enabled = os.getenv("CLAWDBOT_ENABLED", "true").lower() == "true"
        self.channels = os.getenv("CLAWDBOT_ALERT_CHANNELS", "telegram").split(",")
    
    def format_alert(self, message: str, priority: str = "info", context: dict = None) -> str:
        """Format alert message with emojis and structure"""
        emoji_map = {
            "info": "ℹ️",
            "warning": "⚠️",
            "critical": "🚨",
            "success": "✅",
            "error": "❌"
        }
        
        emoji = emoji_map.get(priority, "ℹ️")
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        formatted = f"{emoji} [{timestamp}] {message}"
        
        if context:
            context_str = " | ".join([f"{k}: {v}" for k, v in context.items()])
            formatted += f"\n   {context_str}"
        
        return formatted
    
    def send_alert(
        self,
        message: str,
        priority: str = "info",
        channels: Optional[List[str]] = None,
        context: dict = None
    ) -> bool:
        """
        Send alert to configured channels.
        
        Args:
            message: Alert message
            priority: Priority level (info, warning, critical, success, error)
            channels: List of channels to send to (defaults to configured channels)
            context: Additional context data
            
        Returns:
            bool: True if sent successfully
        """
        if not self.enabled or not self.bridge:
            logger.debug("Clawdbot alert service disabled or bridge unavailable")
            return False
        
        channels = channels or self.channels
        formatted_message = self.format_alert(message, priority, context)
        
        success_count = 0
        for channel in channels:
            try:
                result = self.bridge.send_trading_alert(channel.strip(), formatted_message, priority)
                if result.get("status") == "sent":
                    success_count += 1
                    logger.debug(f"Alert sent to {channel}")
                else:
                    logger.warning(f"Failed to send alert to {channel}: {result}")
            except Exception as e:
                logger.error(f"Error sending alert to {channel}: {e}")
        
        return success_count > 0
    
    def send_entry_alert(
        self,
        symbol: str,
        action: str,
        quantity: int,
        price: float,
        exchange: str = "NSE",
        strategy: str = "Unknown",
        context: dict = None
    ):
        """Send entry alert"""
        message = f"{strategy}: {action} {quantity} {symbol} @ {price:.2f} ({exchange})"
        return self.send_alert(message, "info", context=context or {})
    
    def send_exit_alert(
        self,
        symbol: str,
        action: str,
        quantity: int,
        price: float,
        reason: str,
        exchange: str = "NSE",
        strategy: str = "Unknown",
        context: dict = None
    ):
        """Send exit alert"""
        message = f"{strategy}: {action} {quantity} {symbol} @ {price:.2f} | Reason: {reason} ({exchange})"
        priority = "warning" if "STOP_LOSS" in reason or "LOSS" in reason else "info"
        return self.send_alert(message, priority, context=context or {})
    
    def send_take_profit_alert(
        self,
        symbol: str,
        level: str,
        price: float,
        strategy: str = "Unknown"
    ):
        """Send take profit alert"""
        message = f"{strategy}: {level} hit for {symbol} @ {price:.2f}"
        return self.send_alert(message, "success")
    
    def send_stop_loss_alert(
        self,
        symbol: str,
        price: float,
        strategy: str = "Unknown"
    ):
        """Send stop loss alert"""
        message = f"{strategy}: Stop loss hit for {symbol} @ {price:.2f}"
        return self.send_alert(message, "warning")
    
    def send_error_alert(
        self,
        error_message: str,
        strategy: str = "Unknown",
        context: dict = None
    ):
        """Send error alert"""
        message = f"{strategy}: Error - {error_message}"
        return self.send_alert(message, "error", context=context or {})


# Singleton instance
_alert_service_instance: Optional[ClawdbotAlertService] = None

def get_alert_service() -> ClawdbotAlertService:
    """Get or create singleton alert service instance"""
    global _alert_service_instance
    if _alert_service_instance is None:
        _alert_service_instance = ClawdbotAlertService()
    return _alert_service_instance
