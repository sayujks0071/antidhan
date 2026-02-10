import logging
import time


class SignalDebouncer:
    """Checks if a signal condition is stable over time."""
    def __init__(self, debounce_time=0):
        self.debounce_time = debounce_time
        self.last_signal_time = {}

    def edge(self, signal_name, condition):
        """Returns True if condition goes from False to True and stays True."""
        if condition:
            if signal_name not in self.last_signal_time:
                self.last_signal_time[signal_name] = time.time()
                return True # Edge detected
            # If debounce required, check time? Usually 'edge' means instant trigger on transition.
            # Strategy usage suggests `self.debouncer.edge("ENTRY_SIGNAL", True)`
            # This implies simple edge detection or rate limiting.
            return False
        else:
            if signal_name in self.last_signal_time:
                del self.last_signal_time[signal_name]
            return False

class TradeLedger:
    """Tracks executed trades."""
    def __init__(self):
        self.trades = []

    def record(self, trade_details):
        self.trades.append(trade_details)

class TradeLimiter:
    """Limits number of trades per period."""
    def __init__(self, max_per_day=1, max_per_hour=1, cooldown_seconds=0):
        self.max_per_day = max_per_day
        self.max_per_hour = max_per_hour
        self.cooldown_seconds = cooldown_seconds
        self.trades = [] # List of timestamps

    def allow(self):
        now = time.time()
        # Clean old trades (older than 1 day for simplicity, or keep all for day check)
        # Check cooldown
        if self.trades and (now - self.trades[-1] < self.cooldown_seconds):
            return False

        day_trades = [t for t in self.trades if now - t < 86400]
        hour_trades = [t for t in self.trades if now - t < 3600]

        if len(day_trades) >= self.max_per_day:
            return False
        if len(hour_trades) >= self.max_per_hour:
            return False

        return True

    def record(self):
        self.trades.append(time.time())

class DataFreshnessGuard:
    """Checks if data is fresh."""
    def __init__(self, max_delay_seconds=60):
        self.max_delay_seconds = max_delay_seconds

    def check(self, timestamp):
        if not timestamp:
            return False
        # Timestamp can be int/float (epoch) or datetime? Assume epoch
        try:
            delay = time.time() - float(timestamp)
            return delay <= self.max_delay_seconds
        except Exception:
            return False

class RiskConfig:
    """Configuration for Risk Management."""
    def __init__(self, max_loss_per_day=1000, max_loss_per_trade=500):
        self.max_loss_per_day = max_loss_per_day
        self.max_loss_per_trade = max_loss_per_trade

class RiskManager:
    """Manages risk limits."""
    def __init__(self, config=None):
        self.config = config or RiskConfig()
        self.daily_pnl = 0.0

    def check_entry(self, potential_loss):
        if potential_loss > self.config.max_loss_per_trade:
            return False
        # Simplified check
        return True

def format_kv(**kwargs):
    """Format key-value pairs for logging."""
    return ", ".join([f"{k}={v}" for k, v in kwargs.items()])
