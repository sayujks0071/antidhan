import time
import os
import csv
from datetime import datetime

class SignalDebouncer:
    def __init__(self):
        self.last_state = {}

    def edge(self, signal_name, condition_bool):
        """
        Returns True only on a False -> True transition (rising edge).
        """
        prev = self.last_state.get(signal_name, False)
        self.last_state[signal_name] = condition_bool
        return condition_bool and not prev

class TradeLimiter:
    def __init__(self, max_per_day, max_per_hour, cooldown_seconds):
        self.max_per_day = max_per_day
        self.max_per_hour = max_per_hour
        self.cooldown_seconds = cooldown_seconds

        self.trades_today = [] # List of timestamps
        self.last_trade_time = 0

    def allow(self):
        now = time.time()

        # Cooldown check
        if now - self.last_trade_time < self.cooldown_seconds:
            return False

        # Filter trades for today (reset if day changed)
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        self.trades_today = [t for t in self.trades_today if t >= today_start]

        if len(self.trades_today) >= self.max_per_day:
            return False

        # Filter trades for last hour
        hour_ago = now - 3600
        trades_last_hour = [t for t in self.trades_today if t >= hour_ago]

        if len(trades_last_hour) >= self.max_per_hour:
            return False

        return True

    def record(self):
        now = time.time()
        self.last_trade_time = now
        self.trades_today.append(now)

class TradeLedger:
    def __init__(self, filepath):
        self.filepath = filepath
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.filepath):
            try:
                os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
                with open(self.filepath, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(["timestamp", "side", "reason", "details"])
            except Exception as e:
                print(f"Error creating ledger: {e}", flush=True)

    def append(self, data):
        """
        data: dict with side, reason, details (timestamp added automatically)
        """
        try:
            with open(self.filepath, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().isoformat(),
                    data.get("side", ""),
                    data.get("reason", ""),
                    str(data.get("details", ""))
                ])
        except Exception as e:
            print(f"Error writing to ledger: {e}", flush=True)

def format_kv(**kwargs):
    """
    Formats key-value pairs for structured logging.
    Example: format_kv(spot=25000, signal="BUY") -> "spot=25000 signal=BUY"
    """
    return " ".join([f"{k}={v}" for k, v in kwargs.items()])
