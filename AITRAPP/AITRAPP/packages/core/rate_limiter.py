"""Rate limiter using leaky bucket algorithm"""
import asyncio
import time
from typing import Optional

import structlog

from packages.core.metrics import throttle_queue_depth

logger = structlog.get_logger(__name__)


class LeakyBucketLimiter:
    """Leaky bucket rate limiter for API calls"""

    def __init__(self, rate_per_second: float, rate_per_minute: Optional[float] = None,
                 bucket_size: int = 10):
        """
        Args:
            rate_per_second: Maximum requests per second
            rate_per_minute: Maximum requests per minute (optional)
            bucket_size: Maximum queue depth
        """
        self.rate_per_second = rate_per_second
        self.rate_per_minute = rate_per_minute
        self.bucket_size = bucket_size

        # Per-second bucket
        self.last_second_time = time.time()
        self.tokens_second = rate_per_second

        # Per-minute bucket
        if rate_per_minute:
            self.last_minute_time = time.time()
            self.tokens_minute = rate_per_minute

        self.queue = asyncio.Queue(maxsize=bucket_size)
        self._lock = asyncio.Lock()

    async def acquire(self, limiter_type: str = "default") -> bool:
        """
        Acquire a token (wait if needed).
        
        Args:
            limiter_type: Type of limiter (for metrics)
        
        Returns:
            True if acquired, False if queue full
        """
        # Update queue depth metric
        throttle_queue_depth.labels(type=limiter_type).set(self.queue.qsize())

        # Check if queue is full
        if self.queue.full():
            logger.warning("Rate limiter queue full", type=limiter_type, queue_size=self.queue.qsize())
            return False

        async with self._lock:
            now = time.time()

            # Refill per-second bucket
            elapsed = now - self.last_second_time
            self.tokens_second = min(
                self.rate_per_second,
                self.tokens_second + elapsed * self.rate_per_second
            )
            self.last_second_time = now

            # Refill per-minute bucket if configured
            if self.rate_per_minute:
                elapsed_minute = now - self.last_minute_time
                if elapsed_minute >= 60:
                    self.tokens_minute = self.rate_per_minute
                    self.last_minute_time = now
                elif elapsed_minute > 0:
                    self.tokens_minute = min(
                        self.rate_per_minute,
                        self.tokens_minute + elapsed_minute * (self.rate_per_minute / 60)
                    )

            # Check if we can acquire immediately
            if self.tokens_second >= 1.0:
                if not self.rate_per_minute or self.tokens_minute >= 1.0:
                    self.tokens_second -= 1.0
                    if self.rate_per_minute:
                        self.tokens_minute -= 1.0
                    return True

            # Need to wait - add to queue
            wait_time = max(0, (1.0 - self.tokens_second) / self.rate_per_second)
            if self.rate_per_minute and self.tokens_minute < 1.0:
                wait_time = max(wait_time, (1.0 - self.tokens_minute) / (self.rate_per_minute / 60))

            try:
                await asyncio.sleep(wait_time)
                # Retry after wait
                return await self.acquire(limiter_type)
            except asyncio.CancelledError:
                return False

