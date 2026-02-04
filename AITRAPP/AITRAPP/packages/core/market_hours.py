"""Market hours and holiday management"""
from datetime import datetime, time
from typing import List

import pytz
import structlog

from packages.core.nse_holidays import get_trading_holidays

logger = structlog.get_logger(__name__)

# NSE trading hours (IST)
MARKET_OPEN = time(9, 15)  # 09:15 IST
MARKET_CLOSE = time(15, 20)  # 15:20 IST (entries stop, exits allowed until 15:25)
HARD_CLOSE = time(15, 25)  # 15:25 IST (all positions must be flat)

IST = pytz.timezone("Asia/Kolkata")


class MarketHoursGuard:
    """Guards against trading outside market hours"""

    def __init__(self, trading_holidays: List[str] = None):
        """
        Args:
            trading_holidays: List of holiday dates in YYYY-MM-DD format
        """
        if trading_holidays:
            self.trading_holidays = set(trading_holidays)
        else:
            self.trading_holidays = get_trading_holidays()

    def is_market_open(self, dt: datetime = None) -> bool:
        """
        Check if market is open for entries.
        
        Args:
            dt: Datetime to check (default: now in IST)
        
        Returns:
            True if market is open for entries
        """
        if dt is None:
            dt = datetime.now(IST)
        else:
            # Ensure timezone-aware
            if dt.tzinfo is None:
                dt = IST.localize(dt)
            else:
                dt = dt.astimezone(IST)

        # Check if holiday
        date_str = dt.date().isoformat()
        if date_str in self.trading_holidays:
            logger.debug("Market closed: holiday", date=date_str)
            return False

        # Check if weekend
        if dt.weekday() >= 5:  # Saturday = 5, Sunday = 6
            logger.debug("Market closed: weekend", weekday=dt.weekday())
            return False

        # Check trading hours
        current_time = dt.time()
        if current_time < MARKET_OPEN or current_time >= MARKET_CLOSE:
            logger.debug("Market closed: outside hours",
                        current_time=current_time,
                        open=MARKET_OPEN,
                        close=MARKET_CLOSE)
            return False

        return True

    def can_place_entry(self, dt: datetime = None) -> bool:
        """
        Check if entry orders can be placed.
        
        Entries allowed: 09:15 - 15:20 IST
        """
        return self.is_market_open(dt)

    def can_place_exit(self, dt: datetime = None) -> bool:
        """
        Check if exit orders can be placed.
        
        Exits allowed: 09:15 - 15:25 IST
        """
        if dt is None:
            dt = datetime.now(IST)
        else:
            if dt.tzinfo is None:
                dt = IST.localize(dt)
            else:
                dt = dt.astimezone(IST)

        # Check if holiday
        date_str = dt.date().isoformat()
        if date_str in self.trading_holidays:
            return False

        # Check if weekend
        if dt.weekday() >= 5:
            return False

        # Check trading hours (exits allowed until 15:25)
        current_time = dt.time()
        if current_time < MARKET_OPEN or current_time >= HARD_CLOSE:
            return False

        return True

    def is_expiry_day(self, dt: datetime = None) -> bool:
        """
        Check if today is weekly/monthly expiry.
        
        TODO: Load from NSE calendar or calculate from expiry dates
        """
        if dt is None:
            dt = datetime.now(IST)
        else:
            if dt.tzinfo is None:
                dt = IST.localize(dt)
            else:
                dt = dt.astimezone(IST)

        # Thursday = weekly expiry, last Thursday = monthly expiry
        # This is a placeholder - should load from NSE calendar
        if dt.weekday() == 3:  # Thursday
            # Check if last Thursday of month (rough check)
            next_thursday = dt.replace(day=dt.day + 7)
            if next_thursday.month != dt.month:
                return True  # Monthly expiry
            return True  # Weekly expiry

        return False

    def add_holiday(self, date_str: str) -> None:
        """Add a trading holiday"""
        self.trading_holidays.add(date_str)
        logger.info("Holiday added", date=date_str)

    def remove_holiday(self, date_str: str) -> None:
        """Remove a trading holiday"""
        self.trading_holidays.discard(date_str)
        logger.info("Holiday removed", date=date_str)

