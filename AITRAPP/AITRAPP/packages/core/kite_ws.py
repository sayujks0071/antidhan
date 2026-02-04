"""Safe KiteTicker wrapper for graceful shutdown and reconnection"""
import asyncio

import structlog
from kiteconnect import KiteTicker

logger = structlog.get_logger(__name__)


class SafeKiteTicker:
    """Wrapper around KiteTicker with defensive error handling"""

    def __init__(self, ticker: KiteTicker):
        self.ticker = ticker

    def stop(self) -> None:
        """Safely stop the ticker, handling missing attributes gracefully"""
        try:
            # Newer libs: .close() exists; older: .stop()
            close_fn = getattr(self.ticker, "close", None)
            stop_fn = getattr(self.ticker, "stop", None)

            if callable(close_fn):
                close_fn()
            elif callable(stop_fn):
                stop_fn()
            else:
                logger.warning("KiteTicker has no close() or stop() method")
        except AttributeError as e:
            # Some versions have transient .factory or socket refs; ignore on teardown
            logger.warning(f"KiteTicker stop error (ignored): {e}", exc_info=False)
        except Exception as e:
            logger.warning(f"KiteTicker stop error: {e}", exc_info=False)

    async def reconnect(self, delay: float = 1.0) -> None:
        """Stop and reconnect the ticker after a delay"""
        self.stop()
        await asyncio.sleep(delay)

        try:
            start_fn = getattr(self.ticker, "connect", None) or getattr(self.ticker, "start", None)
            if callable(start_fn):
                # Check if it's threaded or async
                if hasattr(start_fn, '__code__') and 'threaded' in start_fn.__code__.co_varnames:
                    start_fn(threaded=True)
                else:
                    start_fn()
            else:
                raise AttributeError("KiteTicker has no connect() or start() method")
        except Exception as e:
            logger.error(f"KiteTicker reconnect failed: {e}")
            raise

