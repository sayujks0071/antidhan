from datetime import datetime, time

from packages.core.market_hours import HARD_CLOSE, MARKET_CLOSE, MarketHoursGuard


class MarketHoursAdapter:
    def __init__(self):
        self.guard = MarketHoursGuard()

    def is_market_open(self, dt: datetime = None) -> bool:
        return self.guard.is_market_open(dt)

    def get_market_close_time(self) -> time:
        return MARKET_CLOSE

    def get_hard_close_time(self) -> time:
        return HARD_CLOSE
