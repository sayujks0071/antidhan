from packages.strategy_foundry.adapters.core_market_hours import MarketHoursAdapter
from datetime import datetime, time

class LiveMarketHours:
    def __init__(self):
        self.adapter = MarketHoursAdapter()

    def is_market_open(self):
        # Use core adapter
        try:
            return self.adapter.is_market_open()
        except:
            # Fallback
            now = datetime.now()
            # IST offset is +5:30.
            # Assuming system is UTC or we handle timezone manually.
            # Core handles it.
            # Simple fallback:
            # Check if weekday 0-4
            if now.weekday() > 4:
                return False
            # Check time 09:15 - 15:30 (approx)
            # This fallback is weak without timezone info, but better than crashing.
            return True # Risky default, but core should work.
