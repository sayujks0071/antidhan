import time
import logging

class SignalDebouncer:
    """
    Tracks signal state changes to detect rising/falling edges.
    """
    def __init__(self):
        self.states = {}

    def edge(self, key, value):
        """
        Returns True if the value changed from False (or undefined) to True.
        """
        previous = self.states.get(key, False)
        self.states[key] = value

        # Rising edge: was False, now True
        if not previous and value:
            return True
        return False

class TradeLedger:
    """
    Simple ledger to record trades.
    """
    def __init__(self):
        self.trades = []

    def log(self, trade):
        self.trades.append(trade)

class TradeLimiter:
    """
    Limits the number of trades per day/hour and enforces cooldowns.
    """
    def __init__(self, max_per_day=1, max_per_hour=1, cooldown_seconds=300):
        self.max_per_day = max_per_day
        self.max_per_hour = max_per_hour
        self.cooldown_seconds = cooldown_seconds
        self.trades = []
        self.last_trade_time = 0

    def allow(self):
        now = time.time()

        # Check cooldown
        if now - self.last_trade_time < self.cooldown_seconds:
            return False

        # Filter trades within the last day (86400 seconds)
        day_trades = [t for t in self.trades if now - t < 86400]
        if len(day_trades) >= self.max_per_day:
            return False

        # Filter trades within the last hour (3600 seconds)
        hour_trades = [t for t in self.trades if now - t < 3600]
        if len(hour_trades) >= self.max_per_hour:
            return False

        return True

    def record(self):
        now = time.time()
        self.trades.append(now)
        self.last_trade_time = now

def format_kv(**kwargs):
    """
    Formats key-value pairs into a log string.
    """
    return " ".join([f"{k}={v}" for k, v in kwargs.items()])
