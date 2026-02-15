#!/usr/bin/env python3
"""
NSE MA Crossover Strategy
Simple Moving Average Crossover for NSE stocks.
Entry: Buy when SMA 20 crosses above SMA 50.
Exit: Sell when SMA 20 crosses below SMA 50.
Inherits from BaseStrategy for significant code reduction.
"""
import os
import sys

# Add repo root to path to find BaseStrategy
try:
    from base_strategy import BaseStrategy
except ImportError:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    strategies_dir = os.path.dirname(current_dir)
    utils_dir = os.path.join(strategies_dir, "utils")
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    from base_strategy import BaseStrategy

class NSEMaCrossoverStrategy(BaseStrategy):
    def setup(self):
        # Parameters
        self.short_window = int(getattr(self, 'short_window', 20))
        self.long_window = int(getattr(self, 'long_window', 50))

        # Auto-detect exchange for Indices
        if self.symbol and ("NIFTY" in self.symbol.upper() or "BANKNIFTY" in self.symbol.upper()):
            self.exchange = "NSE_INDEX"

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--short_window', type=int, default=20, help='Short Moving Average Window')
        parser.add_argument('--long_window', type=int, default=50, help='Long Moving Average Window')
        parser.add_argument('--port', type=int, help='API Port (Legacy)')

    @classmethod
    def parse_arguments(cls, args):
        kwargs = super().parse_arguments(args)
        # Support legacy --port arg
        if hasattr(args, 'port') and args.port:
            kwargs['host'] = f"http://127.0.0.1:{args.port}"
        return kwargs

    def calculate_indicators(self, df):
        df = df.copy()
        df['short_mavg'] = self.calculate_sma(df['close'], period=self.short_window)
        df['long_mavg'] = self.calculate_sma(df['close'], period=self.long_window)
        return df

    def cycle(self):
        # Fetch Data
        df = self.fetch_history(days=5, interval="5m")
        if df.empty or len(df) < self.long_window:
            self.logger.warning("Insufficient data.")
            return

        # New Candle Check
        if not self.check_new_candle(df):
            return

        df = self.calculate_indicators(df)
        self.check_signals(df)

    def check_signals(self, df):
        last = df.iloc[-1]
        prev = df.iloc[-2]
        current_price = last['close']

        self.logger.info(f"Price: {current_price}, SMA{self.short_window}: {last['short_mavg']:.2f}, SMA{self.long_window}: {last['long_mavg']:.2f}")

        has_pos = self.pm.has_position() if self.pm else False
        pos_qty = self.pm.position if self.pm else 0

        # Golden Cross (Buy)
        if (prev['short_mavg'] <= prev['long_mavg']) and (last['short_mavg'] > last['long_mavg']):
            if not has_pos:
                self.logger.info(f"Entry signal detected (Golden Cross). Buying {self.quantity} at {current_price}")
                self.buy(self.quantity, current_price)
            elif pos_qty < 0:
                self.logger.info("Reversing Short to Long")
                self.buy(abs(pos_qty) + self.quantity, current_price)

        # Death Cross (Sell)
        elif (prev['short_mavg'] >= prev['long_mavg']) and (last['short_mavg'] < last['long_mavg']):
            if has_pos and pos_qty > 0:
                self.logger.info(f"Exiting position (Death Cross).")
                self.sell(abs(pos_qty), current_price)

    def get_signal(self, df):
        """Backtesting signal generation"""
        if df.empty or len(df) < self.long_window + 5:
            return 'HOLD', 0.0, {}

        df = self.calculate_indicators(df)
        last = df.iloc[-1]
        prev = df.iloc[-2]

        # Entry logic
        if (prev['short_mavg'] <= prev['long_mavg']) and (last['short_mavg'] > last['long_mavg']):
            return 'BUY', 1.0, {
                'reason': 'MA Crossover (Golden Cross)',
                'price': last['close'],
                'short_mavg': last['short_mavg'],
                'long_mavg': last['long_mavg']
            }

        # Exit logic
        if (prev['short_mavg'] >= prev['long_mavg']) and (last['short_mavg'] < last['long_mavg']):
             return 'SELL', 1.0, {
                'reason': 'MA Crossover (Death Cross)',
                'price': last['close'],
                'short_mavg': last['short_mavg'],
                'long_mavg': last['long_mavg']
            }

        return 'HOLD', 0.0, {}

# Backtesting alias
generate_signal = NSEMaCrossoverStrategy.backtest_signal

if __name__ == "__main__":
    NSEMaCrossoverStrategy.cli()
