#!/usr/bin/env python3
"""
NSE MA Crossover Strategy
Simple Moving Average Crossover for NSE stocks.
Entry: Buy when SMA 20 crosses above SMA 50.
Exit: Sell when SMA 20 crosses below SMA 50.
"""
from strategy_preamble import BaseStrategy

class NSEMaCrossoverStrategy(BaseStrategy):
    # Declarative Parameters
    params = {
        'short_window': 20,
        'long_window': 50
    }

    # Declarative Indicators
    # Note: calculate_indicators in BaseStrategy will use these to populate df
    # But this strategy calculates them manually/specifically in cycle/signal
    # to control column names (short_mavg vs sma_20).
    # We can leverage BaseStrategy's calc if we standardize names,
    # but for now we'll stick to logic transparency.

    def setup(self):
        # Auto-detect exchange for Indices
        if self.symbol and ("NIFTY" in self.symbol.upper() or "BANKNIFTY" in self.symbol.upper()):
            self.exchange = "NSE_INDEX"

    def calculate_indicators(self, df):
        df = df.copy()
        df['short_mavg'] = self.calculate_sma(df['close'], period=self.short_window)
        df['long_mavg'] = self.calculate_sma(df['close'], period=self.long_window)
        return df

    def generate_signal(self, df):
        """
        Unified signal generation for both Live Execution (cycle) and Backtesting.
        Returns: Signal (str) or (Signal, Qty, Details)
        """
        if df.empty or len(df) < self.long_window:
            return 'HOLD'

        df = self.calculate_indicators(df)
        last = df.iloc[-1]
        prev = df.iloc[-2]

        details = {
            'price': last['close'],
            'short_mavg': last['short_mavg'],
            'long_mavg': last['long_mavg']
        }

        # Golden Cross (Buy)
        if (prev['short_mavg'] <= prev['long_mavg']) and (last['short_mavg'] > last['long_mavg']):
            return 'BUY', 1.0, {**details, 'reason': 'Golden Cross'}

        # Death Cross (Sell)
        elif (prev['short_mavg'] >= prev['long_mavg']) and (last['short_mavg'] < last['long_mavg']):
            return 'SELL', 1.0, {**details, 'reason': 'Death Cross'}

        return 'HOLD', 0.0, details

    # Backtesting alias (BaseStrategy expects get_signal for legacy/compat)
    def get_signal(self, df):
        return self.generate_signal(df)

if __name__ == "__main__":
    NSEMaCrossoverStrategy.cli()
