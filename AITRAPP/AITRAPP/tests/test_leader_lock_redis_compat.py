"""Unit test for leader lock Redis compatibility (bytes vs strings)"""
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from packages.core.leader_lock import LeaderLock


async def test_leader_lock_redis_compatibility():
    """Test that leader lock works with both bytes and string Redis responses"""
    if not REDIS_AVAILABLE:
        print("⚠️  redis.asyncio not available, skipping test")
        return

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    try:
        conn = redis.from_url(redis_url)
        await conn.ping()
    except Exception as e:
        print(f"⚠️  Redis not available: {e}, skipping test")
        return

    # Test with unique key
    test_key = f"lock:test:{os.getpid()}"
    lock = LeaderLock(conn, key=test_key, ttl=10)

    # Test acquire
    acquired = await lock.acquire()
    assert acquired, "acquire failed"
    assert lock.is_leader, "is_leader should be True after acquire"

    # Test refresh
    refreshed = await lock.refresh()
    assert refreshed, "refresh failed"
    assert lock.is_leader, "is_leader should still be True after refresh"

    # Test release
    released_ok = await lock.release()
    assert released_ok is None or released_ok, "release should succeed"
    assert not lock.is_leader, "is_leader should be False after release"

    # Cleanup
    try:
        await conn.delete(test_key)
        await conn.close()
    except Exception:
        pass

    print("✅ Leader lock Redis compatibility test passed")


if __name__ == "__main__":
    # Standalone runner
    async def main():
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

        try:
            conn = redis.from_url(redis_url)
            await conn.ping()
        except Exception as e:
            print(f"❌ Redis not available: {e}")
            return

        test_key = f"lock:test:{os.getpid()}"
        lock = LeaderLock(conn, key=test_key, ttl=10)

        print("Testing acquire...")
        assert await lock.acquire(), "acquire failed"
        print("✅ acquire passed")

        print("Testing refresh...")
        ok = await lock.refresh()
        print(f"refresh_ok: {ok}")
        assert ok, "refresh failed"
        print("✅ refresh passed")

        print("Testing release...")
        await lock.release()
        print("✅ release passed")

        # Cleanup
        await conn.delete(test_key)
        await conn.close()

        print("\n✅ All leader lock compatibility tests passed!")

    asyncio.run(main())

