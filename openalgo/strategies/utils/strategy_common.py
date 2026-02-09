import time
import os
import csv
from datetime import datetime
import logging

logger = logging.getLogger("StrategyCommon")

class SignalDebouncer:
    """
    Prevents same signal re-triggering.
    """
    def __init__(self):
        self.state = {}

    def edge(self, key, condition_bool):
        """
        Returns True ONLY on False->True transition (rising edge)
        """
        prev = self.state.get(key, False)
        self.state[key] = condition_bool
        return condition_bool and not prev

    @staticmethod
    def cross_above(prev_val, curr_val, threshold):
        return prev_val <= threshold and curr_val > threshold

    @staticmethod
    def cross_below(prev_val, curr_val, threshold):
        return prev_val >= threshold and curr_val < threshold

class TradeLedger:
    def __init__(self, filepath):
        self.filepath = filepath
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(os.path.dirname(self.filepath)):
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        if not os.path.exists(self.filepath):
            with open(self.filepath, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "side", "reason", "details"])

    def append(self, data_dict):
        """
        data_dict: {"timestamp": ..., "side": ..., "reason": ...}
        """
        try:
            with open(self.filepath, "a", newline="") as f:
                writer = csv.writer(f)
                # Map dict to columns or just dump
                row = [
                    data_dict.get("timestamp", datetime.now().isoformat()),
                    data_dict.get("side", ""),
                    data_dict.get("reason", ""),
                    str(data_dict)
                ]
                writer.writerow(row)
        except Exception as e:
            logger.error(f"Failed to write to ledger: {e}")

class TradeLimiter:
    def __init__(self, max_per_day, max_per_hour, cooldown_seconds):
        self.max_per_day = max_per_day
        self.max_per_hour = max_per_hour
        self.cooldown_seconds = cooldown_seconds
        self.trades_today = 0
        self.trades_last_hour = [] # List of timestamps
        self.last_trade_time = 0

    def allow(self):
        now = time.time()

        # Cooldown check
        if now - self.last_trade_time < self.cooldown_seconds:
            return False

        # Daily limit check
        # (Assuming caller resets trades_today daily, or we check date change)
        # For simplicity, we rely on external reset or just monotonic counter if script restarts daily.
        if self.trades_today >= self.max_per_day:
            return False

        # Hourly limit check
        # Clean up old timestamps
        self.trades_last_hour = [t for t in self.trades_last_hour if now - t < 3600]
        if len(self.trades_last_hour) >= self.max_per_hour:
            return False

        return True

    def record(self):
        now = time.time()
        self.last_trade_time = now
        self.trades_today += 1
        self.trades_last_hour.append(now)

def format_kv(**kwargs):
    """
    Format key-value pairs for logging.
    Example: spot=84002 straddle=723
    """
    return " ".join([f"{k}={v}" for k, v in kwargs.items()])

class DataFreshnessGuard:
    def __init__(self, stale_bars=5, max_same_close=5, require_volume=False):
        self.stale_bars = stale_bars
        self.max_same_close = max_same_close
        self.require_volume = require_volume

    def is_fresh(self, df):
        """
        Check if DataFrame data is fresh.
        Returns: (is_fresh: bool, reason: str)
        """
        if df is None or df.empty:
            return False, "empty_data"

        # Check if last timestamp is recent (simplified)
        # In a real system, compare df.index[-1] with now

        # Check for flatline (same close price for N bars)
        if len(df) >= self.max_same_close:
            last_closes = df['close'].tail(self.max_same_close)
            if last_closes.nunique() == 1:
                return False, "price_flatline"

        if self.require_volume:
            if df['volume'].iloc[-1] == 0:
                 return False, "zero_volume"

        return True, "fresh"

class RiskConfig:
    def __init__(self, sl_pct, tp_pct, max_hold_min):
        self.sl_pct = sl_pct
        self.tp_pct = tp_pct
        self.max_hold_min = max_hold_min

class RiskManager:
    def __init__(self, config):
        self.config = config
        self.entry_price = 0.0
        self.side = None
        self.entry_time = None

    def on_entry(self, side, price):
        self.side = side
        self.entry_price = float(price)
        self.entry_time = time.time()

    def should_exit(self, current_price):
        """
        Check SL/TP/Time.
        Returns: (should_exit: bool, reason: str)
        """
        if not self.entry_time:
             return False, "no_position"

        current_price = float(current_price)

        # Time stop
        elapsed_min = (time.time() - self.entry_time) / 60
        if elapsed_min >= self.config.max_hold_min:
            return True, "time_stop"

        # SL/TP
        if self.side == "LONG": # Buy Premium
            # SL: Price Drops
            if current_price <= self.entry_price * (1 - self.config.sl_pct / 100):
                 return True, "stop_loss"
            # TP: Price Rises
            if current_price >= self.entry_price * (1 + self.config.tp_pct / 100):
                 return True, "take_profit"

        elif self.side == "SHORT": # Sell Premium
            # SL: Price Rises
            if current_price >= self.entry_price * (1 + self.config.sl_pct / 100):
                 return True, "stop_loss"
            # TP: Price Drops
            if current_price <= self.entry_price * (1 - self.config.tp_pct / 100):
                 return True, "take_profit"

        return False, "hold"
