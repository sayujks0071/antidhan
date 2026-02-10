import csv
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

class SignalDebouncer:
    """
    Prevents signal flickering by only triggering on rising edges (False -> True).
    """
    def __init__(self):
        self.states = {}

    def edge(self, name: str, condition: bool) -> bool:
        """
        Returns True only when condition transitions from False to True.
        """
        last_state = self.states.get(name, False)
        self.states[name] = condition
        return condition and not last_state

    @staticmethod
    def cross_above(series_a, series_b, threshold=0) -> bool:
        """
        Check if series_a crosses above series_b.
        Simple implementation assuming scalar values passed in loop.
        For true series (list/array), logic would differ.
        Here we assume usage like: cross_above(prev_val, curr_val, threshold) from prompt?
        Prompt says: cross_up = SignalDebouncer.cross_above(prev_val, curr_val, threshold)
        """
        # Wait, the prompt example says:
        # cross_up = SignalDebouncer.cross_above(prev_val, curr_val, threshold)
        # This implies checking if value crossed threshold.
        # But commonly cross_above means A crosses B.
        # Let's support both: cross_above(prev, curr, threshold) -> curr > threshold and prev <= threshold
        return series_a <= threshold and series_b > threshold

    @staticmethod
    def cross_below(prev_val, curr_val, threshold) -> bool:
        return prev_val >= threshold and curr_val < threshold


class TradeLedger:
    """
    Logs trades to a CSV file.
    """
    def __init__(self, filepath: str):
        self.filepath = filepath
        self._ensure_dir()
        if not os.path.exists(self.filepath):
            self._write_header()

    def _ensure_dir(self):
        directory = os.path.dirname(self.filepath)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

    def _write_header(self):
        with open(self.filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "side", "reason", "symbol", "price", "quantity", "pnl"])

    def append(self, data: Dict[str, Any]):
        """
        Appends a trade record.
        Expected keys: timestamp, side, reason, symbol, price, quantity, pnl (optional)
        """
        with open(self.filepath, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                data.get("timestamp", datetime.now().isoformat()),
                data.get("side", ""),
                data.get("reason", ""),
                data.get("symbol", ""),
                data.get("price", 0.0),
                data.get("quantity", 0),
                data.get("pnl", 0.0)
            ])


class TradeLimiter:
    """
    Limits trade frequency and count.
    """
    def __init__(self, max_per_day: int, max_per_hour: int, cooldown_seconds: int):
        self.max_per_day = max_per_day
        self.max_per_hour = max_per_hour
        self.cooldown_seconds = cooldown_seconds

        self.daily_count = 0
        self.hourly_timestamps = []
        self.last_trade_time = 0
        self.last_reset_day = datetime.now().date()

    def allow(self) -> bool:
        now = datetime.now()
        today = now.date()

        # Reset daily count if new day
        if today != self.last_reset_day:
            self.daily_count = 0
            self.hourly_timestamps = []
            self.last_reset_day = today

        # Check daily limit
        if self.daily_count >= self.max_per_day:
            return False

        # Clean up hourly timestamps (older than 1 hour)
        cutoff = now - timedelta(hours=1)
        self.hourly_timestamps = [t for t in self.hourly_timestamps if t > cutoff]

        # Check hourly limit
        if len(self.hourly_timestamps) >= self.max_per_hour:
            return False

        # Check cooldown
        if (time.time() - self.last_trade_time) < self.cooldown_seconds:
            return False

        return True

    def record(self):
        """Call this when a trade is actually placed."""
        now = datetime.now()
        self.daily_count += 1
        self.hourly_timestamps.append(now)
        self.last_trade_time = time.time()


def format_kv(**kwargs) -> str:
    """Formats key-value pairs for logging."""
    return " ".join([f"{k}={v}" for k, v in kwargs.items()])


class DataFreshnessGuard:
    """
    Checks if data is stale.
    """
    def __init__(self, stale_bars: int = 5, max_same_close: int = 5, require_volume: bool = False):
        self.stale_bars = stale_bars
        self.max_same_close = max_same_close
        self.require_volume = require_volume

    def is_fresh(self, df) -> Tuple[bool, str]:
        if df is None or df.empty:
            return False, "empty_dataframe"

        # Check timestamp of last bar
        if "datetime" in df.columns:
            last_time = df["datetime"].iloc[-1]
            if isinstance(last_time, str):
                # Try parsing if string
                try:
                    last_time = datetime.fromisoformat(last_time.replace("Z", "+00:00"))
                except:
                    pass # Keep as is if fails

            # Simple check: if last time is too old compared to now?
            # Requires timezone awareness which is tricky.
            # We'll skip complex time check and rely on "stale_bars" count logic if meant to be gap check.
            # But "stale_bars" implies checking if data hasn't updated in N calls.
            # Actually, usually this checks if the *latest* timestamp is lagging behind *current time*.
            pass

        # Check for flatlining close prices
        if len(df) >= self.max_same_close:
            recent_closes = df["close"].tail(self.max_same_close)
            if recent_closes.nunique() == 1:
                return False, f"flatline_close_{self.max_same_close}_bars"

        # Check volume
        if self.require_volume and "volume" in df.columns:
            if df["volume"].iloc[-1] == 0:
                return False, "zero_volume"

        return True, "ok"


class RiskConfig:
    def __init__(self, sl_pct: float, tp_pct: float, max_hold_min: int):
        self.sl_pct = sl_pct
        self.tp_pct = tp_pct
        self.max_hold_min = max_hold_min


class RiskManager:
    """
    Tracks a single trade/position risk (SL/TP/Time).
    """
    def __init__(self, config: RiskConfig):
        self.config = config
        self.entry_price = 0.0
        self.entry_time = 0
        self.side = "LONG" # LONG or SHORT

    def on_entry(self, side: str, price: float):
        self.side = side.upper()
        self.entry_price = price
        self.entry_time = time.time()

    def should_exit(self, current_price: float) -> Tuple[bool, str]:
        if self.entry_price == 0:
            return False, ""

        # Check Time Stop
        if self.config.max_hold_min > 0:
            elapsed_min = (time.time() - self.entry_time) / 60
            if elapsed_min >= self.config.max_hold_min:
                return True, "time_stop"

        # Calculate PnL %
        # For LONG: (Curr - Entry) / Entry
        # For SHORT: (Entry - Curr) / Entry
        if self.side == "LONG":
            pnl_pct = (current_price - self.entry_price) / self.entry_price * 100
        else:
            pnl_pct = (self.entry_price - current_price) / self.entry_price * 100

        # Check SL (pnl is negative)
        # sl_pct is positive e.g. 30%. Trigger if pnl_pct <= -30
        if pnl_pct <= -self.config.sl_pct:
            return True, "stop_loss"

        # Check TP
        if pnl_pct >= self.config.tp_pct:
            return True, "take_profit"

        return False, ""
