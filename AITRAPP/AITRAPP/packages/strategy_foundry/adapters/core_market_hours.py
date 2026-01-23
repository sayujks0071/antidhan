from packages.core.market_hours import MarketHoursGuard, MARKET_OPEN, MARKET_CLOSE, HARD_CLOSE, IST
from datetime import datetime, time
import pytz

class MarketHoursAdapter:
    def __init__(self):
        self.guard = MarketHoursGuard()

    def is_market_open(self, dt: datetime = None) -> bool:
        return self.guard.is_market_open(dt)

    def get_market_close_time(self) -> time:
        return MARKET_CLOSE

    def get_hard_close_time(self) -> time:
        return HARD_CLOSE
