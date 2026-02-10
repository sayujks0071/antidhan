import time
import os
import csv
from datetime import datetime
import threading

class SignalDebouncer:
    """
    Prevents signal flickering by ensuring a signal is only triggered on a False->True transition.
    Also supports cooldowns.
    """
    def __init__(self, cooldown_seconds=0):
        self.states = {}
        self.last_triggered = {}
        self.cooldown_seconds = cooldown_seconds

    def edge(self, name, condition):
        """
        Returns True only when condition transitions from False to True.
        """
        previous = self.states.get(name, False)
        self.states[name] = condition

        if condition and not previous:
            # Check cooldown
            last = self.last_triggered.get(name, 0)
            now = time.time()
            if (now - last) >= self.cooldown_seconds:
                self.last_triggered[name] = now
                return True

        return False

class TradeLimiter:
    """
    Limits the number of trades per day/hour/minute to prevent overtrading.
    """
    def __init__(self, max_per_day=20, max_per_hour=5, cooldown_seconds=60):
        self.max_per_day = max_per_day
        self.max_per_hour = max_per_hour
        self.cooldown_seconds = cooldown_seconds

        self.trades_today = []
        self.last_trade_time = 0

    def allow(self):
        """
        Checks if a new trade is allowed.
        """
        now = time.time()

        # 1. Cooldown
        if (now - self.last_trade_time) < self.cooldown_seconds:
            return False

        # Clean up old trades from list (keep only today's)
        # Assuming run loop is continuous, we can just filter
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        self.trades_today = [t for t in self.trades_today if t >= today_start]

        # 2. Daily Limit
        if len(self.trades_today) >= self.max_per_day:
            return False

        # 3. Hourly Limit
        hour_ago = now - 3600
        trades_last_hour = [t for t in self.trades_today if t >= hour_ago]
        if len(trades_last_hour) >= self.max_per_hour:
            return False

        return True

    def record(self):
        """
        Records a trade execution.
        """
        now = time.time()
        self.trades_today.append(now)
        self.last_trade_time = now

class TradeLedger:
    """
    Logs trades to a CSV file.
    """
    def __init__(self, filepath="trades.csv"):
        self.filepath = filepath
        # Ensure directory exists
        dirname = os.path.dirname(filepath)
        if dirname and not os.path.exists(dirname):
            try:
                os.makedirs(dirname)
            except OSError:
                pass # Already exists or permission error

    def append(self, data):
        """
        Appends a dictionary to the CSV.
        """
        if not data:
            return

        # Add timestamp if missing
        if "timestamp" not in data:
            data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        file_exists = os.path.isfile(self.filepath)

        try:
            with open(self.filepath, 'a', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=data.keys())
                if not file_exists:
                    writer.writeheader()
                writer.writerow(data)
        except Exception as e:
            print(f"Error writing to ledger: {e}")

def format_kv(**kwargs):
    """
    Formats key-value pairs into a log string.
    Example: format_kv(a=1, b=2) -> "a=1 b=2"
    """
    return " ".join([f"{k}={v}" for k, v in kwargs.items()])
