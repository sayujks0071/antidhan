#!/usr/bin/env python3
import sys
import os
from datetime import datetime, time, timedelta
import pandas as pd

# Add repo root to path to allow imports (if running as script)
try:
    from base_strategy import BaseStrategy
except ImportError:
    # Try setting path to find utils
    script_dir = os.path.dirname(os.path.abspath(__file__))
    strategies_dir = os.path.dirname(script_dir)
    utils_dir = os.path.join(strategies_dir, 'utils')
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    from base_strategy import BaseStrategy

class GapFadeStrategy(BaseStrategy):
    """
    Gap Fade Strategy V2:
    - Fades gaps > 0.5% (or custom threshold).
    - Requires Reversal Confirmation (Close against Gap).
    - Uses ADX Filter (< 30) to avoid fading strong trends.
    - Sets Stop Loss based on Reversal Candle High/Low.
    """
    def __init__(self, symbol, quantity, gap_threshold=0.5, api_key=None, host=None, log_file=None, client=None, **kwargs):
        super().__init__(
            name="GapFadeStrategy",
            symbol=symbol,
            quantity=quantity,
            api_key=api_key,
            host=host,
            log_file=log_file,
            client=client,
            **kwargs
        )
        self.gap_threshold = gap_threshold
        self.stop_loss_price = None
        self.take_profit_price = None

        # State
        self.last_trade_date = None

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument("--threshold", type=float, default=0.5, help="Gap Threshold %%")

    @classmethod
    def parse_arguments(cls, args):
        kwargs = super().parse_arguments(args)
        kwargs['gap_threshold'] = args.threshold
        if not kwargs.get('symbol'):
            kwargs['symbol'] = "NIFTY"
        return kwargs

    def cycle(self):
        self.logger.info(f"Starting Gap Fade Cycle for {self.symbol}")

        # Handle NIFTY -> NIFTY 50 mapping for quote and history
        target_symbol = f"{self.symbol} 50" if self.symbol == "NIFTY" else self.symbol

        # Check Time
        now = datetime.now()
        current_time = now.time()

        # Define Time Windows
        # Entry only allowed in first hour: 9:15 - 10:15
        start_time = time(9, 15)
        end_entry_time = time(10, 15)
        exit_time = time(15, 15)

        # 1. Exit Logic (Time Based)
        if current_time >= exit_time and self.pm.current_position != 0:
            self.logger.info("End of Day Exit.")
            action = "SELL" if self.pm.current_position > 0 else "BUY"
            self.execute_trade(action, abs(self.pm.current_position))
            return

        # 2. SL/TP Logic
        quote = self.client.get_quote(target_symbol, self.exchange)
        if not quote or 'ltp' not in quote:
            self.logger.error("Could not fetch quote.")
            return

        current_price = float(quote['ltp'])

        if self.pm.current_position != 0:
            # Check Stop Loss
            if self.stop_loss_price:
                if (self.pm.current_position > 0 and current_price < self.stop_loss_price) or \
                   (self.pm.current_position < 0 and current_price > self.stop_loss_price):
                    self.logger.info(f"Stop Loss Hit @ {current_price} (SL: {self.stop_loss_price})")
                    action = "SELL" if self.pm.current_position > 0 else "BUY"
                    self.execute_trade(action, abs(self.pm.current_position))
                    self.stop_loss_price = None
                    self.take_profit_price = None
                    return

            # Check Take Profit
            if self.take_profit_price:
                if (self.pm.current_position > 0 and current_price > self.take_profit_price) or \
                   (self.pm.current_position < 0 and current_price < self.take_profit_price):
                    self.logger.info(f"Take Profit Hit @ {current_price} (TP: {self.take_profit_price})")
                    action = "SELL" if self.pm.current_position > 0 else "BUY"
                    self.execute_trade(action, abs(self.pm.current_position))
                    self.stop_loss_price = None
                    self.take_profit_price = None
                    return

            return # Position is open, no new entry

        # 3. Entry Logic
        # Only check entry window
        if not (start_time <= current_time <= end_entry_time):
            return

        # Check if we already traded today
        if self.last_trade_date == now.date():
             return

        # Get Previous Close (for Gap calculation)
        daily_df = self.fetch_history(days=3, interval="1d", symbol=target_symbol)
        if daily_df.empty or len(daily_df) < 2:
            self.logger.warning("Insufficient daily data for gap calculation.")
            return

        # Identify previous close carefully
        # If last row date is today, use -2. Else -1.
        last_row_date = daily_df.iloc[-1]['datetime'].date()
        if last_row_date == now.date():
             prev_close = daily_df.iloc[-2]['close']
        else:
             prev_close = daily_df.iloc[-1]['close']

        # Get Today's Open from Quote
        day_open = float(quote.get('open', 0))
        if day_open == 0:
             if last_row_date == now.date():
                 day_open = daily_df.iloc[-1]['open']
             else:
                 day_open = current_price

        gap_pct = ((day_open - prev_close) / prev_close) * 100

        # Log gap only if significant
        if abs(gap_pct) > 0.1:
            self.logger.info(f"Gap: {gap_pct:.2f}%, LTP: {current_price}, Open: {day_open}")

        if abs(gap_pct) < self.gap_threshold:
            return

        # Fetch Intraday History
        hist_df = self.fetch_history(days=2, interval="5m", symbol=target_symbol)
        if hist_df.empty:
            return

        # Filter for today's candles
        today_df = hist_df[hist_df['datetime'].dt.date == now.date()]
        if today_df.empty:
            return

        # ADX Filter (< 30)
        adx_series = self.calculate_adx_series(hist_df)
        if not adx_series.empty:
            adx = adx_series.iloc[-1]
            if adx > 30:
                self.logger.info(f"ADX {adx:.2f} > 30. Strong Trend. Skipping Fade.")
                return

        # Get Last Completed Candle
        completed_candle = None
        for i in range(len(today_df)-1, -1, -1):
             candle_start = today_df.iloc[i]['datetime']
             # Assume completed if start time + 5min <= now
             if candle_start + timedelta(minutes=5) <= now:
                 completed_candle = today_df.iloc[i]
                 break

        if completed_candle is None:
             self.logger.info("No completed candle found yet.")
             return

        # Reversal Confirmation Logic on COMPLETED candle

        if gap_pct > self.gap_threshold: # Gap UP -> SELL
            # Check for RED candle
            if completed_candle['close'] < completed_candle['open']:
                self.logger.info(f"Gap UP + Reversal (Red) Detected @ {completed_candle['datetime']}. Shorting.")

                entry_price = current_price
                sl_price = completed_candle['high'] * 1.0005 # High of reversal candle + buffer
                tp_price = entry_price * 0.98 # 2% Target

                # Sanity check SL
                if sl_price <= entry_price:
                     sl_price = entry_price * 1.005

                self.stop_loss_price = sl_price
                self.take_profit_price = tp_price

                qty = self.get_adaptive_quantity(entry_price)
                if self.execute_trade("SELL", qty, entry_price):
                    self.last_trade_date = now.date()

        elif gap_pct < -self.gap_threshold: # Gap DOWN -> BUY
             # Check for GREEN candle
             if completed_candle['close'] > completed_candle['open']:
                self.logger.info(f"Gap DOWN + Reversal (Green) Detected @ {completed_candle['datetime']}. Buying.")

                entry_price = current_price
                sl_price = completed_candle['low'] * 0.9995 # Low of reversal candle - buffer
                tp_price = entry_price * 1.02 # 2% Target

                if sl_price >= entry_price:
                     sl_price = entry_price * 0.995

                self.stop_loss_price = sl_price
                self.take_profit_price = tp_price

                qty = self.get_adaptive_quantity(entry_price)
                if self.execute_trade("BUY", qty, entry_price):
                    self.last_trade_date = now.date()

if __name__ == "__main__":
    GapFadeStrategy.cli()
