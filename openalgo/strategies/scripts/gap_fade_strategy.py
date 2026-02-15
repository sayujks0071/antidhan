import sys
import os
import pandas as pd
import numpy as np

# Ensure project root is in path
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    strategies_dir = os.path.dirname(current_dir)
    openalgo_dir = os.path.dirname(strategies_dir)
    project_root = os.path.dirname(openalgo_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
except Exception:
    pass

from openalgo.strategies.utils.base_strategy import BaseStrategy
from openalgo.strategies.utils.trading_utils import calculate_adx

class GapFadeStrategy(BaseStrategy):
    def setup(self):
        """
        Setup strategy specific parameters.
        """
        self.gap_threshold_pct = getattr(self, 'gap_pct', 0.5)
        self.adx_threshold = getattr(self, 'adx_max', 30)
        self.risk_reward_ratio = 2.0  # Target 2:1 RR

        self.sl_price = None
        self.tp_price = None

        # Default interval to 5m if not specified, though usually passed in __init__
        if not self.interval:
            self.interval = "5m"

    def get_signal(self, df):
        """
        Generate signal based on Gap Fade logic.

        Logic:
        1. Calculate Gap: (Today Open - Prev Day Close) / Prev Day Close * 100
        2. Filter: Gap > 0.5% (Absolute)
        3. Filter: ADX < 30 (Non-trending)
        4. Trigger: Reversal Candle
           - Gap Up -> Wait for Red Candle (Close < Open) -> SELL
           - Gap Down -> Wait for Green Candle (Close > Open) -> BUY
        """
        if df.empty or len(df) < 20: # Need enough data for ADX
            return "HOLD", 0.0, {}

        # 1. Calculate Gap (Requires Daily Data ideally, but we can approximate from 5m if we have enough history)
        # However, for robustness, we should fetch daily data.
        # But get_signal receives a single DF (usually intraday).
        # We'll assume the DF passed contains enough data to find the previous day's close.

        # Identify "Today" and "Yesterday" boundaries
        df['date'] = df.index.date
        unique_dates = df['date'].unique()

        if len(unique_dates) < 2:
            return "HOLD", 0.0, {"reason": "Insufficient daily history for Gap calc"}

        today = unique_dates[-1]
        yesterday = unique_dates[-2]

        today_data = df[df['date'] == today]
        yesterday_data = df[df['date'] == yesterday]

        if yesterday_data.empty or today_data.empty:
             return "HOLD", 0.0, {}

        prev_close = yesterday_data.iloc[-1]['close']
        today_open = today_data.iloc[0]['open']

        gap_pct = ((today_open - prev_close) / prev_close) * 100

        # 2. ADX Filter
        adx_series = calculate_adx(df, period=14)
        current_adx = adx_series.iloc[-1]

        if current_adx > self.adx_threshold:
             return "HOLD", 0.0, {"reason": f"ADX too high ({current_adx:.2f} > {self.adx_threshold})"}

        # 3. Gap Check
        if abs(gap_pct) < self.gap_threshold_pct:
             return "HOLD", 0.0, {"reason": f"Gap too small ({gap_pct:.2f}%)"}

        # 4. Reversal Candle Check (Current Candle)
        current_candle = df.iloc[-1]
        signal = "HOLD"
        reason = ""

        # Gap Up -> Look for Short
        if gap_pct > 0:
            # Check for Reversal (Red Candle)
            if current_candle['close'] < current_candle['open']:
                # Optional: Check if price is still above Prev Close (Gap partially filled but not fully?)
                # Strategy is to fade the gap, so we sell to close the gap.
                signal = "SELL"
                reason = f"Gap Up ({gap_pct:.2f}%) + Reversal Candle + ADX {current_adx:.2f}"
            else:
                reason = "Gap Up but no Reversal Candle"

        # Gap Down -> Look for Long
        elif gap_pct < 0:
            # Check for Reversal (Green Candle)
            if current_candle['close'] > current_candle['open']:
                signal = "BUY"
                reason = f"Gap Down ({gap_pct:.2f}%) + Reversal Candle + ADX {current_adx:.2f}"
            else:
                reason = "Gap Down but no Reversal Candle"

        return signal, 1.0, {"gap": gap_pct, "adx": current_adx, "reason": reason}

    def cycle(self):
        """
        Main execution cycle for live/paper trading.
        """
        # 1. Manage Existing Position (Exits)
        if self.pm.position != 0:
            current_price = self.get_current_price()
            if not current_price:
                return

            # Check Stop Loss
            if self.sl_price:
                if (self.pm.position > 0 and current_price <= self.sl_price) or \
                   (self.pm.position < 0 and current_price >= self.sl_price):
                    self.logger.info(f"SL Hit: {current_price} (SL: {self.sl_price})")
                    if self.pm.position > 0:
                        self.sell(abs(self.pm.position), urgency="HIGH")
                    else:
                        self.buy(abs(self.pm.position), urgency="HIGH")
                    self.sl_price = None
                    self.tp_price = None
                    return

            # Check Take Profit
            if self.tp_price:
                if (self.pm.position > 0 and current_price >= self.tp_price) or \
                   (self.pm.position < 0 and current_price <= self.tp_price):
                    self.logger.info(f"TP Hit: {current_price} (TP: {self.tp_price})")
                    if self.pm.position > 0:
                        self.sell(abs(self.pm.position), urgency="MEDIUM")
                    else:
                        self.buy(abs(self.pm.position), urgency="MEDIUM")
                    self.sl_price = None
                    self.tp_price = None
                    return

            # End of Day Exit (e.g., 15:15)
            # Assuming simple check if market is about to close
            # implementation depends on market_hours utils which we use implicitly via is_market_open
            # For now, we rely on manual or scheduler intervention for EOD, or add a time check here.
            pass

        # 2. Look for New Entries
        # Fetch enough history for ADX and Gap calculation (2+ days)
        df = self.fetch_history(days=5)

        if df.empty:
            return

        if self.pm.position == 0 and self.check_new_candle(df):
            signal, conf, details = self.get_signal(df)

            if signal == "BUY":
                # Calculate Stop Loss (Low of current reversal candle)
                current_low = df.iloc[-1]['low']
                current_close = df.iloc[-1]['close']

                # SL at Low of reversal candle
                self.sl_price = current_low - (current_low * 0.001) # 0.1% buffer

                # TP at 2x Risk
                risk = current_close - self.sl_price
                self.tp_price = current_close + (risk * self.risk_reward_ratio)

                self.buy(self.quantity, price=None, urgency="HIGH")
                self.logger.info(f"Signal: BUY | SL: {self.sl_price:.2f} | TP: {self.tp_price:.2f} | {details}")

            elif signal == "SELL":
                # Calculate Stop Loss (High of current reversal candle)
                current_high = df.iloc[-1]['high']
                current_close = df.iloc[-1]['close']

                # SL at High of reversal candle
                self.sl_price = current_high + (current_high * 0.001) # 0.1% buffer

                # TP at 2x Risk
                risk = self.sl_price - current_close
                self.tp_price = current_close - (risk * self.risk_reward_ratio)

                self.sell(self.quantity, price=None, urgency="HIGH")
                self.logger.info(f"Signal: SELL | SL: {self.sl_price:.2f} | TP: {self.tp_price:.2f} | {details}")
            else:
                self.logger.info(f"No Signal: {details.get('reason')}")

if __name__ == "__main__":
    GapFadeStrategy.cli()
