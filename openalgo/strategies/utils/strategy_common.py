"""
[MOCK] Strategy Common Utilities for OpenAlgo Strategies.
This file mocks the behavior of the real utility file for development and testing.
"""
import time
import math

class SignalDebouncer:
    """Detects signal edges (False -> True) to prevent re-triggering."""
    def __init__(self):
        self.last_states = {}

    def edge(self, signal_name, condition_bool):
        """Returns True ONLY on the rising edge of the condition."""
        last = self.last_states.get(signal_name, False)
        self.last_states[signal_name] = condition_bool
        return condition_bool and not last

class TradeLedger:
    """Logs trades to a CSV file."""
    def __init__(self, filepath):
        self.filepath = filepath

    def append(self, trade_dict):
        """Appends a trade record."""
        # Mock logging to file
        print(f"TradeLedger: Appended {trade_dict}")

class TradeLimiter:
    """Limits trade frequency."""
    def __init__(self, max_per_day, max_per_hour, cooldown_seconds):
        self.max_per_day = max_per_day
        self.max_per_hour = max_per_hour
        self.cooldown_seconds = cooldown_seconds
        self.last_trade_time = 0
        self.daily_count = 0
        self.hourly_count = 0

    def allow(self):
        """Checks if a trade is allowed."""
        now = time.time()
        if now - self.last_trade_time < self.cooldown_seconds:
            return False
        if self.daily_count >= self.max_per_day:
            return False
        # Simplified hourly check (resetting logic omitted for brevity in mock)
        if self.hourly_count >= self.max_per_hour:
            return False
        return True

    def record(self):
        """Records a trade execution."""
        self.last_trade_time = time.time()
        self.daily_count += 1
        self.hourly_count += 1

def format_kv(**kwargs):
    """Formats key-value pairs for logging."""
    return " ".join([f"{k}={v}" for k, v in kwargs.items()])
