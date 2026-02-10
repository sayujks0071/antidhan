import time
import os
import csv
import logging
from datetime import datetime

logger = logging.getLogger("StrategyCommon")

def format_kv(**kwargs):
    """
    Formats key-value pairs into a log-friendly string.
    Example: spot=123.45 signal=BUY -> "spot=123.45 signal=BUY"
    """
    return " ".join([f"{k}={v}" for k, v in kwargs.items()])

class SignalDebouncer:
    def __init__(self):
        self.states = {}

    def edge(self, name, condition):
        """
        Returns True only on a False -> True transition (Rising Edge).
        """
        last_state = self.states.get(name, False)
        self.states[name] = condition

        # Rising Edge: Last was False, Current is True
        return condition and not last_state

class TradeLimiter:
    def __init__(self, max_per_day, max_per_hour, cooldown_seconds):
        self.max_per_day = max_per_day
        self.max_per_hour = max_per_hour
        self.cooldown_seconds = cooldown_seconds
        self.trade_timestamps = []

    def allow(self):
        now = time.time()

        # Filter out old timestamps (> 24h) to keep list clean
        self.trade_timestamps = [t for t in self.trade_timestamps if now - t < 86400]

        # Check Cooldown
        if self.trade_timestamps:
            last_trade = self.trade_timestamps[-1]
            if now - last_trade < self.cooldown_seconds:
                return False

        # Check Hourly Limit
        trades_last_hour = [t for t in self.trade_timestamps if now - t < 3600]
        if len(trades_last_hour) >= self.max_per_hour:
            return False

        # Check Daily Limit
        trades_last_day = [t for t in self.trade_timestamps if now - t < 86400]
        # (Assuming day resets at midnight or rolling 24h? Prompt implies rolling or count)
        # Using rolling 24h for simplicity as "Day" usually implies session but script runs continuously.
        if len(trades_last_day) >= self.max_per_day:
            return False

        return True

    def record(self):
        self.trade_timestamps.append(time.time())

class TradeLedger:
    def __init__(self, filepath):
        self.filepath = filepath
        self.fieldnames = ["timestamp", "strategy", "symbol", "action", "price", "quantity", "reason"]

        # Ensure directory exists
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
        except OSError:
            pass # Maybe filepath is just a filename

        # Initialize file if not exists
        if not os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                    writer.writeheader()
            except Exception as e:
                logger.error(f"Failed to initialize ledger: {e}")

    def append(self, trade_data):
        """
        Appends a trade record to the CSV ledger.
        """
        try:
            # Add timestamp if missing
            if "timestamp" not in trade_data:
                trade_data["timestamp"] = datetime.now().isoformat()

            # Filter keys to match fieldnames (ignore extras)
            row = {k: trade_data.get(k, "") for k in self.fieldnames}

            with open(self.filepath, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                writer.writerow(row)
        except Exception as e:
            logger.error(f"Failed to write to ledger: {e}")
