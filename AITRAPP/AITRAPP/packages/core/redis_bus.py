"""Redis pub/sub bus for real-time events"""
import json
from typing import Any, Callable, Optional
import structlog

import redis.asyncio as aioredis
from packages.core.config import settings

logger = structlog.get_logger(__name__)


class RedisBus:
    """Redis pub/sub bus for decoupling components"""
    
    # Channel names
    CHANNEL_TICKS = "ticks"
    CHANNEL_SIGNALS = "signals"
    CHANNEL_DECISIONS = "decisions"
    CHANNEL_ORDERS = "orders"
    CHANNEL_RISK = "risk"
    CHANNEL_EVENTS = "events"
    
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or settings.redis_url
        self.redis: Optional[aioredis.Redis] = None
        self.pubsub: Optional[aioredis.client.PubSub] = None
    
    async def connect(self):
        """Connect to Redis"""
        try:
            self.redis = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            self.pubsub = self.redis.pubsub()
            logger.info("Connected to Redis", url=self.redis_url)
        except Exception as e:
            logger.error("Failed to connect to Redis", error=str(e))
            raise
    
    async def disconnect(self):
        """Disconnect from Redis"""
        if self.pubsub:
            await self.pubsub.unsubscribe()
            await self.pubsub.close()
        if self.redis:
            await self.redis.close()
        logger.info("Disconnected from Redis")
    
    async def publish(self, channel: str, data: Any):
        """Publish data to a channel"""
        if not self.redis:
            await self.connect()
        
        try:
            message = json.dumps(data, default=str)
            await self.redis.publish(channel, message)
            logger.debug("Published to channel", channel=channel, data_keys=list(data.keys()) if isinstance(data, dict) else None)
        except Exception as e:
            logger.error("Failed to publish to Redis", channel=channel, error=str(e))
    
    async def subscribe(self, channel: str, callback: Callable[[dict], None]):
        """Subscribe to a channel with a callback"""
        if not self.pubsub:
            await self.connect()
        
        await self.pubsub.subscribe(channel)
        logger.info("Subscribed to channel", channel=channel)
        
        async for message in self.pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    callback(data)
                except Exception as e:
                    logger.error("Error processing message", channel=channel, error=str(e))
    
    # Convenience methods for each channel
    async def publish_tick(self, token: int, tick_data: dict):
        """Publish tick data"""
        await self.publish(f"{self.CHANNEL_TICKS}.{token}", tick_data)
    
    async def publish_signal(self, signal_data: dict):
        """Publish signal"""
        await self.publish(self.CHANNEL_SIGNALS, signal_data)
    
    async def publish_decision(self, decision_data: dict):
        """Publish decision"""
        await self.publish(self.CHANNEL_DECISIONS, decision_data)
    
    async def publish_order(self, order_data: dict):
        """Publish order update"""
        await self.publish(self.CHANNEL_ORDERS, order_data)
    
    async def publish_risk(self, risk_data: dict):
        """Publish risk update"""
        await self.publish(self.CHANNEL_RISK, risk_data)
    
    async def publish_event(self, event_data: dict):
        """Publish general event"""
        await self.publish(self.CHANNEL_EVENTS, event_data)

