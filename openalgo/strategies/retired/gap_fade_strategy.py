#!/usr/bin/env python3
import sys
import os
from datetime import datetime, time

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
    def __init__(self, symbol, quantity, gap_threshold=0.5, api_key=None, host=None, log_file=None, client=None, **kwargs):
        super().__init__(
            name="GapFadeStrategy",
            symbol=symbol,
            quantity=quantity,
            api_key=api_key,
            host=host,
            log_file=log_file,
            client=client
        )
        self.gap_threshold = gap_threshold
        # State to track if we already traded today
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
        start_time = time(9, 15)
        end_entry_time = time(10, 0)
        exit_time = time(15, 15)

        # 1. Exit Logic (Time Based)
        if current_time >= exit_time and self.pm.current_position != 0:
            self.logger.info("End of Day Exit.")
            action = "SELL" if self.pm.current_position > 0 else "BUY"
            self.execute_trade(action, abs(self.pm.current_position))
            return

        # 2. SL/TP Logic
        quote = self.client.get_quote(target_symbol, self.exchange)
        if not quote:
            self.logger.error("Could not fetch quote.")
            return

        current_price = float(quote['ltp'])

        if self.pm.current_position != 0:
            entry_price = self.pm.average_price
            pnl_pct = 0
            if entry_price > 0:
                if self.pm.current_position > 0: # Long
                    pnl_pct = (current_price - entry_price) / entry_price * 100
                else: # Short
                    pnl_pct = (entry_price - current_price) / entry_price * 100

            # Stop Loss: 1%
            if pnl_pct < -1.0:
                self.logger.info(f"Stop Loss Hit ({pnl_pct:.2f}%). Exiting.")
                action = "SELL" if self.pm.current_position > 0 else "BUY"
                self.execute_trade(action, abs(self.pm.current_position))
                return

            # Take Profit: 2%
            if pnl_pct > 2.0:
                self.logger.info(f"Take Profit Hit ({pnl_pct:.2f}%). Exiting.")
                action = "SELL" if self.pm.current_position > 0 else "BUY"
                self.execute_trade(action, abs(self.pm.current_position))
                return

            return # Position is open, no new entry

        # 3. Entry Logic
        # Only check entry between 9:15 and 10:00
        if not (start_time <= current_time <= end_entry_time):
            return

        # Check if we already traded today
        if self.last_trade_date == now.date():
             self.logger.info("Already traded today. Skipping.")
             return

        # Get Previous Close (for Gap calculation)
        # Optimization: Fetch previous close
        df = self.fetch_history(days=5, interval="day", symbol=target_symbol)
        if df.empty:
            return

        prev_close = df.iloc[-1]['close']

        # Current Open (of the day)
        day_open = float(quote.get('open', 0))
        if day_open == 0:
             day_open = current_price # Fallback

        gap_pct = ((day_open - prev_close) / prev_close) * 100

        self.logger.info(f"Gap: {gap_pct:.2f}%, LTP: {current_price}, Open: {day_open}")

        if abs(gap_pct) < self.gap_threshold:
            return

        # Reversal Confirmation Logic
        if gap_pct > self.gap_threshold: # Gap UP
            # Trend Confirmation: LTP must be below Open (Red Candle) to confirm fading
            if current_price < day_open:
                # RSI Check (Intraday 5m) - Reduce fetch size to 3 days
                hist_df = self.fetch_history(days=3, interval="5m", symbol=target_symbol)
                if not hist_df.empty:
                    rsi = self.calculate_rsi(hist_df['close']).iloc[-1]
                    if rsi > 60: # Overbought
                        self.logger.info(f"Gap UP + Reversal (LTP {current_price} < Open {day_open}) + RSI {rsi:.2f}. SHORT.")
                        qty = self.get_adaptive_quantity(current_price)
                        if self.execute_trade("SELL", qty, current_price):
                            self.last_trade_date = now.date()

        elif gap_pct < -self.gap_threshold: # Gap DOWN
             # Trend Confirmation: LTP must be above Open (Green Candle) to confirm fading
             if current_price > day_open:
                # RSI Check - Reduce fetch size to 3 days
                hist_df = self.fetch_history(days=3, interval="5m", symbol=target_symbol)
                if not hist_df.empty:
                    rsi = self.calculate_rsi(hist_df['close']).iloc[-1]
                    if rsi < 40: # Oversold
                        self.logger.info(f"Gap DOWN + Reversal (LTP {current_price} > Open {day_open}) + RSI {rsi:.2f}. LONG.")
                        qty = self.get_adaptive_quantity(current_price)
                        if self.execute_trade("BUY", qty, current_price):
                            self.last_trade_date = now.date()

if __name__ == "__main__":
    GapFadeStrategy.cli()
