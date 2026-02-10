import time
import os
import csv
from datetime import datetime
import threading

def format_kv(**kwargs):
    """Formats key-value pairs into a string like 'key=value key2=value2'."""
    return " ".join([f"{k}={v}" for k, v in kwargs.items()])

class SignalDebouncer:
    def __init__(self):
        self.last_states = {}

    def edge(self, key, condition_bool):
        """
        Returns True ONLY on False -> True transition (rising edge).
        """
        last = self.last_states.get(key, False)
        self.last_states[key] = condition_bool
        return condition_bool and not last

    def cross_above(self, prev_val, curr_val, threshold):
        return prev_val <= threshold and curr_val > threshold

    def cross_below(self, prev_val, curr_val, threshold):
        return prev_val >= threshold and curr_val < threshold

class TradeLimiter:
    def __init__(self, max_per_day, max_per_hour, cooldown_seconds):
        self.max_per_day = max_per_day
        self.max_per_hour = max_per_hour
        self.cooldown_seconds = cooldown_seconds

        self.trades_today = 0
        self.trade_timestamps = [] # Keep timestamps for hour check
        self.last_trade_time = 0
        self.reset_date = datetime.now().date()

    def _check_reset(self):
        now = datetime.now()
        if now.date() != self.reset_date:
            self.trades_today = 0
            self.trade_timestamps = []
            self.reset_date = now.date()

    def allow(self):
        self._check_reset()
        now = time.time()

        # Cooldown
        if (now - self.last_trade_time) < self.cooldown_seconds:
            return False

        # Daily limit
        if self.trades_today >= self.max_per_day:
            return False

        # Hourly limit
        cutoff = now - 3600
        trades_last_hour = sum(1 for t in self.trade_timestamps if t > cutoff)
        if trades_last_hour >= self.max_per_hour:
            return False

        return True

    def record(self):
        self._check_reset()
        now = time.time()
        self.trades_today += 1
        self.trade_timestamps.append(now)
        self.last_trade_time = now

class TradeLedger:
    def __init__(self, filepath):
        self.filepath = filepath
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(os.path.dirname(self.filepath)):
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)

        if not os.path.exists(self.filepath):
            with open(self.filepath, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "side", "reason", "details"])

    def append(self, data):
        """
        data: dict with keys matching header or extra keys.
        """
        try:
            with open(self.filepath, 'a', newline='') as f:
                writer = csv.writer(f)
                # Flexible writing
                row = [
                    data.get("timestamp", datetime.now().isoformat()),
                    data.get("side", ""),
                    data.get("reason", ""),
                    str(data) # Dump everything else here
                ]
                writer.writerow(row)
        except Exception as e:
            print(f"Ledger Error: {e}", flush=True)

class DataFreshnessGuard:
    def __init__(self, stale_bars=5, max_same_close=5, require_volume=False):
        self.stale_bars = stale_bars
        self.max_same_close = max_same_close
        self.require_volume = require_volume

    def is_fresh(self, df):
        if df.empty:
            return False, "Empty DataFrame"

        # Check last timestamp
        last_ts = df.iloc[-1].get("datetime")
        if last_ts:
            # If data is older than X minutes?
            # Hard to judge without knowing timeframe, skipping for now.
            pass

        # Check for flatline (same close price repeatedly)
        if len(df) >= self.max_same_close:
            last_closes = df['close'].tail(self.max_same_close)
            if last_closes.nunique() == 1:
                return False, "Flatline Data (Same Close)"

        # Check volume
        if self.require_volume:
            if df.iloc[-1].get("volume", 0) <= 0:
                return False, "Zero Volume"

        return True, "Fresh"

class RiskConfig:
    def __init__(self, sl_pct, tp_pct, max_hold_min):
        self.sl_pct = sl_pct
        self.tp_pct = tp_pct
        self.max_hold_min = max_hold_min

class RiskManager:
    def __init__(self, config):
        self.config = config
        self.entry_price = 0
        self.entry_time = None
        self.side = None

    def on_entry(self, side, price):
        self.side = side
        self.entry_price = price
        self.entry_time = datetime.now()

    def should_exit(self, current_price):
        if not self.entry_time:
            return False, ""

        # Time stop
        minutes = (datetime.now() - self.entry_time).total_seconds() / 60
        if minutes > self.config.max_hold_min:
            return True, "time_stop"

        # PnL
        if self.entry_price == 0:
            return False, ""

        pnl_pct = 0
        if self.side == "LONG":
            pnl_pct = (current_price - self.entry_price) / self.entry_price * 100
        else:
            pnl_pct = (self.entry_price - current_price) / self.entry_price * 100

        if pnl_pct <= -self.config.sl_pct:
            return True, "stop_loss"

        if pnl_pct >= self.config.tp_pct:
            return True, "take_profit"

        return False, ""
