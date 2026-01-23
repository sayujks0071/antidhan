"""Price utilities for order validation"""
from typing import Tuple
import structlog

logger = structlog.get_logger(__name__)


def clamp_price(price: float, tick_size: float) -> float:
    """
    Clamp price to valid tick size.
    
    Args:
        price: Raw price
        tick_size: Minimum price increment (e.g., 0.05 for options)
    
    Returns:
        Price rounded to nearest tick
    """
    if tick_size <= 0:
        return price
    
    return round(round(price / tick_size) * tick_size, 10)


def within_band(price: float, lower: float, upper: float) -> bool:
    """
    Check if price is within valid band.
    
    Args:
        price: Price to check
        lower: Lower bound
        upper: Upper bound
    
    Returns:
        True if price is within band
    """
    return lower <= price <= upper


def validate_order_price(
    price: float,
    tick_size: float,
    lower_band: Optional[float] = None,
    upper_band: Optional[float] = None
) -> Tuple[float, bool]:
    """
    Validate and clamp order price.
    
    Args:
        price: Raw price
        tick_size: Minimum price increment
        lower_band: Lower price limit (optional)
        upper_band: Upper price limit (optional)
    
    Returns:
        (clamped_price, is_valid)
    """
    clamped = clamp_price(price, tick_size)
    
    if lower_band is not None and upper_band is not None:
        if not within_band(clamped, lower_band, upper_band):
            logger.warning(
                "Price outside bands",
                price=clamped,
                lower=lower_band,
                upper=upper_band
            )
            return clamped, False
    
    return clamped, True

