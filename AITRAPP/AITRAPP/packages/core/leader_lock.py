"""Leader lock to ensure only one orchestrator instance runs"""
import uuid

import structlog

logger = structlog.get_logger(__name__)


class LeaderLock:
    """Redis-based leader lock to prevent multiple orchestrator instances"""

    def __init__(self, redis, key: str = "trader:leader", ttl: int = 30):
        """
        Args:
            redis: Redis client (aioredis or redis)
            key: Redis key for leader lock
            ttl: Time-to-live in seconds (lock expires if not refreshed)
        """
        self.redis = redis
        self.key = key
        self.ttl = ttl
        self.instance_id = str(uuid.uuid4())
        self.is_leader = False

    async def acquire(self) -> bool:
        """
        Try to acquire leader lock.
        
        Returns:
            True if lock acquired, False if another instance is leader
        """
        try:
            # SET key val NX EX ttl
            # NX = only set if not exists
            # EX = expire after ttl seconds
            result = await self.redis.set(
                self.key,
                self.instance_id,
                nx=True,
                ex=self.ttl
            )

            if result:
                self.is_leader = True
                logger.info("Leader lock acquired", instance_id=self.instance_id)
            else:
                existing_leader = await self.redis.get(self.key)
                # Handle both bytes and strings (Redis client compatibility)
                if existing_leader:
                    if isinstance(existing_leader, bytes):
                        existing_leader = existing_leader.decode()
                logger.warning(
                    "Failed to acquire leader lock",
                    instance_id=self.instance_id,
                    existing_leader=existing_leader
                )

            return result
        except Exception as e:
            logger.error("Error acquiring leader lock", error=str(e))
            return False

    async def refresh(self) -> bool:
        """
        Refresh leader lock (must be called periodically).
        
        Returns:
            True if still leader, False if lost leadership
        """
        if not self.is_leader:
            return False

        try:
            # Use pipeline for atomic check-and-update
            pipe = self.redis.pipeline()
            pipe.watch(self.key)

            current_leader = await self.redis.get(self.key)
            # Handle both bytes and strings (Redis client compatibility)
            if current_leader:
                if isinstance(current_leader, bytes):
                    current_leader = current_leader.decode()
            if current_leader is None or current_leader != self.instance_id:
                pipe.reset()
                self.is_leader = False
                logger.warning("Lost leader lock", instance_id=self.instance_id)
                # Track leader change
                from packages.core.metrics import leader_changes_total
                leader_changes_total.inc()
                return False

            # Still leader - refresh TTL
            pipe.multi()
            pipe.expire(self.key, self.ttl)
            await pipe.execute()

            return True
        except Exception as e:
            logger.error("Error refreshing leader lock", error=str(e))
            self.is_leader = False
            return False

    async def release(self) -> None:
        """Release leader lock"""
        if not self.is_leader:
            return

        try:
            # Only delete if we're still the leader
            current_leader = await self.redis.get(self.key)
            # Handle both bytes and strings (Redis client compatibility)
            if current_leader:
                if isinstance(current_leader, bytes):
                    current_leader = current_leader.decode()
            if current_leader and current_leader == self.instance_id:
                await self.redis.delete(self.key)
                logger.info("Leader lock released", instance_id=self.instance_id)
            self.is_leader = False
        except Exception as e:
            logger.error("Error releasing leader lock", error=str(e))

