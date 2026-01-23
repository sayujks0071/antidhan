"""Kite Client wrapper for order operations"""
from typing import Optional, Callable
import structlog
from kiteconnect import KiteConnect
from kiteconnect.exceptions import TokenException, NetworkException

from packages.core.metrics import retries_total

logger = structlog.get_logger(__name__)


class TokenExpiredError(Exception):
    """Raised when access token has expired"""
    pass


class KiteClient:
    """Wrapper around KiteConnect for order operations with token expiry handling"""
    
    def __init__(self, kite: KiteConnect, token_refresh_callback: Optional[Callable] = None):
        self.kite = kite
        self.token_refresh_callback = token_refresh_callback
    
    def _handle_auth_error(self, e: Exception) -> None:
        """Handle authentication errors (401/403)"""
        error_str = str(e).lower()
        if '401' in error_str or '403' in error_str or 'token' in error_str or 'unauthorized' in error_str:
            logger.critical("Access token expired or invalid", error=str(e))
            retries_total.labels(type="token_refresh").inc()
            
            if self.token_refresh_callback:
                try:
                    self.token_refresh_callback()
                    logger.info("Token refreshed via callback")
                except Exception as refresh_error:
                    logger.error("Token refresh failed", error=str(refresh_error))
                    raise TokenExpiredError("Token expired and refresh failed")
            else:
                raise TokenExpiredError("Token expired - no refresh callback configured")
    
    def place_order(self, **kwargs) -> Optional[str]:
        """Place an order via Kite Connect with token expiry handling"""
        try:
            order_id = self.kite.place_order(**kwargs)
            logger.info("Order placed", order_id=order_id, **kwargs)
            return str(order_id)
        except (TokenException, NetworkException) as e:
            self._handle_auth_error(e)
            # Retry once after token refresh
            try:
                order_id = self.kite.place_order(**kwargs)
                logger.info("Order placed after token refresh", order_id=order_id, **kwargs)
                return str(order_id)
            except Exception as retry_error:
                logger.error("Failed to place order after token refresh", error=str(retry_error), **kwargs)
                raise
        except Exception as e:
            logger.error("Failed to place order", error=str(e), **kwargs)
            raise
    
    def cancel_order(self, order_id: str, variety: str = "regular") -> None:
        """Cancel an order"""
        try:
            self.kite.cancel_order(variety=variety, order_id=order_id)
            logger.info("Order cancelled", order_id=order_id)
        except Exception as e:
            logger.error("Failed to cancel order", error=str(e), order_id=order_id)
            raise
    
    def get_orders(self) -> list:
        """Get all orders"""
        try:
            orders = self.kite.orders()
            return orders
        except Exception as e:
            logger.error("Failed to get orders", error=str(e))
            return []

