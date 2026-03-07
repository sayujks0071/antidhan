import logging
import pandas as pd
from datetime import datetime, time

import os
import sys

# Ensure openalgo is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

try:
    from strategies.utils.base_strategy import BaseStrategy
except ImportError:
    from openalgo.strategies.utils.base_strategy import BaseStrategy

class GapFadeStrategy(BaseStrategy):
    """
    Fades opening gaps if a Reversal Candle confirms the direction using 2 days of 5-minute intraday data,
    and includes an ADX trend filter (< 25) and RSI confirmation (> 60 / < 40) to filter out strong trend ('Gap and Go') days.
    """
    def setup(self):
        if self.symbol:
            self.name = f"GapFade_{self.symbol}"

        self.adx_period = getattr(self, "adx_period", 14)
        self.adx_threshold = getattr(self, "adx_threshold", 25)
        self.rsi_period = getattr(self, "rsi_period", 14)
        self.gap_threshold_pct = getattr(self, "gap_threshold_pct", 0.5)

        self.entry_time_start = getattr(self, "entry_time_start", time(9, 20))
        self.entry_time_end = getattr(self, "entry_time_end", time(10, 30))

        self.traded_today = False
        self.last_trade_date = None

    def cycle(self):
        current_time = datetime.now()
        current_date = current_time.date()

        # Reset trade state on a new day
        if self.last_trade_date != current_date:
            self.traded_today = False
            self.last_trade_date = current_date

        # Need 2 days of 5-minute data to see the gap from previous close
        df = self.fetch_and_prepare_data(days=2, min_rows=50)
        if df is None or len(df) < 20:
            return

        df = self.calculate_indicators(df)
        if df is None:
            return

        last = df.iloc[-1]

        # We need the previous day's close. Since we have intraday data, we find the last candle of the previous day.
        # This requires grouping by date.
        df['date'] = df.index.date
        dates = df['date'].unique()

        if len(dates) < 2:
            self.logger.warning("Not enough days to calculate gap")
            return

        prev_date = dates[-2]
        prev_day_data = df[df['date'] == prev_date]
        if prev_day_data.empty:
            return

        prev_close = prev_day_data.iloc[-1]['close']
        today_data = df[df['date'] == dates[-1]]

        if today_data.empty:
            return

        today_open = today_data.iloc[0]['open']

        # Ensure PM handles the position (Exits should be monitored all day)
        if self.pm and self.pm.has_position():
            position = self.pm.get_position()
            pos_type = position.get('direction', 'LONG')
            open_qty = position.get('quantity', 0)

            # Intraday Square-off at 15:15
            if current_time.time() >= time(15, 15):
                self.logger.info("End of day square off.")
                action = 'SELL' if pos_type == 'LONG' else 'BUY'
                self.execute_trade(action, open_qty, last['close'])
                return

            # Use tighter Stop Loss based on first candle's High/Low
            first_candle = today_data.iloc[0]

            # Also implement a basic Take Profit (e.g. 1% move)
            entry_price = position.get('average_price', 0)
            if pos_type == 'LONG':
                if last['close'] < first_candle['low']:
                    self.logger.info(f"Stop Loss hit (Long): Close {last['close']} < First Candle Low {first_candle['low']}")
                    self.execute_trade('SELL', open_qty, last['close'])
                elif entry_price > 0 and last['close'] > entry_price * 1.01:
                    self.logger.info(f"Take Profit hit (Long): {last['close']}")
                    self.execute_trade('SELL', open_qty, last['close'])
            elif pos_type == 'SHORT':
                if last['close'] > first_candle['high']:
                    self.logger.info(f"Stop Loss hit (Short): Close {last['close']} > First Candle High {first_candle['high']}")
                    self.execute_trade('BUY', open_qty, last['close'])
                elif entry_price > 0 and last['close'] < entry_price * 0.99:
                    self.logger.info(f"Take Profit hit (Short): {last['close']}")
                    self.execute_trade('BUY', open_qty, last['close'])

            return

        # Only trade within specific morning window
        if not (self.entry_time_start <= current_time.time() <= self.entry_time_end):
            return

        if self.traded_today:
            # Prevent multiple entries per day for gap fade
            return

        gap_pct = ((today_open - prev_close) / prev_close) * 100

        is_gap_up = gap_pct >= self.gap_threshold_pct
        is_gap_down = gap_pct <= -self.gap_threshold_pct

        if not (is_gap_up or is_gap_down):
            return

        # Reversal Candle Logic (from Leaderboard recommendation)
        # We need the reversal candle check. A reversal candle is usually the first or current candle.
        # Let's say if gap up, the current candle must be a bearish reversal candle (close < open)
        # Or better, the very first 5 min candle must have been a reversal candle or current is.
        # Following Leaderboard exactly: "Add a 'Reversal Candle' check (e.g., Close < Open for Gap Up)"
        is_bearish_reversal = today_data.iloc[0]['close'] < today_data.iloc[0]['open']
        is_bullish_reversal = today_data.iloc[0]['close'] > today_data.iloc[0]['open']

        # Filters
        adx = last['adx']
        rsi = last['rsi']

        is_weak_trend = adx < self.adx_threshold

        # Base quantity
        base_qty = self.get_adaptive_quantity(last['close'], risk_pct=1.0, capital=500000)

        if is_gap_up and is_bearish_reversal and is_weak_trend and rsi > 60:
            self.logger.info(f"Gap Up Fade: Shorting {base_qty} {self.symbol} at {last['close']}")
            self.execute_trade('SELL', base_qty, last['close'])
            self.traded_today = True

        elif is_gap_down and is_bullish_reversal and is_weak_trend and rsi < 40:
            self.logger.info(f"Gap Down Fade: Buying {base_qty} {self.symbol} at {last['close']}")
            self.execute_trade('BUY', base_qty, last['close'])
            self.traded_today = True

    def calculate_indicators(self, df):
        try:
            df['adx'] = self.calculate_adx(df, period=self.adx_period)
            df['rsi'] = self.calculate_rsi(df['close'], period=self.rsi_period)
            return df
        except Exception as e:
            self.logger.error(f"Error calculating indicators: {e}")
            return None

if __name__ == "__main__":
    GapFadeStrategy.cli()
