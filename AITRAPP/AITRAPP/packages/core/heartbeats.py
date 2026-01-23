"""Heartbeat tracking for market data, order stream, and scan loop"""
import asyncio
import time
import structlog

from packages.core.metrics import (
    marketdata_heartbeat_seconds,
    order_stream_heartbeat_seconds,
    scan_heartbeat_seconds,
)

logger = structlog.get_logger(__name__)

# Track last event times
_last_md = time.monotonic()
_last_order = time.monotonic()
_last_scan = time.monotonic()


def touch_marketdata() -> None:
    """Call on every market data tick"""
    global _last_md
    _last_md = time.monotonic()


def touch_order() -> None:
    """Call on every order event/ack"""
    global _last_order
    _last_order = time.monotonic()


def touch_scan() -> None:
    """Call once per orchestrator scan cycle"""
    global _last_scan
    _last_scan = time.monotonic()


async def run_heartbeat_updater(interval: float = 1.0, stop: asyncio.Event | None = None) -> None:
    """Background task to update heartbeat metrics"""
    log = logger.bind(component="heartbeats")
    
    try:
        while not (stop and stop.is_set()):
            now = time.monotonic()
            
            # Update heartbeat gauges
            marketdata_heartbeat_seconds.set(now - _last_md)
            order_stream_heartbeat_seconds.set(now - _last_order)
            scan_heartbeat_seconds.set(now - _last_scan)
            
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        log.info("Heartbeat updater cancelled")
    except Exception as e:
        log.error(f"Heartbeat updater error: {e}", exc_info=True)
    finally:
        log.info("Heartbeat updater stopped")

